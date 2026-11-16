#!/usr/bin/env python3
import json
import sys

import gitproc

try:
    proc = gitproc.run(["git", "status", "--porcelain"])
except gitproc.GitTimeout as error:
    print(f"git status failed: {error}", file=sys.stderr)
    sys.exit(1)
if proc.returncode != 0:
    print(f"git status failed: {proc.stderr.strip()}", file=sys.stderr)
    sys.exit(1)

dirty = [line[3:] for line in proc.stdout.splitlines() if line.strip()]
if dirty:
    print(
        "the worktree has uncommitted changes and is left in place: " + ", ".join(dirty),
        file=sys.stderr,
    )
    sys.exit(1)

print(json.dumps({"outcome": "done", "note": "worktree clean"}))
