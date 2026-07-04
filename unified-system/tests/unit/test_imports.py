from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path


PUBLIC_NAMESPACE_MODULES = [
    "embed_toolkit.adapters",
    "embed_toolkit.audit",
    "embed_toolkit.clinical",
    "embed_toolkit.config",
    "embed_toolkit.core",
    "embed_toolkit.imaging",
    "embed_toolkit.visualization",
    "embed_toolkit.workflows",
]


@contextmanager
def new_src_imports() -> Iterator[Path]:
    project_root = Path(__file__).resolve().parents[2]
    src_path = project_root / "src"
    sys.path.insert(0, str(src_path))

    try:
        yield src_path
    finally:
        sys.path.remove(str(src_path))


def test_imports_new_src_package() -> None:
    with new_src_imports() as src_path:
        package = importlib.import_module("embed_toolkit")
        assert package.__version__ == "0.1.0"
        assert Path(package.__file__).resolve().is_relative_to(src_path)


def test_public_namespace_packages_import() -> None:
    with new_src_imports():
        for module in PUBLIC_NAMESPACE_MODULES:
            importlib.import_module(module)


def test_public_namespace_imports_stay_inside_new_src_tree() -> None:
    with new_src_imports() as src_path:
        loaded = [
            importlib.import_module(module)
            for module in ["embed_toolkit", *PUBLIC_NAMESPACE_MODULES]
        ]

        for module in loaded:
            assert Path(module.__file__).resolve().is_relative_to(src_path)

        assert not any(
            name == "quadrant_matching" or name.startswith("quadrant_matching.")
            for name in sys.modules
        )
        assert not any(
            name == "hiti_preproc" or name.startswith("hiti_preproc.")
            for name in sys.modules
        )


def test_foundation_exports_are_available_from_namespaces() -> None:
    with new_src_imports():
        adapters = importlib.import_module("embed_toolkit.adapters")
        audit = importlib.import_module("embed_toolkit.audit")
        clinical = importlib.import_module("embed_toolkit.clinical")
        config = importlib.import_module("embed_toolkit.config")
        core = importlib.import_module("embed_toolkit.core")
        imaging = importlib.import_module("embed_toolkit.imaging")
        visualization = importlib.import_module("embed_toolkit.visualization")
        workflows = importlib.import_module("embed_toolkit.workflows")

    assert adapters.build_clinical_tables
    assert adapters.normalize_magview_location
    assert audit.WorkflowResult
    assert audit.export_result
    assert clinical.Finding
    assert config.EmbedColumnConfig().accession == "acc_anon"
    assert core.MassShape.LOBULATED.value == "lobulated"
    assert imaging.Alignment.reference().is_reference
    assert imaging.RegionOfInterest((0, 0, 1, 1)).area == 1
    assert visualization.build_mammogram_render_plan
    assert workflows.FindingLocalizer
    assert workflows.FindingRoiMatcher
    assert workflows.RoiLocalizer
    assert workflows.transfer_roi
    assert workflows.extract_patch
