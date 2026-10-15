import re
import sys
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parent.parent
pin_version = sys.argv[1]
requirement = tomllib.loads((root / "source.toml").read_text()).get("requires-engine")


def parse(text):
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.exit(f"not a three-integer version: {text!r}")
    return tuple(int(p) for p in parts)


if requirement is None:
    sys.exit("source.toml declares no requires-engine")

operators = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
}
pin = parse(pin_version)
failures = []

for clause in requirement.split(","):
    match = re.fullmatch(r"\s*(>=|<=|>|<)\s*(\S+)\s*", clause)
    if not match:
        sys.exit(f"unreadable requires-engine clause: {clause!r}")
    op, version = match.groups()
    if not operators[op](pin, parse(version)):
        failures.append(clause.strip())

if failures:
    print(
        f"ENGINE_PIN is engine {pin_version}, outside requires-engine = {requirement!r} "
        f"(fails: {', '.join(failures)})"
    )
    sys.exit(1)

print(f"ENGINE_PIN is engine {pin_version}, inside requires-engine = {requirement!r}")
