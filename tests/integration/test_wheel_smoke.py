from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv
from zipfile import ZipFile


def test_built_wheel_imports_and_loads_outside_source_tree(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    build_root = tmp_path / "project"
    shutil.copytree(
        project_root,
        build_root,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "build",
            "dist",
            "temp",
            "*.egg-info",
        ),
    )
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(wheel_dir)],
        cwd=build_root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("*.whl"))
    assert wheel.name.startswith("embed_data_model-")
    with ZipFile(wheel) as archive:
        archive_files = archive.namelist()
        package_files = [name for name in archive_files if name.endswith(".py")]
    assert any(name.startswith("embed_data_model/") for name in package_files)
    assert not any(name.startswith("embed_toolkit/") for name in package_files)
    assert any(
        ".dist-info/" in name and Path(name).name.lower().startswith("license")
        for name in archive_files
    )

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(environment)
    scripts = "Scripts" if os.name == "nt" else "bin"
    python = environment / scripts / ("python.exe" if os.name == "nt" else "python")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    code = """
from importlib.metadata import distribution
from pathlib import Path
import embed_data_model
from embed_data_model import (
    DatasetGraph, Patient, Exam, Finding, Procedure, ProcedureIdentity,
    Pathology, MammogramImage, RegionOfInterest, Laterality, load_embed, validate,
)
class ResearchPatient(Patient):
    pass
patient = ResearchPatient("P-1")
patient.research = {"labels": ["source"]}
graph = DatasetGraph()
graph.register(patient)
report = load_embed(
    patients=[{"empi_anon": "P-1"}],
    exams=[{"acc_anon": "A-1", "empi_anon": "P-1", "desc": "old"}],
    into=graph,
)
exam = graph.exam("A-1")
assert patient.exams == (exam,)
load_embed(exams=[{"acc_anon": "A-1", "desc": "new"}], into=graph)
assert graph.exam("A-1") is exam and exam.description == "new"
assert graph.patient("P-1") is patient and patient.research["labels"] == ["source"]
finding = exam.add_finding(Finding("A-1", Laterality.LEFT, "1"))
procedure = finding.add_procedure(Procedure(ProcedureIdentity("P-1", "2020-01-01", "biopsy", Laterality.LEFT)))
pathology = procedure.add_pathology(Pathology(("P-1", "report-1"), diagnosis="reported"))
assert patient.pathology == (pathology,)
path = "/root/cohort1/P-1/study/series/SOP.dcm"
load_embed(images=[{"anon_dicom_path": path, "acc_anon": "A-1", "ROI_coords": "[(0, 0, 9, 9)]"}], into=graph)
image = graph.source_image("SOP")
roi = image.rois[0]
roi.update(confidence=0.75)
graph.rekey(image, image_id="processed")
assert graph.roi("processed", "0") is roi
assert graph.roi_at_source(path, 0) is roi
parts = graph.partition(level="exam", key=lambda obj: "selected")
copy = parts["selected"].exam("A-1")
assert copy is not exam and copy.findings[0] is not finding
assert validate(copy).valid
other = DatasetGraph()
other.register(graph.pop(exam))
assert other.exam("A-1") is exam and graph.exam("A-1") is None
assert image.graph is other and roi.graph is other

# Review regressions must also work in the installed distribution.
identities = DatasetGraph()
first = identities.register(MammogramImage("I", source_sop_instance_uid="S1"))
second = identities.register(MammogramImage("J", source_sop_instance_uid="S2"))
try:
    first.update(source_sop_instance_uid="S2")
except ValueError:
    pass
else:
    raise AssertionError("Source SOP collisions must be rejected before mutation")
load_embed(images=[{"uid": "S2", "height": 123}], into=identities,
           columns={"images": {"source_sop_instance_uid": "uid", "height": "height"}})
assert first.source_sop_instance_uid == "S1" and first.height is None
assert identities.source_image("S2") is second and second.height == 123

links = DatasetGraph()
a, b = links.register(Exam("A")), links.register(Exam("B"))
links.set_linked_accessions(a, ["B"])
a.rekey(accession_number="C")
assert b.linked_exams == (a,)
links.set_linked_accessions(a, [])
assert not b.linked_exams
links.set_linked_accessions(a, ["B"])
destination = DatasetGraph()
destination.register(b)
assert destination.unresolved_references and not b.linked_exams
c = destination.register(Exam("C"))
assert c.linked_exams == (b,) and b.linked_exams == (c,)

standalone = ResearchPatient("standalone")
standalone.research = {"labels": ["preserved"]}
local_exam = standalone.add_exam(Exam("old"))
local_finding = local_exam.add_finding(Finding("old", Laterality.LEFT, "1"))
local_image = local_exam.add_image(MammogramImage("original", accession_number="old"))
local_roi = local_image.add_roi(RegionOfInterest((0, 0, 10, 10), "original", "0"))
local_exam.rekey(accession_number="new")
local_image.update(image_id="renamed")
assert all(obj.graph is None for obj in (standalone, local_exam, local_finding, local_image, local_roi))
registered = DatasetGraph()
registered.register(standalone)
assert registered.finding("new", "1") is local_finding
assert registered.roi("renamed", "0") is local_roi
assert not registered.unresolved_references
assert standalone.research == {"labels": ["preserved"]}
metadata = distribution("embed-data-model")
assert metadata.metadata["Name"] == "embed-data-model"
assert metadata.metadata["License-Expression"] == "MIT"
assert metadata.version == embed_data_model.__version__
assert "site-packages" in Path(embed_data_model.__file__).as_posix()
"""
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [str(python), "-c", code],
        cwd=tmp_path,
        env=clean_environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
