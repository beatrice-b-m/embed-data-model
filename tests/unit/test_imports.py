from __future__ import annotations

import ast
import importlib
import importlib.abc
import importlib.metadata
import pkgutil
import sys
from contextlib import contextmanager
from collections.abc import Iterator
from types import ModuleType
from pathlib import Path
from typing import Optional


PUBLIC_NAMESPACE_MODULES = [
    "embed_data_model.clinical",
    "embed_data_model.core",
    "embed_data_model.imaging",
    "embed_data_model.sources.embed",
]

LEGACY_IMPORT_PREFIXES = (
    "embed_toolkit",
    "quadrant_matching",
    "hiti_preproc",
    "quadrants",
    "embed_data_model.elements",
    "embed_data_model.structure",
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
    package_root = src_path / "embed_data_model"
    for module_info in pkgutil.walk_packages(
        [str(package_root)], prefix="embed_data_model."
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
        package = importlib.import_module("embed_data_model")
        assert package.__version__ == importlib.metadata.version(
            "embed-data-model"
        )
        assert Path(package.__file__).resolve().is_relative_to(src_path)


def test_package_root_exports_only_the_researcher_facade() -> None:
    with new_src_imports():
        package = importlib.import_module("embed_data_model")

    assert set(package.__all__) == {
        "DatasetGraph",
        "load_embed",
        "LoadReport",
        "Issue",
        "SourceRef",
        "Patient",
        "Exam",
        "BreastSide",
        "Finding",
        "MammogramImage",
        "RegionOfInterest",
        "Box",
        "Procedure", "ProcedureIdentity", "Pathology", "CancerRegistryEntry",
        "Laterality", "ImageModality", "ViewPosition", "ValidationResult", "validate",
    }


def test_public_namespace_packages_import() -> None:
    with new_src_imports():
        for module in PUBLIC_NAMESPACE_MODULES:
            importlib.import_module(module)


def test_public_namespace_imports_stay_inside_new_src_tree() -> None:
    with new_src_imports() as src_path:
        loaded = [
            importlib.import_module(module)
            for module in ["embed_data_model", *PUBLIC_NAMESPACE_MODULES]
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

    for source_file in sorted((src_path / "embed_data_model").rglob("*.py")):
        for target in import_targets(source_file):
            if target in LEGACY_IMPORT_PREFIXES or any(
                target.startswith(f"{prefix}.") for prefix in LEGACY_IMPORT_PREFIXES
            ):
                violations.append(f"{source_file.relative_to(project_root)}: {target}")

    assert violations == []


def test_all_unified_modules_import_without_legacy_runtime_dependencies() -> None:
    with new_src_imports() as src_path:
        with temporarily_unloaded(("embed_data_model", *LEGACY_IMPORT_PREFIXES)):
            with block_legacy_imports():
                module_names = ["embed_data_model", *iter_unified_source_modules(src_path)]

                for module_name in module_names:
                    importlib.import_module(module_name)

                loaded_unified_modules = {
                    name: module
                    for name, module in sys.modules.items()
                    if name == "embed_data_model" or name.startswith("embed_data_model.")
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


def test_specialist_symbols_are_available_from_focused_modules() -> None:
    with new_src_imports():
        package = importlib.import_module("embed_data_model")
        attributes = importlib.import_module("embed_data_model.clinical.attributes")
        findings = importlib.import_module("embed_data_model.clinical.findings")
        histories = importlib.import_module("embed_data_model.clinical.histories")
        pathology = importlib.import_module("embed_data_model.clinical.pathology")
        birads = importlib.import_module("embed_data_model.core.birads")
        primitives = importlib.import_module("embed_data_model.core.primitives")
        provenance = importlib.import_module("embed_data_model.core.provenance")
        images = importlib.import_module("embed_data_model.imaging.images")
        rois = importlib.import_module("embed_data_model.imaging.rois")


    assert package.DatasetGraph
    assert package.load_embed
    assert findings.Finding
    assert findings.FindingNormalizationEvidence
    assert histories.HistoryTimeEstimate
    assert histories.MedicationHistoryObservation
    assert pathology.PathologyObservation
    assert pathology.PathologyDiagnosis
    assert attributes.ExamAttributeObservation
    assert attributes.PatientAttributeObservation
    assert birads.MassShape.LOBULATED.value == "lobulated"
    assert images.MammogramImage
    assert provenance.SourceRef if hasattr(provenance, "SourceRef") else provenance.SourceLocator
    assert primitives.Laterality.LEFT.value == "L"
    assert rois.RegionOfInterest((0, 0, 1, 1), image_id="IMG-1", roi_key="0").area == 1
