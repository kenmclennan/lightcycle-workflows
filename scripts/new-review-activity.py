#!/usr/bin/env python3
import datetime
import json
import os
import re
import subprocess
import sys

TITLE_PREFIX = "Review yield -"


def emit(obj):
    sys.stdout.write(json.dumps(obj))


def die(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def param(key):
    return os.environ.get("LC_SCHEDULE_PARAM_" + key.upper().replace("-", "_"), "").strip()


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die("%s failed (exit %d): %s" % (" ".join(cmd[:2]), proc.returncode, proc.stderr.strip()))
    return proc.stdout


def read_state(stdin):
    last = stdin.get("last_state")
    if not last:
        return None
    if isinstance(last, str):
        try:
            last = json.loads(last)
        except ValueError:
            die("last_state is not a through/boundary object: %r" % (last,))
    if not isinstance(last, dict) or not last.get("through"):
        die("last_state is not a through/boundary object: %r" % (last,))
    return last


def rows(report):
    found = []
    for stage in report.get("stages", []):
        for row in stage.get("verdict_rows", []):
            found.append((row["step"], str(row.get("closed_at", ""))[:10]))
        for row in stage.get("escape_rows", []):
            found.append((escape_key(row), str(row.get("at", ""))[:10]))
    for row in report.get("unattributed_escapes", []):
        found.append((escape_key(row), str(row.get("at", ""))[:10]))
    return found


def escape_key(row):
    if row.get("kind") == "post-merge" or row.get("linked_item"):
        return "%s|%s" % (row.get("item"), row.get("linked_item"))
    return "%s|%s|%s" % (row.get("verdict_step"), row.get("item"), row.get("at"))


def previous_item():
    best = None
    for line in run(["lc", "search", TITLE_PREFIX]).splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[1] == "done" and fields[3].startswith(TITLE_PREFIX):
            number = int(re.sub(r"\D", "", fields[0].split(".")[0]) or 0)
            if best is None or number > best[0]:
                best = (number, fields[0])
    return best[1] if best else "none"


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError:
        stdin = {}
    floor = param("catch-rate-floor")
    repeat_min = param("repeat-min")
    for key, value in (("catch-rate-floor", floor), ("repeat-min", repeat_min)):
        if not value:
            die("the schedule sets no %s parameter (required; the guard has no default)" % key)

    last = read_state(stdin)
    through = last["through"] if last else None
    boundary = set(last.get("boundary", [])) if last else set()

    cmd = ["lc", "review-yield", "--json"]
    if through:
        cmd[2:2] = ["--since", through]
    report = json.loads(run(cmd))

    new = [key for key, day in rows(report) if not (day == through and key in boundary)]
    if not new:
        emit({"outcome": "fail", "note": "no new review verdicts or escapes since %s" % (through or "the start")})
        return

    today = datetime.datetime.now().astimezone().date().isoformat()
    todays = sorted({key for key, day in rows(report) if day == today})
    description = "\n".join(
        [
            "since: %s" % (through or "none"),
            "already-counted: %s" % (", ".join(sorted(boundary)) or "none"),
            "previous: %s" % previous_item(),
            "floor: %s" % floor,
            "repeat-min: %s" % repeat_min,
        ]
    )
    emit(
        {
            "outcome": "pass",
            "title": "%s %s" % (TITLE_PREFIX, today),
            "description": description,
            "state": json.dumps({"through": today, "boundary": todays}, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
