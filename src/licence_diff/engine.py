"""Evidence-linked rights comparison and a deliberately bounded schedule extractor."""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from .audit import Strict, check_span, finding

RIGHTS = {"reproduce", "distribute", "adapt", "communicate", "perform", "display"}
MEDIA = {"print", "web", "social", "paid-advertising", "broadcast", "internal"}


class Evidence(Strict):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class Term(Strict):
    kind: Literal["fixed", "perpetual", "unknown"]
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "fixed" and (not self.start or not self.end or self.end < self.start):
            raise ValueError("Fixed term needs ordered start/end dates")
        if self.kind != "fixed" and (self.start or self.end):
            raise ValueError("Unknown/perpetual term must not also contain fixed dates")
        return self


class Grant(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,62}$")
    work: str = Field(min_length=1)
    licensor: str = Field(min_length=1)
    licensee: str = Field(min_length=1)
    rights: list[str] | None
    territories: list[str] | None
    media: list[str] | None
    exclusive: StrictBool | None
    sublicensing: StrictBool | None
    term: Term
    restrictions: list[str] | None
    definitions: dict[str, str] = Field(default_factory=dict)
    evidence: dict[str, Evidence]
    interpretation: Literal["proposed", "human-confirmed"] = "proposed"
    reviewer: str | None = None

    @model_validator(mode="after")
    def valid_grant(self):
        for field, allowed in (("rights", RIGHTS), ("media", MEDIA)):
            values = getattr(self, field)
            if values is not None and (len(set(values)) != len(values) or set(values) - allowed):
                raise ValueError(f"Unsupported or duplicate {field}")
        for field in ("territories", "restrictions"):
            values = getattr(self, field)
            if values is not None and (
                len(set(values)) != len(values) or any(not v.strip() for v in values)
            ):
                raise ValueError(f"Duplicate or blank {field}")
        if self.territories is not None and any(
            not re.fullmatch(r"[A-Z]{2}", v) for v in self.territories
        ):
            raise ValueError(
                "Supply explicit two-letter territories; resolve regional shorthand first"
            )
        if self.interpretation == "human-confirmed" and not (self.reviewer or "").strip():
            raise ValueError("Confirmed interpretations require reviewer attribution")
        return self


class RightsRegister(Strict):
    schema_version: Literal["1"] = "1"
    matter: str = Field(min_length=1)
    synthetic: StrictBool = False
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    grants: list[Grant]
    unclassified: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def ids(self):
        ids = [grant.id for grant in self.grants]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate grant IDs")
        if not self.grants:
            raise ValueError(
                "No grants extracted; supply a supported schedule or a reviewed register"
            )
        return self


FIELDS = {
    "Work": "work",
    "Licensor": "licensor",
    "Licensee": "licensee",
    "Rights": "rights",
    "Territories": "territories",
    "Media": "media",
    "Exclusive": "exclusive",
    "Sublicensing": "sublicensing",
    "Term": "term",
    "Restrictions": "restrictions",
}


