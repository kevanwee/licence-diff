"""Install only this wheel into a fresh environment and run the synthetic full journey."""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--scenario", default="scripts/browser-scenario.json")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / args.scenario).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="standalone-wheel-") as temporary:
        directory = Path(temporary)
        env = directory / "env"
        subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
        python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

        def command(arguments):
            result = subprocess.run([str(python), *arguments], cwd=directory, text=True,
                                    capture_output=True, encoding="utf-8")
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout

        command(["-m", "pip", "install", str(wheel)])
        other = [name for name in ("data_flow_diff", "licence_diff", "lease_plan_check")
                 if name != config["package"]]
        command(["-c", "import importlib.util; assert all(importlib.util.find_spec(n) is None "
                 f"for n in {other!r})"])
        shutil.copytree(root / "examples", directory / "examples")
        command(["-m", config["package"], *config["args"], "--out", "analysis"])
        report = json.loads((directory / "analysis/report.json").read_bytes())
        record = json.loads((directory / "analysis/bundle.json").read_bytes())
        decision = {"schema_version": "1", "package_digest": record["digest"],
                    "actor": "SYNTHETIC wheel-test reviewer", "basis": "SYNTHETIC full-journey verification",
                    "reviewed_at": "2026-10-25T12:00:00+08:00", "synthetic": True,
                    "findings": {row["id"]: {"disposition": "needs-information" if row["rule"] in config.get("pending_rules", []) else "confirmed", "note": "SYNTHETIC test decision", "correction": None}
                                 for row in report["findings"]}}
        (directory / "decisions.json").write_text(json.dumps(decision), encoding="utf-8")
        command(["-m", config["package"], "finalize", "analysis", "--decisions", "decisions.json",
                 "--out", "reviewed"])
        command(["-m", config["package"], "verify", "reviewed"])
        assert (directory / "reviewed/report.html").is_file()
        final = json.loads((directory / "reviewed/report.json").read_bytes())
        has_pending = any(row["rule"] in config.get("pending_rules", []) for row in report["findings"])
        assert final["review_status"] == ("needs-information" if has_pending else "review-complete")
        print(json.dumps({"package": config["package"], "wheel_install": "passed",
                          "independent_environment": True, "analysis_review_export": "passed",
                          "synthetic": True, "findings": len(report["findings"]), "scenario": args.scenario}))


if __name__ == "__main__":
    main()
