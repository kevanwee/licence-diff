from pathlib import Path

import pytest

from licence_diff.audit import digest
from licence_diff.engine import RightsRegister, compare, extract, validate_register

ROOT = Path(__file__).parents[1] / "examples/campaign-licence"


def registers():
    raw = [(ROOT / name).read_bytes() for name in ("before.txt", "after.txt")]
    records = [extract(r.decode(), digest(r), matter="Campaign", synthetic=True) for r in raw]
    return records, raw


def test_rights_expansion_and_definition_changes():
    records, raw = registers()
    result = compare(*records, *raw)
    changes = {r["entity"]: r for r in result["findings"] if r["rule"] == "rights-delta"}
    assert len(changes) == 8
    assert "expanded" in changes["campaign-art.rights"]["title"]
    assert changes["campaign-art.exclusive"]["before"] is False
    assert changes["campaign-art.exclusive"]["after"] is True
    assert "definitions" in changes["campaign-art.definitions"]["entity"]
    assert "expanded date window" in changes["campaign-art.term"]["title"]
    assert all(r["evidence"] for r in changes.values())


def test_order_is_not_a_substantive_change():
    records, raw = registers()
    changed = raw[0].replace(b"reproduce; distribute", b"distribute; reproduce")
    after = extract(changed.decode(), digest(changed), matter="Campaign", synthetic=True)
    assert not any(
        r["rule"] == "rights-delta" for r in compare(records[0], after, raw[0], changed)["findings"]
    )


def test_unrecognised_clause_is_not_ignored():
    records, raw = registers()
    changed = raw[1] + b"Notwithstanding this schedule, all grants are conditional on approval.\n"
    after = extract(changed.decode(), digest(changed), matter="Campaign", synthetic=True)
    assert any(
        r["rule"] == "unclassified-text"
        for r in compare(records[0], after, raw[0], changed)["findings"]
    )


def test_unknown_is_not_worldwide_or_no_right():
    records, raw = registers()
    changed = raw[1].replace(b"Territories: SG; MY", b"Territories: APAC")
    after = extract(changed.decode(), digest(changed), matter="Campaign", synthetic=True)
    assert after.grants[0].territories is None
    rows = compare(records[0], after, raw[0], changed)["findings"]
    assert any(r["rule"] == "unknown-rights" for r in rows)


@pytest.mark.parametrize("change", ["duplicate", "missing", "term"])
def test_contradictory_and_missing_input_fail(change):
    raw = (ROOT / "before.txt").read_bytes()
    if change == "duplicate":
        raw += b"Exclusive: yes\n"
    elif change == "missing":
        raw = raw.replace(b"Licensor: Illustrator\n", b"")
    else:
        raw = raw.replace(b"2027-01-01 to 2027-12-31", b"2028-01-01 to 2027-12-31")
    with pytest.raises(ValueError):
        extract(raw.decode(), digest(raw), matter="Campaign", synthetic=True)


def test_wrong_source_hash_fails():
    records, raw = registers()
    with pytest.raises(ValueError, match="bytes"):
        validate_register(records[0], raw[0] + b" ")


def test_bad_evidence_and_incomplete_coverage_fail():
    records, raw = registers()
    value = records[0].model_dump(mode="json")
    value["grants"][0]["evidence"]["work"]["start"] += 1
    with pytest.raises(ValueError, match="span"):
        validate_register(RightsRegister.model_validate(value), raw[0])
    value = records[0].model_dump(mode="json")
    value["unclassified"] = []
    with pytest.raises(ValueError, match="coverage"):
        validate_register(RightsRegister.model_validate(value), raw[0])


def test_no_grants_refused():
    with pytest.raises(ValueError, match="No grants"):
        extract("unstructured text", digest(b"unstructured text"), matter="Unknown", synthetic=True)


def test_confirmed_reading_requires_reviewer():
    records, _ = registers()
    raw = records[0].model_dump(mode="json")
    raw["grants"][0]["interpretation"] = "human-confirmed"
    with pytest.raises(ValueError, match="reviewer"):
        RightsRegister.model_validate(raw)