def extract(text, source_hash, *, matter, synthetic):
    """Recognise labelled licence schedules only. Unrecognised lines remain visible."""
    grants, current, unclassified = [], None, []
    cursor = 0
    for line in text.splitlines(keepends=True):
        content = line.strip()
        start = cursor + len(line) - len(line.lstrip())
        ref = {
            "start": start,
            "end": start + len(content),
            "quote": content,
            "locator": f"line {text[:start].count(chr(10)) + 1}",
        }
        cursor += len(line)
        if not content:
            continue
        match = re.fullmatch(r"Grant: ([a-z][a-z0-9-]{0,62})", content)
        if match:
            current = {"id": match[1], "evidence": {"id": ref}, "definitions": {}}
            grants.append(current)
            continue
        if current is None:
            unclassified.append(ref)
            continue
        if content.startswith("Definition ") and ":" in content:
            key, value = content[len("Definition ") :].split(":", 1)
            if not key.strip() or key in current["definitions"]:
                raise ValueError("Blank/duplicate definition")
            current["definitions"][key] = value.strip()
            current["evidence"]["definition:" + key] = ref
            continue
        key, sep, value = content.partition(":")
        if not sep or key not in FIELDS:
            unclassified.append(ref)
            continue
        field, value = FIELDS[key], value.strip()
        if field in current:
            raise ValueError(f"Duplicate/conflicting {key} in grant {current['id']}")
        current["evidence"][field] = ref
        if field in {"rights", "territories", "media", "restrictions"}:
            if value.lower() == "unknown":
                parsed = None
            elif value.lower() == "none":
                parsed = []
            else:
                parsed = [v.strip() for v in value.split(";")]
            if (
                parsed is not None
                and field in {"rights", "media"}
                and set(parsed) - (RIGHTS if field == "rights" else MEDIA)
            ):
                unclassified.append(ref)
                parsed = None
            if (
                parsed is not None
                and field == "territories"
                and any(not re.fullmatch(r"[A-Z]{2}", v) for v in parsed)
            ):
                unclassified.append(ref)
                parsed = None
        elif field in {"exclusive", "sublicensing"}:
            if value.lower() not in {"yes", "no", "unknown"}:
                unclassified.append(ref)
            parsed = {"yes": True, "no": False}.get(value.lower())
        elif field == "term":
            if value.lower() in {"perpetual", "unknown"}:
                parsed = {"kind": value.lower()}
            elif re.fullmatch(r"\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2}", value):
                a, b = value.split(" to ")
                parsed = {"kind": "fixed", "start": a, "end": b}
            else:
                parsed = {"kind": "unknown"}
                unclassified.append(ref)
        else:
            parsed = value
        current[field] = parsed
    for grant in grants:
        for field in (
            "rights",
            "territories",
            "media",
            "exclusive",
            "sublicensing",
            "restrictions",
        ):
            grant.setdefault(field, None)
        grant.setdefault("term", {"kind": "unknown"})
    return RightsRegister.model_validate(
        {
            "matter": matter,
            "synthetic": synthetic,
            "source_sha256": source_hash,
            "grants": grants,
            "unclassified": unclassified,
        }
    )


def validate_register(register, raw):
    from .audit import digest

    if digest(raw) != register.source_sha256:
        raise ValueError("Rights register refers to different source bytes")
    text = raw.decode("utf-8-sig")
    covered = set()
    for grant in register.grants:
        required = {"id", "work", "licensor", "licensee"}
        required |= {
            field
            for field in FIELDS.values()
            if getattr(grant, field) is not None and field != "term"
        }
        if grant.term.kind != "unknown":
            required.add("term")
        required |= {"definition:" + key for key in grant.definitions}
        if required - grant.evidence.keys():
            raise ValueError(f"Grant {grant.id} lacks evidence for stated values")
        for ref in [*grant.evidence.values()]:
            data = ref.model_dump()
            check_span(data, text)
            covered.update(range(ref.start, ref.end))
    for ref in register.unclassified:
        check_span(ref.model_dump(), text)
        covered.update(range(ref.start, ref.end))
    if any(not c.isspace() and i not in covered for i, c in enumerate(text)):
        raise ValueError("Source text coverage is incomplete; account for every operative line")


def _value(grant, field):
    value = grant.model_dump(mode="json")[field]
    return sorted(value) if isinstance(value, list) else value


