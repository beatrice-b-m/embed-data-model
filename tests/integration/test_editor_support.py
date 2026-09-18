"""Optional editor-engine checks; install Jedi to exercise without a GUI editor."""
from __future__ import annotations

from pathlib import Path

import pytest

jedi = pytest.importorskip("jedi", reason="Optional editor-engine qualification needs Jedi")


def test_editor_signatures_hovers_completion_and_navigation(tmp_path: Path) -> None:
    jedi.settings.cache_directory = str(tmp_path / "jedi-cache")
    root = Path(__file__).resolve().parents[2]
    project = jedi.Project(str(root), added_sys_path=[str(root / "src")], smart_sys_path=False)

    def script(code: str):
        return jedi.Script(code, project=project)

    loader = script("from embed_data_model import load_embed\nload_embed(")
    signature = loader.get_signatures()[0]
    assert {"mode", "columns", "source_keys", "into"} <= {p.name for p in signature.params}
    assert "refresh" in signature.to_string() and "merge" in signature.to_string()
    assert "materialized" in signature.docstring()

    roi = script("from embed_data_model import RegionOfInterest\nRegionOfInterest.from_embed_coordinates(")
    assert any({"image_id", "roi_key", "confidence"} <= {p.name for p in sig.params}
               for sig in roi.get_signatures())
    assert "exclusive" in roi.get_signatures()[0].docstring()

    pathology = script("from embed_data_model import Pathology\nPathology(")
    assert {"patient_id", "record_id"} <= {p.name for p in pathology.get_signatures()[0].params}

    code = 'from embed_data_model import DatasetGraph\nexam = DatasetGraph().exam("A")\nexam'
    assert any(value.full_name == "embed_data_model.clinical.exams.Exam"
               for value in script(code).infer())
    assert {"description", "findings", "images", "patient_id"} <= {
        value.name for value in script(code + ".").complete()
    }
    result = script('from embed_data_model import load_embed\nreport = load_embed()\nreport.graph')
    assert any(value.full_name == "embed_data_model.core.graph.DatasetGraph"
               for value in result.infer())
