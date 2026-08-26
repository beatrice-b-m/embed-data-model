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
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)],
        cwd=build_root,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(wheel_dir.glob("*.whl"))

    environment = tmp_path / "environment"
    venv.EnvBuilder(with_pip=True).create(environment)
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
from embed_toolkit import DatasetGraph, load_embed

report = load_embed(
    patients=[{"empi_anon": "P-1"}],
    exams=[{"acc_anon": "A-1", "empi_anon": "P-1"}],
    source_scope="wheel-smoke",
    identity_namespace="test-release",
)
assert report.graph.patient("P-1").exams == [report.graph.exam("A-1")]
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
