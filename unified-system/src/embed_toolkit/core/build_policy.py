"""Strict and audit policies for source-to-domain construction."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from embed_toolkit.core.provenance import (
    BuildIssue,
    IssueSeverity,
    SourceOccurrence,
)


class BuildMode(str, Enum):
    """Supported handling modes for governed build issues."""

    STRICT = "strict"
    AUDIT = "audit"


class BuildPolicyError(ValueError):
    """Raised when strict policy encounters an unsafe build issue."""

    def __init__(self, issue: BuildIssue) -> None:
        self.issue = issue
        super().__init__(f"{issue.code}: {issue.message}")


@dataclass(frozen=True)
class BuildPolicy:
    """Apply consistent strict or audit handling to source evidence."""

    mode: BuildMode = BuildMode.STRICT

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", BuildMode(self.mode))

    def handle_issue(self, issue: BuildIssue) -> BuildIssue:
        """Raise for errors in strict mode; otherwise retain the issue."""

        if self.mode is BuildMode.STRICT and issue.severity is IssueSeverity.ERROR:
            raise BuildPolicyError(issue)
        return issue

    def review(self, occurrence: SourceOccurrence) -> SourceOccurrence:
        """Apply this policy to every issue on a source occurrence."""

        for issue in occurrence.issues:
            self.handle_issue(issue)
        return occurrence

    def to_dict(self) -> Dict[str, Any]:
        """Return the policy configuration in a JSON-ready shape."""

        return {"mode": self.mode.value}
