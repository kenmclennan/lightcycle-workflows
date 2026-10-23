#!/usr/bin/env python3
import base64
import json
import os
import re
import subprocess
import sys

TITLE = "bump the engine pin (%d commits behind)"
OPEN_PREFIX = "bump the engine pin"


def emit(obj):
    sys.stdout.write(json.dumps(obj))


def die(message):
    sys.stderr.write(message + "\n")
    sys.exit(1)


def param(key, default=None):
    value = os.environ.get("LC_SCHEDULE_PARAM_" + key.upper().replace("-", "_"), "").strip()
    return value or default


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        die("%s failed (exit %d): %s" % (cmd[0], proc.returncode, proc.stderr.strip()))
    return proc.stdout


def read_file(repo, path):
    payload = json.loads(run(["gh", "api", "repos/%s/contents/%s" % (repo, path)]))
    return base64.b64decode(payload["content"]).decode()


def engine_pin_section(text):
    match = re.search(r"^## Engine pin\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        die("CLAUDE.md has no '## Engine pin' section")
    return match.group(1)


def engine_repo(section):
    match = re.search(r"ENGINE_REPO\b[^\n]*?\bis\s+`([\w.-]+/[\w.-]+)`", section)
    if not match:
        die("the Engine pin section of CLAUDE.md has no 'ENGINE_REPO ... is `owner/name`' line")
    return match.group(1)


def pin_and_threshold(repo):
    section = engine_pin_section(read_file(repo, "CLAUDE.md"))
    engine = engine_repo(section)
    paths = [p for p in re.findall(r"`([\w./-]+\.[\w]+)`", section) if "/" in p]
    if not paths:
        die("the Engine pin section names no file that holds the pin")
    text = read_file(repo, paths[0])
    pin = re.search(r"\bENGINE_PIN\s*[:=]\s*['\"]?([0-9a-f]{40})\b", text)
    threshold = re.search(r"\bthreshold\s*=\s*(\d+)", text)
    if not pin:
        die("%s holds no ENGINE_PIN sha" % paths[0])
    if not threshold:
        die("%s holds no threshold=<N> line" % paths[0])
    return engine, pin.group(1), int(threshold.group(1))


def earlier_item_open(pin):
    for line in run(["lc", "search", pin]).splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[3].startswith(OPEN_PREFIX) and fields[1] != "done":
            return fields[0]
    return None


def main():
    try:
        stdin = json.load(sys.stdin)
    except ValueError:
        stdin = {}
    repo = param("repo")
    if not repo:
        die("the schedule sets no repo parameter (owner/name of the repo whose pin to check)")

    engine, pin, threshold = pin_and_threshold(repo)

    last = stdin.get("last_state")
    if last:
        try:
            filed_pin = json.loads(last).get("pin")
        except (ValueError, AttributeError):
            die("last_state is not a pin object: %r" % (last,))
        if filed_pin:
            open_id = earlier_item_open(filed_pin)
            if open_id:
                emit({"outcome": "fail", "note": "item %s from an earlier firing is still open" % open_id})
                return

    ahead_by = int(run(["gh", "api", "repos/%s/compare/%s...main" % (engine, pin), "--jq", ".ahead_by"]).strip())
    if ahead_by <= threshold:
        emit({"outcome": "fail", "note": "pin is %d commits behind, within threshold %d" % (ahead_by, threshold)})
        return

    main_sha = run(["gh", "api", "repos/%s/commits/main" % engine, "--jq", ".sha"]).strip()
    emit(
        {
            "outcome": "pass",
            "title": TITLE % ahead_by,
            "description": "The engine pin %s in %s is %d commits behind %s main (%s); the staleness threshold is %d."
            % (pin, repo, ahead_by, engine, main_sha, threshold),
            "state": json.dumps({"pin": pin, "main": main_sha}, sort_keys=True),
        }
    )


if __name__ == "__main__":
    main()
