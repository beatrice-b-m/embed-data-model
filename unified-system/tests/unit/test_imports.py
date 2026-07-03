from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path


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
    modules = [
        "embed_toolkit.adapters",
        "embed_toolkit.audit",
        "embed_toolkit.clinical",
        "embed_toolkit.config",
        "embed_toolkit.core",
        "embed_toolkit.imaging",
        "embed_toolkit.visualization",
        "embed_toolkit.workflows",
    ]

    with new_src_imports():
        for module in modules:
            importlib.import_module(module)
