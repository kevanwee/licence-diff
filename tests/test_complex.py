from pathlib import Path

import pytest

from licence_diff.audit import digest, read_json
from licence_diff.engine import compare, extract

CASE = Path(__file__).parents[1] / "examples/multimedia-licence"


def result():
    raw = [(CASE / name).read_bytes() for name in ("before.txt", "after.txt")]
    records = [
        extract(r.decode("utf-8"), digest(r), matter="Multimedia licensing", synthetic=True)
        for r in raw
    ]
    return compare(*records, *raw)


def test_four_grants_match_independent_delta_ledger():
    report = result()
    expected = read_json(CASE / "expected.json")
    assert report["coverage"]["before_grants"] == report["coverage"]["after_grants"] == 4
    rows = report["findings"]
    for rule, key in [
        ("grant-added", "added"),
        ("grant-removed", "removed"),
        ("rights-delta", "delta_fields"),
    ]:
        assert {r["entity"] for r in rows if r["rule"] == rule} == set(expected[key])
    assert not any(r["entity"].startswith("archive.") and r["rule"] == "rights-delta" for r in rows)
    assert len([r for r in rows if r["rule"] == "interpretation-review"]) == 8


def test_unknown_regions_and_media_do_not_become_unrestricted():
    expected = read_json(CASE / "expected.json")
    rows = result()["findings"]
    assert {r["entity"] for r in rows if r["rule"] == "unknown-rights"} == set(expected["unknowns"])
    for field in ("photos.territories", "photos.media"):
        row = next(r for r in rows if r["entity"] == field and r["rule"] == "rights-delta")
        assert row["after"] is None
        assert "unresolved" in row["title"]


def test_overriding_qualifications_are_preserved_for_human_review():
    expected = read_json(CASE / "expected.json")
    quotes = {
        ref["quote"]
        for row in result()["findings"]
        if row["rule"] == "unclassified-text"
        for ref in row["evidence"]
    }
    assert set(expected["required_qualification_quotes"]) <= quotes
    row = next(r for r in result()["findings"] if r["entity"] == "illustrations.territories")
    assert expected["territory_direction"] in row["title"]


def test_conflicting_grant_field_is_refused():
    raw = (CASE / "after.txt").read_bytes() + b"Exclusive: no\n"
    with pytest.raises(ValueError, match="Duplicate/conflicting"):
        extract(raw.decode("utf-8"), digest(raw), matter="Multimedia licensing", synthetic=True)


def test_complex_rehearsal_keeps_unresolved_questions_pending(tmp_path):
    import importlib.util

    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location("rehearsal", root / "scripts/rehearse_complex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run("scripts/complex-scenario.json", tmp_path / "rehearsal")
    assert result["review_status"] == "needs-information"
    assert result["pending"] > 0
    assert result["external_actions"] == "none"
