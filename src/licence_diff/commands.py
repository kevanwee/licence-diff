from pathlib import Path

from .audit import Decisions, canonical, digest, read_json
from .cli import analysis_args
from .engine import RightsRegister, compare, extract


def arguments(sub):
    p = sub.add_parser(
        "compare", help="extract supported licence schedules or compare supplied rights registers"
    )
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--matter", required=True)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--before-register", type=Path)
    p.add_argument("--after-register", type=Path)
    analysis_args(p)


def schemas():
    return {"rights": RightsRegister, "decisions": Decisions}


def execute(args):
    raw = [args.before.read_bytes(), args.after.read_bytes()]
    registers = []
    for source, supplied in zip(raw, (args.before_register, args.after_register)):
        register = (
            RightsRegister.model_validate(read_json(supplied))
            if supplied
            else extract(
                source.decode("utf-8-sig"),
                digest(source),
                matter=args.matter,
                synthetic=args.synthetic,
            )
        )
        if register.matter != args.matter or register.synthetic != args.synthetic:
            raise ValueError(
                "CLI matter/synthetic settings disagree with the supplied rights register"
            )
        registers.append(register)
    report = compare(*registers, *raw)
    snapshots = {"before.txt": raw[0], "after.txt": raw[1]}
    exports = {
        f"{side}-rights.json": canonical(register.model_dump(mode="json"))
        for side, register in zip(("before", "after"), registers)
    }
    return report, snapshots, exports
