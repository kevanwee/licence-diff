import json
from pathlib import Path

import pytest

from licence_diff.audit import bundle, finalize, read_json, verify
from licence_diff.cli import main

ROOT = Path(__file__).parents[1]


@pytest.fixture
def package(tmp_path):
    args = [
        "compare",
        str(ROOT / "examples/campaign-licence/before.txt"),
        str(ROOT / "examples/campaign-licence/after.txt"),
        "--matter",
        "Campaign illustrations",
        "--synthetic",
    ]
    directory = tmp_path / "analysis"
    assert main([*args, "--out", str(directory)]) == 0
    return directory


def decisions(package, tmp_path, disposition="confirmed"):
    record, report = verify(package)
    value = {
        "schema_version": "1",
        "package_digest": record["digest"],
        "actor": "SYNTHETIC responsible reviewer",
        "basis": "SYNTHETIC inspection of every source and finding",
        "reviewed_at": "2026-10-25T12:00:00+08:00",
        "synthetic": True,
        "findings": {
            r["id"]: {
                "disposition": disposition,
                "note": "SYNTHETIC review assessment",
                "correction": "Synthetic corrected assessment"
                if disposition == "corrected"
                else None,
            }
            for r in report["findings"]
        },
    }
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_documented_end_to_end(package, tmp_path):
    path = decisions(package, tmp_path, "corrected")
    output = tmp_path / "reviewed"
    assert main(["finalize", str(package), "--decisions", str(path), "--out", str(output)]) == 0
    original = read_json(package / "report.json")
    report = read_json(output / "report.json")
    assert original["review_status"] == "unreviewed"
    assert report["review_status"] == "review-complete"
    assert len(report["findings"]) == len(original["findings"])
    assert all(r["review"]["correction"] for r in report["findings"])
    assert report["sources"] == original["sources"]
    assert "review-complete" in (output / "report.md").read_text()
    assert all(
        r["properties"]["reviewStatus"] == "review-complete"
        for r in read_json(output / "findings.sarif")["runs"][0]["results"]
    )
    assert main(["verify", str(package)]) == 0


def test_pending_questions_stay_pending(package, tmp_path):
    status = finalize(
        package, decisions(package, tmp_path, "needs-information"), tmp_path / "reviewed"
    )
    assert status == "needs-information"


@pytest.mark.parametrize("file", ["report.json", "review.html", "bundle.json"])
def test_package_tampering_fails(package, tmp_path, file):
    path = decisions(package, tmp_path)
    target = package / file
    if file == "bundle.json":
        value = read_json(target)
        value["body"]["tool"] = "other"
        target.write_text(json.dumps(value), encoding="utf-8")
    else:
        with target.open("ab") as stream:
            stream.write(b" ")
    with pytest.raises(ValueError):
        finalize(package, path, tmp_path / "reviewed")
    assert not (tmp_path / "reviewed").exists()


@pytest.mark.parametrize(
    "change", ["digest", "missing", "extra", "synthetic", "blank", "correction"]
)
def test_invalid_decisions_fail(package, tmp_path, change):
    path = decisions(package, tmp_path)
    value = read_json(path)
    if change == "digest":
        value["package_digest"] = "0" * 64
    elif change == "missing":
        value["findings"].pop(next(iter(value["findings"])))
    elif change == "extra":
        value["findings"]["unknown"] = next(iter(value["findings"].values()))
    elif change == "synthetic":
        value["synthetic"] = False
    elif change == "blank":
        value["actor"] = " "
    else:
        entry = next(iter(value["findings"].values()))
        entry.update(disposition="corrected", correction=None)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError):
        finalize(package, path, tmp_path / "reviewed")


def test_output_collision_preserves_original(package, tmp_path):
    path = decisions(package, tmp_path)
    output = tmp_path / "reviewed"
    finalize(package, path, output)
    original = (output / "report.json").read_bytes()
    with pytest.raises(ValueError, match="exists"):
        finalize(package, path, output)
    assert original == (output / "report.json").read_bytes()


def test_frozen_source_tampering_fails(package):
    record, _ = verify(package)
    filename = next(
        name
        for name in record["body"]["files"]
        if name not in {"report.json", "report.md", "findings.sarif"}
    )
    with (package / filename).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="Frozen file"):
        verify(package)


def test_duplicate_and_nonfinite_json_refused(tmp_path):
    path = tmp_path / "invalid.json"
    for text in ('{"a":1,"a":2}', '{"value":NaN}'):
        path.write_text(text)
        with pytest.raises(ValueError):
            read_json(path)


def test_source_content_is_escaped(package, tmp_path):
    _, report = verify(package)
    report["title"] = "<script>globalThis.injected=true</script>"
    target = tmp_path / "escape"
    bundle(target, report, {"source.txt": b"safe source"})
    text = (target / "review.html").read_text(encoding="utf-8")
    assert "<script>globalThis.injected" not in text
    assert "&lt;script&gt;globalThis.injected" in text


def test_unknown_schema_and_commands_fail(capsys):
    assert main(["schema", "missing"]) == 2
    assert "Unknown schema" in capsys.readouterr().err


def test_schemas_match_committed_files():
    from licence_diff.commands import schemas

    for name, model in schemas().items():
        assert read_json(ROOT / "schema" / f"{name}.schema.json") == model.model_json_schema()


def test_reviewed_export_can_be_verified_and_tampering_detected(package, tmp_path):
    output = tmp_path / "final"
    finalize(package, decisions(package, tmp_path), output)
    verify(output)
    with (output / "report.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="Reviewed file"):
        verify(output)


def test_repeated_analysis_is_deterministic(package, tmp_path):
    first, _ = verify(package)
    args = [
        "compare",
        str(ROOT / "examples/campaign-licence/before.txt"),
        str(ROOT / "examples/campaign-licence/after.txt"),
        "--matter",
        "Campaign illustrations",
        "--synthetic",
    ]
    other = tmp_path / "second"
    assert main([*args, "--out", str(other)]) == 0
    second, _ = verify(other)
    assert first["digest"] == second["digest"]
