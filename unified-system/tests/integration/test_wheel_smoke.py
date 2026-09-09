from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


def test_built_wheel_imports_and_loads_outside_source_tree(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    build_root = tmp_path / "project"
    shutil.copytree(project_root, build_root, ignore=shutil.ignore_patterns(".venv"))
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
from pathlib import Path
from embed_toolkit import (
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
assert "site-packages" in Path(__import__("embed_toolkit").__file__).as_posix()
"""
    clean_environment = os.environ.copy()
    clean_environment.pop("PYTHONPATH", None)
    subprocess.run(
        [str(python), "-c", code],
        cwd=tmp_path,
        env=clean_environment,
        check=True,
        capture_output=True,
        text=True,
    )
