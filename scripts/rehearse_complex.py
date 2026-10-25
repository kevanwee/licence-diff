"""Synthetic-only end-to-end stress rehearsal. No real sign-off is simulated."""
import argparse
import importlib
import json
from pathlib import Path


def run(config_path, output):
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / config_path).read_text(encoding="utf-8"))
    cli = importlib.import_module(config["package"] + ".cli")
    audit = importlib.import_module(config["package"] + ".audit")
    summary = {}

    def write(stage):
        if cli.main([*config["args"], "--out", str(stage / "analysis")]) != 0:
            raise ValueError("Complex analysis failed")
        record, report = audit.verify(stage / "analysis")
        if not report["synthetic"]:
            raise ValueError("This rehearsal refuses real matter data")
        decisions = {"schema_version": "1", "package_digest": record["digest"],
                     "actor": "SYNTHETIC responsible reviewer",
                     "basis": "SYNTHETIC review: unverified interpretations and missing evidence remain pending",
                     "reviewed_at": "2026-10-25T12:00:00+08:00", "synthetic": True,
                     "findings": {}}
        for row in report["findings"]:
            pending = row["rule"] in config["pending_rules"]
            decisions["findings"][row["id"]] = {
                "disposition": "needs-information" if pending else "confirmed",
                "note": "SYNTHETIC: obtain missing evidence or resolve interpretation" if pending
                        else "SYNTHETIC: comparison/calculation inspected; no legal clearance inferred",
                "correction": None}
        audit.save_json(stage / "decisions.json", decisions)
        status = audit.finalize(stage / "analysis", stage / "decisions.json", stage / "reviewed")
        audit.verify(stage / "reviewed")
        summary.update(synthetic=True, matter=report["title"], findings=len(report["findings"]),
                       review_status=status, pending=sum(d["disposition"] == "needs-information"
                           for d in decisions["findings"].values()),
                       original_package_digest=record["digest"],
                       external_actions="none", legal_adequacy="not established")
        audit.save_json(stage / "rehearsal.json", summary)

    audit.publish(output, write)
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run("scripts/complex-scenario.json", args.out)))
