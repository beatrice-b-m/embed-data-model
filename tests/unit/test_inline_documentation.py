"""Check documented entry points without promoting implementation helpers."""
from __future__ import annotations

import doctest
from enum import Enum
import importlib
import inspect
import pydoc
from pathlib import Path

import pytest

import embed_data_model


# Public domain types and returned records; helper functions without an explicit
# entry below remain implementation details even if they lack a leading '_'.
DOMAIN_MODULES = (
    "clinical.associations", "clinical.attributes", "clinical.exams",
    "clinical.findings", "clinical.histories", "clinical.interpretations",
    "clinical.pathology", "clinical.patients", "clinical.procedures",
    "core.anatomy", "core.birads", "core.primitives", "core.provenance",
    "core.source", "core.tables", "core.validation", "core.selection",
    "core.graph", "imaging.images", "imaging.landmarks", "imaging.rois",
    "sources.embed.loader", "sources.embed.magview",
)
FUNCTIONS = {
    "core.source": ("canonicalize_source_key", "is_null_scalar"),
    "core.tables": ("iter_records",),
    "core.validation": ("validate",),
    "core.selection": ("select", "partition"),
    "clinical.attributes": ("select_patient_attribute_as_of",),
    "core.birads": ("normalize_mass_shape", "normalize_mass_margin",
                    "normalize_calc_morphology", "normalize_asymmetry_type"),
    "sources.embed.loader": ("load_embed",),
    "sources.embed.columns": ("resolve_columns",),
    "sources.embed.magview": ("normalize_magview_location",),
    "sources.embed.histories": ("normalize_medication_history", "normalize_procedure_history"),
    "sources.embed.procedures_pathology": ("normalize_procedure", "normalize_pathology"),
}


@pytest.mark.parametrize("name", DOMAIN_MODULES)
def test_public_class_and_member_documentation(name: str) -> None:
    module = importlib.import_module("embed_data_model." + name)
    for class_name, cls in inspect.getmembers(module, inspect.isclass):
        if class_name.startswith("_") or cls.__module__ != module.__name__:
            continue
        assert cls.__doc__, f"{module.__name__}.{class_name}"
        for member_name, member in vars(cls).items():
            if member_name.startswith("_"):
                continue
            if isinstance(member, (staticmethod, classmethod)):
                member = member.__func__
            if isinstance(member, property) or inspect.isfunction(member):
                assert inspect.getdoc(member), f"{class_name}.{member_name}"
        # All constructible fields need class-level hover/help text, including
        # the parameters of dataclass-generated constructors.
        if issubclass(cls, Enum):
            continue
        for parameter in inspect.signature(cls).parameters.values():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            assert parameter.name in cls.__doc__, f"{class_name}.{parameter.name}"


@pytest.mark.parametrize("name", FUNCTIONS)
def test_supported_function_docstrings(name: str) -> None:
    module = importlib.import_module("embed_data_model." + name)
    for entry in FUNCTIONS[name]:
        function = getattr(module, entry)
        assert inspect.getdoc(function), f"{name}.{entry}"
        assert inspect.signature(function).return_annotation is not inspect.Signature.empty


def test_root_exports_reach_documented_objects() -> None:
    for name in embed_data_model.__all__:
        assert inspect.getdoc(getattr(embed_data_model, name)), name
    from embed_data_model.sources.embed import load_embed
    assert load_embed is embed_data_model.load_embed
    assert "retain_raw" in pydoc.render_doc(load_embed)
    assert "exclusive" in pydoc.render_doc(embed_data_model.RegionOfInterest.from_embed_coordinates)


@pytest.mark.parametrize("name", ("", *DOMAIN_MODULES))
def test_inline_examples(name: str) -> None:
    module = importlib.import_module("embed_data_model" + ("." + name if name else ""))
    result = doctest.testmod(module, optionflags=doctest.ELLIPSIS)
    assert result.failed == 0


def test_source_typing_marker() -> None:
    assert Path(embed_data_model.__file__).with_name("py.typed").is_file()


def test_forwarded_constructor_keywords_preserve_behavior() -> None:
    from embed_data_model import Pathology, RegionOfInterest

    assert Pathology(patient_id="P", record_id="R").identity == ("P", "R")
    assert Pathology("explicit", patient_id="P", record_id="R").identity == "explicit"
    with pytest.raises(TypeError):
        Pathology(patient_id="P")

    class ResearchROI(RegionOfInterest):
        def __init__(self, *args: object, label: str, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)
            self.label = label

    roi = ResearchROI.from_embed_coordinates((0, 0, 4, 4), image_id="I", roi_key="0", label="manual")
    assert isinstance(roi, ResearchROI) and roi.label == "manual"
    assert roi.coordinates == (0, 0, 5, 5)
    roi.metadata["nested"] = []
    scaled = roi.resize(scale_y=2, scale_x=2)
    assert scaled.metadata is roi.metadata and scaled.graph is None
    assert scaled.source_coordinates == roi.source_coordinates
