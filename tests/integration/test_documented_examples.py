"""Keep copyable researcher examples aligned with the public dependency API."""
from __future__ import annotations

from pathlib import Path
import re

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "document",
    ["README.md", "docs/user-guide.md", "docs/downstream-migration.md"],
)
def test_researcher_documentation_examples(document: str) -> None:
    path = PROJECT_ROOT / document
    content = path.read_text()
    blocks = list(re.finditer(r"^```python\n(.*?)^```", content, re.M | re.S))
    assert blocks, f"No executable Python examples found in {document}"
    for block in blocks:
        line = content[:block.start()].count("\n") + 2
        # Each documented example is self-contained. A fresh namespace catches
        # accidental dependencies on another example's imports or live objects.
        code = compile(block.group(1), f"{document}:{line}", "exec")
        exec(code, {"__name__": "__main__"})