def compare(old, new, before_raw, after_raw):
    validate_register(old, before_raw)
    validate_register(new, after_raw)
    if old.matter != new.matter or old.synthetic != new.synthetic:
        raise ValueError("Matter identity and synthetic status must match")
    rows = []
    maps = [{g.id: g for g in register.grants} for register in (old, new)]
    for side, register in (("before", old), ("after", new)):
        for grant in register.grants:
            refs = [{"source": side + ".txt", **r.model_dump()} for r in grant.evidence.values()]
            if grant.interpretation == "proposed":
                rows.append(
                    finding(
                        "interpretation-review",
                        f"{side}.{grant.id}",
                        f"Review the {side} extraction for {grant.id}",
                        after="proposed interpretation",
                        evidence=refs,
                        classification="judgment",
                        explanation="The extractor recognises a bounded schedule grammar; quotations do not prove legal interpretation.",
                    )
                )
            for field in FIELDS.values():
                value = getattr(grant, field)
                if value is None or (field == "term" and value.kind == "unknown"):
                    rows.append(
                        finding(
                            "unknown-rights",
                            f"{side}.{grant.id}.{field}",
                            f"{side} {grant.id}: {field} is unresolved",
                            evidence=refs,
                            classification="assumption",
                            severity="error",
                            explanation="Unknown permission is not treated as unrestricted or absent.",
                        )
                    )
        for i, ref in enumerate(register.unclassified):
            rows.append(
                finding(
                    "unclassified-text",
                    f"{side}.{i}",
                    "Review text outside the supported extraction grammar",
                    after=ref.quote,
                    evidence=[{"source": side + ".txt", **ref.model_dump()}],
                    classification="judgment",
                    explanation="This text could qualify or contradict the recorded rights; it is not silently ignored.",
                )
            )
    fields = sorted(set(FIELDS.values()) | {"definitions"})
    for gid in sorted(maps[0].keys() | maps[1].keys()):
        a, b = maps[0].get(gid), maps[1].get(gid)
        if a is None or b is None:
            grant, side = (b, "after") if a is None else (a, "before")
            rows.append(
                finding(
                    "grant-added" if a is None else "grant-removed",
                    gid,
                    f"{'Added' if a is None else 'Removed'} rights grant: {gid}",
                    before=a.model_dump(mode="json") if a else None,
                    after=b.model_dump(mode="json") if b else None,
                    evidence=[
                        {"source": side + ".txt", **r.model_dump()} for r in grant.evidence.values()
                    ],
                )
            )
            continue
        for field in fields:
            av, bv = _value(a, field), _value(b, field)
            if av == bv:
                continue
            direction = "changed"
            if isinstance(av, list) and isinstance(bv, list):
                direction = (
                    "expanded"
                    if set(av) < set(bv)
                    else "narrowed"
                    if set(bv) < set(av)
                    else "mixed additions and removals"
                )
            if av is None or bv is None:
                direction = "unresolved comparison"
            if field == "term" and av["kind"] == bv["kind"] == "fixed":
                direction = (
                    "expanded date window"
                    if bv["start"] <= av["start"] and bv["end"] >= av["end"]
                    else "narrowed date window"
                    if bv["start"] >= av["start"] and bv["end"] <= av["end"]
                    else "shifted date window"
                )
            refs = []
            for side, grant in (("before", a), ("after", b)):
                for key, ref in grant.evidence.items():
                    if key == field or (field == "definitions" and key.startswith("definition:")):
                        refs.append({"source": side + ".txt", **ref.model_dump()})
            rows.append(
                finding(
                    "rights-delta",
                    f"{gid}.{field}",
                    f"{gid}: {field} — {direction}",
                    before=av,
                    after=bv,
                    evidence=refs,
                    classification="proposed-interpretation",
                    explanation="Comparison of recorded rights. Definitions and restrictions may qualify apparent expansion; lawyer review is required.",
                )
            )
    return {
        "tool": "licence-diff",
        "title": f"Rights delta review — {new.matter}",
        "summary": "Compare recorded contractual permissions, restrictions and definitions",
        "synthetic": new.synthetic,
        "review_status": "unreviewed",
        "findings": rows,
        "configuration": {
            "rights_vocabulary": sorted(RIGHTS),
            "media_vocabulary": sorted(MEDIA),
            "extractor": "labelled-schedule-v1",
        },
        "coverage": {
            "before_grants": len(old.grants),
            "after_grants": len(new.grants),
            "source_character_coverage": "validated; classification remains reviewable",
        },
        "assumptions": [
            "Grant IDs identify the same subject across drafts.",
            "Set comparisons do not resolve the effect of contractual qualifications.",
        ],
        "boundary": "Machine extraction is a proposal. Exact quotations prove provenance, not ownership, enforceability or the legal effect of a grant.",
    }
