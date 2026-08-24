from __future__ import annotations

import ast
import importlib
import importlib.abc
import pkgutil
import sys
from contextlib import contextmanager
from collections.abc import Iterator
from types import ModuleType
from pathlib import Path
from typing import Optional


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

LEGACY_IMPORT_PREFIXES = (
    "quadrant_matching",
    "hiti_preproc",
    "quadrants",
    "embed_toolkit.elements",
    "embed_toolkit.structure",
)


@contextmanager
def new_src_imports() -> Iterator[Path]:
    project_root = Path(__file__).resolve().parents[2]
    src_path = project_root / "src"
    sys.path.insert(0, str(src_path))

    try:
        yield src_path
    finally:
        sys.path.remove(str(src_path))


@contextmanager
def temporarily_unloaded(prefixes: tuple[str, ...]) -> Iterator[None]:
    saved = {
        name: module
        for name, module in list(sys.modules.items())
        if name in prefixes
        or any(name.startswith(f"{prefix}.") for prefix in prefixes)
    }
    for name in saved:
        sys.modules.pop(name, None)

    try:
        yield
    finally:
        for name in list(sys.modules):
            if name in prefixes or any(
                name.startswith(f"{prefix}.") for prefix in prefixes
            ):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class LegacyImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Optional[object],
        target: Optional[ModuleType] = None,
    ) -> None:
        if fullname in LEGACY_IMPORT_PREFIXES or any(
            fullname.startswith(f"{prefix}.") for prefix in LEGACY_IMPORT_PREFIXES
        ):
            raise AssertionError(f"unexpected legacy import: {fullname}")
        return None


@contextmanager
def block_legacy_imports() -> Iterator[None]:
    blocker = LegacyImportBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        yield
    finally:
        sys.meta_path.remove(blocker)


def iter_unified_source_modules(src_path: Path) -> Iterator[str]:
    package_root = src_path / "embed_toolkit"
    for module_info in pkgutil.walk_packages(
        [str(package_root)], prefix="embed_toolkit."
    ):
        yield module_info.name


def import_targets(source_file: Path) -> Iterator[str]:
    module = ast.parse(source_file.read_text(), filename=str(source_file))
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module


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


def test_unified_source_has_no_legacy_import_targets() -> None:
    project_root = Path(__file__).resolve().parents[2]
    src_path = project_root / "src"
    violations: list[str] = []

    for source_file in sorted((src_path / "embed_toolkit").rglob("*.py")):
        for target in import_targets(source_file):
            if target in LEGACY_IMPORT_PREFIXES or any(
                target.startswith(f"{prefix}.") for prefix in LEGACY_IMPORT_PREFIXES
            ):
                violations.append(f"{source_file.relative_to(project_root)}: {target}")

    assert violations == []


def test_all_unified_modules_import_without_legacy_runtime_dependencies() -> None:
    with new_src_imports() as src_path:
        with temporarily_unloaded(("embed_toolkit", *LEGACY_IMPORT_PREFIXES)):
            with block_legacy_imports():
                module_names = ["embed_toolkit", *iter_unified_source_modules(src_path)]

                for module_name in module_names:
                    importlib.import_module(module_name)

                loaded_unified_modules = {
                    name: module
                    for name, module in sys.modules.items()
                    if name == "embed_toolkit" or name.startswith("embed_toolkit.")
                }
                assert loaded_unified_modules

                for module in loaded_unified_modules.values():
                    module_file = getattr(module, "__file__", None)
                    assert module_file is not None
                    assert Path(module_file).resolve().is_relative_to(src_path)

                assert not any(
                    name in LEGACY_IMPORT_PREFIXES
                    or any(
                        name.startswith(f"{prefix}.")
                        for prefix in LEGACY_IMPORT_PREFIXES
                    )
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
    assert adapters.EmbedImageTables
    assert adapters.project_finding_image_candidates
    assert adapters.normalize_magview_location
    assert audit.WorkflowResult
    assert audit.export_result
    assert clinical.Finding
    assert clinical.FindingNormalizationEvidence
    assert clinical.FindingNormalizationWarning
    assert clinical.ExamAttributeName
    assert clinical.ExamAttributeObservation
    assert clinical.ImagingInterpretation
    assert clinical.PathologyObservation
    assert clinical.PathologyDiagnosis
    assert clinical.PathologyAttributionLink
    assert clinical.PatientAttributeAsOfPolicy
    assert clinical.PatientAttributeName
    assert clinical.PatientAttributeObservation
    assert clinical.PatientAttributeSelection
    assert clinical.PatientObservationTimeBasis
    assert clinical.UndatedObservationPolicy
    assert clinical.select_patient_attribute_as_of
    assert config.EmbedColumnConfig().accession == "acc_anon"
    assert core.MassShape.LOBULATED.value == "lobulated"
    assert imaging.Alignment.reference().is_reference
    assert imaging.MammogramImage
    assert imaging.RegionOfInterest((0, 0, 1, 1)).area == 1
    assert visualization.build_mammogram_render_plan
    assert workflows.FindingLocalizer
    assert workflows.FindingRoiMatcher
    assert workflows.RoiLocalizer
    assert workflows.transfer_roi
    assert workflows.extract_patch
