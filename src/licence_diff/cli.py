"""Command line boundary; analysis engines remain deterministic and offline."""

import argparse
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

from .audit import bundle, canonical, finalize, markdown, sarif, verify


def setup(parser):
    from .commands import arguments

    arguments(parser)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    setup(sub)
    v = sub.add_parser("verify", help="check frozen evidence and review presentation")
    v.add_argument("bundle", type=Path)
    f = sub.add_parser("finalize", help="export a reviewed report; originals remain intact")
    f.add_argument("bundle", type=Path)
    f.add_argument("--decisions", type=Path, required=True)
    f.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("schema", help="print a versioned input or review schema")
    s.add_argument("name")
    args = p.parse_args(argv)
    try:
        if args.command == "schema":
            from .commands import schemas

            if args.name not in schemas():
                raise ValueError("Unknown schema; choose " + ", ".join(schemas()))
            print(json.dumps(schemas()[args.name].model_json_schema(), indent=2))
        elif args.command == "verify":
            record, _ = verify(args.bundle)
            print(json.dumps({"status": "verified", "package_digest": record["digest"]}))
        elif args.command == "finalize":
            print(json.dumps({"review_status": finalize(args.bundle, args.decisions, args.out)}))
        else:
            from .commands import execute

            report, snapshots, exports = execute(args)
            report["configuration"]["ci_fail_on"] = args.fail_on
            report["environment"] = {
                "python": platform.python_version(),
                "pydantic": version("pydantic"),
            }
            exports = {
                "report.md": markdown(report).encode(),
                "findings.sarif": canonical(sarif(report)),
                **exports,
            }
            record = bundle(args.out, report, snapshots, exports)
            print(
                json.dumps(
                    {
                        "status": "analysed",
                        "findings": len(report["findings"]),
                        "package_digest": record["digest"],
                        "output": str(args.out),
                    }
                )
            )
            levels = {"none": 99, "info": 0, "warning": 1, "error": 2}
            if any(levels[r["severity"]] >= levels[args.fail_on] for r in report["findings"]):
                return 1
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "invalid-input", "error": str(exc)}), file=sys.stderr)
        return 2


def analysis_args(parser):
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--fail-on",
        choices=["none", "info", "warning", "error"],
        default="none",
        help="CI threshold; 1 means findings, 2 means invalid input",
    )
