import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
failures = []


def normalise(text):
    return "\n".join(line.strip() for line in text.splitlines())


for line in (root / "shared" / "manifest.txt").read_text().splitlines():
    if not line.strip():
        continue
    block, steps = line.split(":", 1)
    block = block.strip()
    canonical = normalise((root / "shared" / f"{block}.md").read_text().strip())
    for entry in steps.split():
        step, _, count = entry.partition("*")
        expected = int(count) if count else 1
        text = normalise((root / "steps" / f"{step}.md").read_text())
        found = text.count(canonical)
        if found != expected:
            failures.append(
                f"steps/{step}.md carries shared/{block}.md {found} time(s), expected {expected}"
            )

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("every listed step carries its shared block")
