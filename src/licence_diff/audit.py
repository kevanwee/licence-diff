"""Local evidence packages, deterministic fingerprints and review overlays."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool, model_validator

from . import __version__


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(
        Path(path).read_bytes().decode("utf-8-sig"),
        object_pairs_hook=_pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"Non-finite JSON number: {value}")
        ),
    )


def save_json(path, value):
    Path(path).write_bytes(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"
    )


def finding(
    rule,
    entity,
    title,
    *,
    before=None,
    after=None,
    evidence=(),
    severity="warning",
    classification="observed",
    explanation="",
):
    identity = digest(canonical([rule, entity]))[:16]
    return {
        "id": identity,
        "rule": rule,
        "entity": entity,
        "title": title,
        "severity": severity,
        "classification": classification,
        "before": before,
        "after": after,
        "evidence": list(evidence),
        "explanation": explanation,
    }


def evidence_text(source, text, quote, locator):
    if not quote or text.count(quote) != 1:
        raise ValueError("Evidence quote must identify exactly one source span")
    start = text.index(quote)
    return {
        "source": source,
        "start": start,
        "end": start + len(quote),
        "quote": quote,
        "locator": locator,
    }


def check_span(ref, text):
    if (
        not isinstance(ref.get("start"), int)
        or isinstance(ref["start"], bool)
        or not isinstance(ref.get("end"), int)
        or isinstance(ref["end"], bool)
        or ref["start"] < 0
        or ref["end"] <= ref["start"]
        or ref["end"] > len(text)
        or text[ref["start"] : ref["end"]] != ref.get("quote")
    ):
        raise ValueError("Evidence span does not match the saved source")


def publish(output, writer):
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / f".{output.name}.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        if output.exists():
            raise ValueError("Output exists; choose a new version directory")
        with tempfile.TemporaryDirectory(dir=output.parent, prefix=".prepare-") as tmp:
            stage = Path(tmp) / "output"
            stage.mkdir()
            writer(stage)
            if output.exists():
                raise ValueError("Output appeared during publication")
            stage.rename(output)
    finally:
        lock.unlink()


def _safe_name(name):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
        raise ValueError("Invalid snapshot filename")
    return name


def bundle(output, report, snapshots, exports=None):
    report = {
        "schema_version": "1",
        "engine_version": __version__,
        "review_status": "unreviewed",
        **report,
    }
    report["findings"] = sorted(
        report["findings"],
        key=lambda row: (
            {"error": 0, "warning": 1, "info": 2}[row["severity"]],
            1 if row["classification"] in {"judgment", "assumption"} else 0,
            row["rule"],
            row["entity"],
        ),
    )
    report["sources"] = [
        {"file": name, "sha256": digest(raw)} for name, raw in sorted(snapshots.items())
    ]
    reserved = {
        "report.json",
        "bundle.json",
        "review.html",
        "report.html",
        "decisions.json",
        "receipt.json",
    }
    if (
        set(snapshots) & reserved
        or set(exports or {}) & reserved
        or set(snapshots) & set(exports or {})
    ):
        raise ValueError("Snapshot/export names overlap or use a reserved artifact name")
    data = {"report.json": canonical(report) + b"\n", **snapshots, **(exports or {})}
    for name in data:
        _safe_name(name)
    body = {
        "tool": report["tool"],
        "version": __version__,
        "files": {name: digest(raw) for name, raw in sorted(data.items())},
    }
    fingerprint = digest(canonical(body))
    record = {"digest": fingerprint, "body": body}

    def write(stage):
        for name, raw in data.items():
            (stage / name).write_bytes(raw)
        save_json(stage / "bundle.json", record)
        (stage / "review.html").write_bytes(render(report, fingerprint).encode("utf-8"))

    publish(output, write)
    return record


def verify(directory):
    directory = Path(directory)
    if not (directory / "bundle.json").exists() and (directory / "receipt.json").exists():
        receipt = read_json(directory / "receipt.json")
        body = {key: value for key, value in receipt.items() if key != "digest"}
        if digest(canonical(body)) != receipt["digest"]:
            raise ValueError("Reviewed receipt changed")
        for name, expected in body["files"].items():
            _safe_name(name)
            if digest((directory / name).read_bytes()) != expected:
                raise ValueError(f"Reviewed file changed: {name}")
        report = read_json(directory / "report.json")
        if (directory / "report.html").read_bytes() != render(
            report, body["source_package_digest"]
        ).encode("utf-8"):
            raise ValueError("Reviewed presentation changed")
        return receipt, report
    record = read_json(directory / "bundle.json")
    if (
        record["body"]["version"] != __version__
        or digest(canonical(record["body"])) != record["digest"]
    ):
        raise ValueError("Package fingerprint changed or engine is unsupported")
    for name, expected in record["body"]["files"].items():
        _safe_name(name)
        if digest((directory / name).read_bytes()) != expected:
            raise ValueError(f"Frozen file changed: {name}")
    report = read_json(directory / "report.json")
    if (directory / "review.html").read_bytes() != render(report, record["digest"]).encode("utf-8"):
        raise ValueError("Review presentation changed")
    return record, report


class FindingDecision(Strict):
    disposition: Literal["confirmed", "dismissed", "corrected", "needs-information"]
    note: str = Field(min_length=8, pattern=r"\S")
    correction: str | None = None

    @model_validator(mode="after")
    def correction_needed(self):
        if self.disposition == "corrected" and not (self.correction or "").strip():
            raise ValueError("A corrected finding needs its replacement assessment")
        return self


class Decisions(Strict):
    schema_version: Literal["1"] = "1"
    package_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: str = Field(min_length=1, pattern=r"\S")
    basis: str = Field(min_length=8, pattern=r"\S")
    reviewed_at: AwareDatetime
    synthetic: StrictBool
    findings: dict[str, FindingDecision]


def finalize(directory, decision_path, output):
    directory = Path(directory)
    if not (directory / "bundle.json").is_file():
        raise ValueError("Finalize an original analysis package, not an already reviewed export")
    record, report = verify(directory)
    decisions = Decisions.model_validate(read_json(decision_path))
    if decisions.package_digest != record["digest"]:
        raise ValueError("Decision belongs to another package")
    if decisions.synthetic != report["synthetic"]:
        raise ValueError("Synthetic status differs from the source matter")
    if set(decisions.findings) != {r["id"] for r in report["findings"]}:
        raise ValueError("Review exactly every finding; unknown or missing identifiers are refused")
    reviewed = json.loads(canonical(report))
    reviewed["review_status"] = (
        "needs-information"
        if any(d.disposition == "needs-information" for d in decisions.findings.values())
        else "review-complete"
    )
    reviewed["review"] = decisions.model_dump(mode="json")
    reviewed["original_package_digest"] = record["digest"]
    for row in reviewed["findings"]:
        row["review"] = decisions.findings[row["id"]].model_dump(mode="json")

    def write(stage):
        for name in record["body"]["files"]:
            if name not in {"report.json", "report.md", "findings.sarif"}:
                (stage / name).write_bytes((directory / name).read_bytes())
        save_json(stage / "report.json", reviewed)
        (stage / "report.md").write_bytes(markdown(reviewed).encode("utf-8"))
        save_json(stage / "findings.sarif", sarif(reviewed))
        save_json(stage / "decisions.json", decisions.model_dump(mode="json"))
        (stage / "report.html").write_bytes(render(reviewed, record["digest"]).encode("utf-8"))
        receipt = {
            "schema_version": "1",
            "source_package_digest": record["digest"],
            "review_status": reviewed["review_status"],
            "files": {p.name: digest(p.read_bytes()) for p in sorted(stage.iterdir())},
            "authority": "Supplied attestation; identity and legal authority are not authenticated",
        }
        save_json(stage / "receipt.json", {**receipt, "digest": digest(canonical(receipt))})

    publish(output, write)
    return reviewed["review_status"]


def markdown(report):
    rows = [
        f"# {report['title']}",
        "",
        f"Review status: {report['review_status']}",
        "",
        report["boundary"],
        "",
        "| Finding | Classification | Severity | Review |",
        "| --- | --- | --- | --- |",
    ]
    rows.extend(
        f"| {r['title'].replace('|', '/')} | {r['classification']} | {r['severity']} | {r.get('review', {}).get('disposition', 'unreviewed')} |"
        for r in report["findings"]
    )
    return "\n".join(rows) + "\n"


def sarif(report):
    rules = sorted({r["rule"] for r in report["findings"]})
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": report["tool"],
                        "version": __version__,
                        "rules": [{"id": rule} for rule in rules],
                    }
                },
                "results": [
                    {
                        "ruleId": row["rule"],
                        "level": {"error": "error", "warning": "warning", "info": "note"}[
                            row["severity"]
                        ],
                        "message": {"text": row["title"]},
                        "partialFingerprints": {"findingId": row["id"]},
                        "properties": {
                            "reviewStatus": report["review_status"],
                            "assessment": row.get("review"),
                            "evidence": row["evidence"],
                        },
                    }
                    for row in report["findings"]
                ],
            }
        ],
    }


def _esc(value):
    return html.escape(str(value))


def render(report, fingerprint):
    package = __package__
    head = files(package).joinpath("assets/head.html").read_text(encoding="utf-8")
    script = files(package).joinpath("assets/review.js").read_text(encoding="utf-8")
    result = [
        head,
        f"<header><h1>{_esc(report['title'])}</h1><p>{_esc(report['summary'])}</p>",
        f"<p>Review status: <strong>{_esc(report['review_status'])}</strong> · {len(report['findings'])} findings</p>",
    ]
    if report["synthetic"]:
        result.append(
            '<p class="notice">Synthetic example — inputs and any sample decisions are fictional.</p>'
        )
    result.extend([f"<p class='boundary'>{_esc(report['boundary'])}</p></header><main>"])
    if report.get("plan_preview"):
        result.append(
            '<section><h2>Annotated premises plan</h2><img class="plan" alt="Supplied premises geometry with labelled discrepancies" src="'
            + report["plan_preview"]
            + '"></section>'
        )
    result.append(
        '<section><h2>Findings</h2><label class="filter">Filter findings<input id="filter" type="search" placeholder="Search title, rule or entity"></label>'
    )
    if not report["findings"]:
        result.append(
            "<p>No differences found under this configuration. This does not establish legal adequacy.</p>"
        )
    for row in report["findings"]:
        result.append(
            f'<article data-finding="{row["id"]}"><h3>{_esc(row["title"])}</h3>'
            f'<p class="meta">{_esc(row["rule"])} · {_esc(row["entity"])} · '
            f"{_esc(row['classification'])} · {_esc(row['severity'])}</p>"
            f'<p>{_esc(row["explanation"])}</p><div class="comparison">'
        )
        for name in ("before", "after"):
            result.append(
                f"<div><h4>{name.capitalize()}</h4><pre>{_esc(json.dumps(row[name], ensure_ascii=False, indent=2, sort_keys=True))}</pre></div>"
            )
        result.append("</div><details><summary>Inspect source evidence</summary>")
        for ref in row["evidence"]:
            result.append(
                f"<p><strong>{_esc(ref.get('source', 'input'))}</strong> · {_esc(ref.get('locator', ref.get('pointer', '')))}</p>"
            )
            if "quote" in ref:
                result.append(
                    f"<blockquote>{_esc(ref['quote'])}</blockquote><small>Characters {ref['start']}–{ref['end']}</small>"
                )
        result.append("</details>")
        if "review" in row:
            result.append(
                f"<h4>Reviewer assessment: {_esc(row['review']['disposition'])}</h4><p>{_esc(row['review']['note'])}</p>"
            )
            if row["review"]["correction"]:
                result.append(f"<p>Correction: {_esc(row['review']['correction'])}</p>")
        else:
            result.append(
                '<label>Assessment<select data-disposition><option value="">Not reviewed</option><option value="confirmed">Confirm</option><option value="dismissed">Dismiss</option><option value="corrected">Correct assessment</option><option value="needs-information">Need information</option></select></label><label>Review note<textarea data-note rows="2" placeholder="Explain your assessment; at least eight characters."></textarea></label><label>Correction, if applicable<input data-correction placeholder="Your corrected assessment; original evidence stays intact."></label>'
            )
        result.append("</article>")
    result.append(
        "</section><section><h2>Sources and configuration</h2><details><summary>Inspect saved configuration, input hashes and assumptions</summary><pre>"
        + _esc(
            json.dumps(
                {
                    k: report.get(k)
                    for k in ("sources", "configuration", "assumptions", "coverage", "review")
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        + "</pre></details></section>"
    )
    if report["review_status"] == "unreviewed":
        result.append(
            '<section><h2>Record the review</h2><p>Correct assessments here. To correct source facts, edit the input and create a new analysis; earlier decisions will not apply.</p><form id="review"><label>Your name and role<input id="actor" required></label><label>Review basis and authority<textarea id="basis" required minlength="8" rows="3"></textarea></label><button type="submit">Download review decisions</button><p id="status" role="status">Review every finding, then run the finalize command with the downloaded file.</p></form></section>'
        )
    result.append(
        f"<footer>Package fingerprint <code>{fingerprint}</code><p>A completed review is not a legal opinion, compliance certification or proof of external action.</p></footer></main>"
    )
    data = json.dumps({"digest": fingerprint, "synthetic": report["synthetic"]}).replace(
        "<", "\\u003c"
    )
    result.append("<script>const packageInfo=" + data + ";" + script + "</script>")
    return "".join(result) + "</body></html>"
