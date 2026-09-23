"""The importable package: exports, version and runnable docstring examples."""

import doctest
import importlib
from importlib.metadata import version
import pkgutil

import pytest

import embed_data_model


MODULES = sorted(
    module.name
    for module in pkgutil.walk_packages(embed_data_model.__path__, "embed_data_model.")
)


def test_every_root_export_resolves():
    for name in embed_data_model.__all__:
        assert getattr(embed_data_model, name) is not None, name


def test_version_matches_the_distribution():
    assert embed_data_model.__version__ == version("embed-data-model")


@pytest.mark.parametrize("name", ["embed_data_model", *MODULES])
def test_docstring_examples_run(name):
    module = importlib.import_module(name)
    assert doctest.testmod(module, optionflags=doctest.ELLIPSIS).failed == 0
