#!/usr/bin/env python3
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import gitproc

BODY_OPEN = "<!-- lc:body -->"
BODY_CLOSE = "<!-- /lc:body -->"


LAYER_LINES_LIMIT_KEY = "layer-lines-limit"
LAYER_LINES_LIMIT_ENV = "LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT"

LAYER_CHECK_FILE = ".lightcycle/layer-check"
LAYER_CHECK_TIMEOUT_KEY = "layer-check-timeout-seconds"
LAYER_CHECK_TIMEOUT_ENV = "LC_WORKFLOW_CONFIG_LAYER_CHECK_TIMEOUT_SECONDS"
LAYER_CHECK_CEILING = 240
LAYER_CHECK_OUTPUT_LINES = 40
LAYER_CHECK_OUTPUT_CHARS = 4000


class Fail(Exception):
    pass


def run(args, check=True, retry=True):
    try:
        proc = gitproc.run(args, retry=retry)
    except gitproc.GitTimeout as error:
        raise Fail(f"{error.cmd} timed out after {error.limit}s ({error.attempts} attempts)")
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"{' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc


STACK_LOCK_MESSAGE = "another process is currently editing the stack"
STACK_LOCK_FIRST_WAIT = 5
STACK_LOCK_MAX_WAIT = 20
STACK_LOCK_WINDOW = 150

sleep = time.sleep
monotonic = time.monotonic


def gh_stack(*args, check=True):
    started = monotonic()
    wait = STACK_LOCK_FIRST_WAIT
    while True:
        proc = run(["gh", "stack", *args], check=False)
        output = (proc.stderr or "") + (proc.stdout or "")
        if proc.returncode == 0 or STACK_LOCK_MESSAGE not in output:
            break
        remaining = STACK_LOCK_WINDOW - (monotonic() - started)
        if remaining <= 0:
            raise Fail(
                f"gh stack {' '.join(args)} could not run: the gh stack lock "
                f"({STACK_LOCK_MESSAGE}) stayed held for the {STACK_LOCK_WINDOW} s window waited"
            )
        sleep(min(wait, remaining))
        wait = min(wait * 2, STACK_LOCK_MAX_WAIT)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"gh stack {' '.join(args)} failed ({proc.returncode}): {detail}")
    return proc


def git(*args, check=True):
    return run(["git", *args], check=check).stdout.strip()


def gh_json(path, *flags):
    out = run(["gh", "api", *flags, path]).stdout
    decoder = json.JSONDecoder()
    merged, pos = [], 0
    text = out.strip()
    if not text:
        return []
    while pos < len(text):
        value, end = decoder.raw_decode(text, pos)
        merged.extend(value) if isinstance(value, list) else merged.append(value)
        pos = end
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return merged


def gh_write(path, fields, method=None):
    args = ["gh", "api"]
    if method:
        args += ["-X", method]
    args.append(path)
    tmp = []
    try:
        for key, value in fields.items():
            if key == "body":
                with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as handle:
                    handle.write(value)
                tmp.append(handle.name)
                args += ["-F", f"body=@{handle.name}"]
            else:
                args += ["-f", f"{key}={value}"]
        return json.loads(run(args, retry=False).stdout or "{}")
    finally:
        for name in tmp:
            os.unlink(name)


def owner_repo():
    url = git("remote", "get-url", "origin")
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match:
        raise Fail(f"cannot read owner and repo from remote {url}")
    return match.group(1), match.group(2)


def find_pr(owner, repo, branch):
    pulls = gh_json(f"repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open")
    return pulls[0] if pulls else None


def dirty_paths():
    dirty = run(["git", "status", "--porcelain"]).stdout
    return ", ".join(line[3:] for line in dirty.splitlines())


def fold_digest(item):
    paths = [line[3:] for line in run(["git", "status", "--porcelain"]).stdout.splitlines()]
    if len(paths) != 1 or os.path.basename(paths[0]) != f"{item}-digest.md":
        return ""
    run(["git", "add", "--", paths[0]])
    run(["git", "commit", "--amend", "--no-edit"])
    return f"amended the uncommitted digest {paths[0]} into the spec commit"


def sync_to_remote(branch):
    remote = git("rev-parse", "--verify", "-q", f"origin/{branch}", check=False)
    if not remote:
        return ""
    local = git("rev-parse", "HEAD")
    if remote == local:
        return ""
    if any(line.startswith("+") for line in git("cherry", f"origin/{branch}", "HEAD").splitlines()):
        return ""
    paths = dirty_paths()
    if paths:
        raise Fail(
            f"local {branch} is at {local}, origin/{branch} is at {remote}, "
            f"and the worktree has uncommitted changes in {paths}; commit or discard them, then re-run"
        )
    git("reset", "--hard", f"origin/{branch}")
    return f"reset local {local} to remote {remote}"


def quote_block(quote, stage):
    if not quote:
        return ""
    return f"\n\n## Closing note from {stage}\n\n{quote}"


def managed_block(quote, stage, ref="HEAD", extra=""):
    message = git("log", "-1", "--format=%B", ref).rstrip()
    return f"\n{message}{extra}{quote_block(quote, stage)}\n"


def new_body(item, quote, stage, ref="HEAD", extra=""):
    return f"<!-- lc:item={item} -->\n{BODY_OPEN}{managed_block(quote, stage, ref, extra)}{BODY_CLOSE}"


def resync_body(body, item, quote, stage, ref="HEAD", extra=""):
    start = body.find(BODY_OPEN)
    end = body.find(BODY_CLOSE)
    if start == -1 or end == -1 or end < start:
        return None
    head = body[:start]
    if f"<!-- lc:item={item} -->" not in body:
        head += f"<!-- lc:item={item} -->\n"
    return head + BODY_OPEN + managed_block(quote, stage, ref, extra) + body[end:]


def resync_existing(pr, owner, repo, item, quote, stage, ref="HEAD", extra="", adopt=False):
    num = pr["number"]
    path = f"repos/{owner}/{repo}/pulls/{num}"
    current = gh_json(path)[0]
    fields = {}
    current_body = current.get("body") or ""
    updated = resync_body(current_body, item, quote, stage, ref, extra)
    if updated is None and adopt:
        updated = new_body(item, quote, stage, ref, extra)
    if updated is not None and updated != current_body:
        fields["body"] = updated
    title = git("log", "-1", "--format=%s", ref)
    if title != current.get("title"):
        fields["title"] = title
    if fields:
        gh_write(path, fields, method="PATCH")


def base_ref():
    git("remote", "set-head", "origin", "--auto", check=False)
    proc = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], check=False)
    ref = proc.stdout.strip()
    if proc.returncode != 0 or not ref:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"cannot resolve the default branch of origin: {detail}")
    return ref


def base_branch():
    return base_ref().split("/", 1)[1]


def create_pr(owner, repo, branch, item, quote, stage, extra=""):
    title = git("log", "-1", "--format=%s")
    fields = {
        "title": title,
        "body": new_body(item, quote, stage, extra=extra),
        "head": branch,
        "base": base_branch(),
    }
    try:
        created = gh_write(f"repos/{owner}/{repo}/pulls", fields)
        return created["html_url"]
    except (Fail, KeyError) as error:
        again = find_pr(owner, repo, branch)
        if again:
            return again["html_url"]
        raise Fail(f"creating the PR failed and no PR exists for {branch}: {error}")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def close_rework_loop(owner, repo, num):
    base = f"repos/{owner}/{repo}"
    issue_comments = gh_json(f"{base}/issues/{num}/comments", "--paginate")
    review_comments = gh_json(f"{base}/pulls/{num}/comments", "--paginate")
    reviews = gh_json(f"{base}/pulls/{num}/reviews", "--paginate")
    tagged = (
        [("issue", c) for c in issue_comments]
        + [("review-comment", c) for c in review_comments]
        + [("review", c) for c in reviews]
    )
    completed = set()
    for _, comment in tagged:
        completed.update(re.findall(r"<!-- lc:completes=(\d+) -->", comment.get("body") or ""))
    commit_time = parse_time(git("log", "-1", "--format=%cI"))
    sha = git("rev-parse", "HEAD")
    subject = git("log", "-1", "--format=%s")
    posted = 0
    for kind, comment in tagged:
        body = comment.get("body") or ""
        cid = str(comment["id"])
        if "<!-- lc:decision=rework -->" not in body or cid in completed:
            continue
        stamp = comment.get("created_at") or comment.get("submitted_at")
        if not stamp or parse_time(stamp) >= commit_time:
            continue
        reply = (
            f"<!-- lc -->\n<!-- lc:completes={cid} -->\n"
            f"Pushed {sha} (\"{subject}\") for this request. "
            "This reply records that the push happened; it does not verify the push addresses the request."
        )
        if kind == "review-comment":
            gh_write(f"{base}/pulls/{num}/comments/{cid}/replies", {"body": reply})
        else:
            gh_write(f"{base}/issues/{num}/comments", {"body": reply})
        posted += 1
    return posted


def refuse_merge_commits(base, tip="HEAD"):
    merges = git("rev-list", "--merges", f"{base}..{tip}", check=False).split()
    if merges:
        raise Fail(
            f"{tip} holds merge commit(s) {', '.join(merges)} ahead of {base}; a rebase would drop "
            "them and leave nothing to open a PR from. The squash most likely amended an upstream "
            "commit. Find the pre-amend commit with `git reflog`, run `git reset --keep <sha>` to "
            "it, then re-run."
        )


def rebase_onto_base(valid_outcomes):
    git("fetch", "origin")
    base = base_ref()
    refuse_merge_commits(base)
    proc = run(["git", "rebase", base], check=False)
    if proc.returncode == 0:
        return None
    paths = git("diff", "--name-only", "--diff-filter=U", check=False).split()
    run(["git", "rebase", "--abort"], check=False)
    if not paths:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"git rebase {base} failed with no conflicted paths: {detail}")
    if "conflicted" in valid_outcomes:
        return {"outcome": "conflicted", "note": f"rebase conflicts in {', '.join(paths)}"}
    raise Fail(
        f"rebase onto {base} conflicts in {', '.join(paths)}; this stage has no conflicted outcome"
    )


def read_delivery(step):
    for entry in (step.get("inputs") or {}).get("item") or []:
        if entry.get("name") == "delivery" and entry.get("value"):
            return parse_delivery(entry["value"])
    return None


def parse_delivery(text):
    parsed = {"decision": "", "reasons": "", "layers": {}}
    current = None
    for line in text.splitlines():
        head = re.match(r"\s*(Decision|Reasons|Layer\s+(\d+))\s*:\s*(.*)$", line)
        if not head:
            if current == "reasons" and line.strip():
                parsed["reasons"] += " " + line.strip()
            continue
        if head.group(1) == "Decision":
            parsed["decision"], current = head.group(3).strip(), "decision"
        elif head.group(1) == "Reasons":
            parsed["reasons"], current = head.group(3).strip(), "reasons"
        else:
            parsed["layers"][int(head.group(2))] = head.group(3).strip()
            current = "layer"
    return parsed


def delivery_lines(delivery):
    lines = []
    if delivery["decision"]:
        lines.append(f"Decision: {delivery['decision']}")
    if delivery["reasons"]:
        lines.append(f"Reasons: {delivery['reasons']}")
    return lines


def delivery_section(lines):
    return "\n\n## Delivery\n\n" + "\n".join(lines) if lines else ""


def stack_branches(branch):
    proc = gh_stack("view", "--json", check=False)
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return []
    names = [b.get("name") for b in (data.get("branches") or []) if isinstance(b, dict)]
    if len(names) < 2 or branch not in names:
        return []
    if names[-1] != branch:
        raise Fail(
            f"the worktree holds a stack whose top layer is {names[-1]}, not {branch}; "
            "the item's branch must be the top layer"
        )
    return names


def worktree_branches():
    out = git("worktree", "list", "--porcelain", check=False)
    return {
        line[len("branch refs/heads/"):]
        for line in out.splitlines()
        if line.startswith("branch refs/heads/")
    }


def was_ancestor(sha, tip):
    return run(["git", "merge-base", "--is-ancestor", sha, tip], check=False).returncode == 0


def sync_layers(names, branch):
    notes = []
    held = worktree_branches()
    for layer in names:
        if layer == branch:
            continue
        remote = git("rev-parse", "--verify", "-q", f"origin/{layer}", check=False)
        local = git("rev-parse", "--verify", "-q", f"refs/heads/{layer}", check=False)
        if not remote or not local or remote == local:
            continue
        if layer in held:
            notes.append(f"held back layer {layer}: checked out in another worktree")
            continue
        ahead = git("rev-list", f"origin/{layer}..{layer}", check=False).split()
        unique = {
            line[2:].strip()
            for line in git("cherry", f"origin/{layer}", layer, check=False).splitlines()
            if line.startswith("+")
        }
        seen = git("reflog", "show", f"origin/{layer}", "--format=%H", check=False).split()
        lost = [
            sha
            for sha in ahead
            if sha in unique and not any(was_ancestor(sha, tip) for tip in seen)
        ]
        if lost:
            notes.append(
                f"held back layer {layer}: local commit {lost[0][:8]} is not on the remote"
            )
            continue
        moved = run(["git", "update-ref", f"refs/heads/{layer}", remote, local], check=False)
        if moved.returncode != 0:
            notes.append(f"held back layer {layer}: its ref moved while syncing")
            continue
        notes.append(f"reset layer {layer} {local} to remote {remote}")
    return notes


STACK_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/stack/\d+")
STACKS_DISABLED = 9


def rebase_stack(valid_outcomes, names=()):
    git("fetch", "origin")
    base = base_ref()
    for layer in names:
        refuse_merge_commits(base, layer)
    proc = gh_stack("rebase", check=False)
    if proc.returncode == 0:
        return None
    paths = git("diff", "--name-only", "--diff-filter=U", check=False).split()
    gh_stack("rebase", "--abort", check=False)
    if not paths:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"gh stack rebase failed with no conflicted paths: {detail}")
    if "conflicted" in valid_outcomes:
        return {"outcome": "conflicted", "note": f"stack rebase conflicts in {', '.join(paths)}"}
    raise Fail(
        f"stack rebase conflicts in {', '.join(paths)}; this stage has no conflicted outcome"
    )


STACK_NUMBER = re.compile(r"/([^/\s]+)/([^/\s]+)/stack/(\d+)$")


def github_layers(owner, repo, stack_url):
    found = STACK_NUMBER.search(stack_url or "")
    if not found:
        return None
    proc = run(["gh", "api", f"repos/{found.group(1)}/{found.group(2)}/stacks/{found.group(3)}"], check=False)
    if proc.returncode != 0:
        if "HTTP 404" in (proc.stderr or proc.stdout):
            return None
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"reading the stack {stack_url} failed ({proc.returncode}): {detail}")
    try:
        entries = json.loads(proc.stdout)["pull_requests"]
        return {
            "number": found.group(3),
            "merged": [e["head"]["ref"] for e in entries if e.get("merged_at")],
            "layers": [
                {"number": e["number"], "head": e["head"]["ref"], "state": e.get("state")}
                for e in entries
                if not e.get("merged_at")
            ],
        }
    except (ValueError, KeyError, TypeError):
        raise Fail(f"could not parse the stack {stack_url} read from GitHub")


def local_stack_names():
    proc = gh_stack("view", "--json", check=False)
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return []
    return [b.get("name") for b in (data.get("branches") or []) if isinstance(b, dict)]


def drop_merged(owner, repo, names, recorded_stack):
    pairs = list(enumerate(names, start=1))
    current = github_layers(owner, repo, recorded_stack)
    if not current:
        return pairs
    merged = set(current["merged"])
    return [(index, name) for index, name in pairs if name not in merged or index == len(pairs)]


def recut_stack(owner, repo, names, recorded_stack):
    current = github_layers(owner, repo, recorded_stack)
    if not current or [layer["head"] for layer in current["layers"]] == names:
        return None
    gh_stack("unstack", current["number"])
    if local_stack_names() != names:
        gh_stack("init", *names)
    return [layer for layer in current["layers"] if layer["head"] not in names]


def close_dropped(owner, repo, dropped, top_url):
    base = f"repos/{owner}/{repo}"
    for layer in dropped:
        if layer["state"] == "open":
            gh_write(
                f"{base}/issues/{layer['number']}/comments",
                {"body": f"Layer dropped by a re-cut; see {top_url}"},
            )
            gh_write(f"{base}/pulls/{layer['number']}", {"state": "closed"}, method="PATCH")
        run(["gh", "api", "-X", "DELETE", f"{base}/git/refs/heads/{layer['head']}"], check=False)


def submit_stack(branch):
    proc = gh_stack("submit", "--auto", "--open", check=False)
    if proc.returncode == STACKS_DISABLED:
        return None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"gh stack submit --auto --open failed ({proc.returncode}): {detail}")
    found = STACK_URL.search(proc.stdout + proc.stderr)
    if not found:
        found = STACK_URL.search(gh_stack("view", "--json", check=False).stdout)
    if not found:
        raise Fail("gh stack submit --auto --open succeeded but printed no stack url")
    return found.group(0)


def open_stack(owner, repo, item, quote, stage, layers, delivery, stack_url, recorded, replace=False):
    top_url = None
    for position, (index, name) in enumerate(layers, start=1):
        pr = find_pr(owner, repo, name)
        if not pr:
            raise Fail(f"gh stack submit --auto --open left no open PR for layer {index} ({name})")
        lines = []
        if delivery and delivery["layers"].get(index):
            lines.append(f"Layer {index}: {delivery['layers'][index]}")
        top = position == len(layers)
        if top and delivery:
            lines = delivery_lines(delivery) + lines
        resync_existing(
            pr, owner, repo, item, quote if top else "", stage, ref=name,
            extra=delivery_section(lines), adopt=True,
        )
        if top:
            top_url = pr["html_url"]
    flag = ["--replace"] if replace else []
    run(["lc", "attach", item, "stack", stack_url, *flag])
    if replace or recorded != top_url:
        run(["lc", "attach", item, "pr", top_url, *flag])
    return top_url


def layer_lines_limit():
    raw = os.environ.get(LAYER_LINES_LIMIT_ENV, "").strip()
    if not raw:
        raise Fail(f"the config key {LAYER_LINES_LIMIT_KEY} is required and is not set")
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise Fail(f"the config key {LAYER_LINES_LIMIT_KEY} must be a positive integer, got {raw!r}")
    return value


def diff_lines(base, head):
    total = 0
    for line in git("diff", "--numstat", f"{base}...{head}").splitlines():
        added, deleted = line.split("\t")[:2]
        total += (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)
    return total


def absorbed_in_base(layer):
    base = base_ref()
    fork = git("merge-base", base, layer, check=False)
    if not fork:
        return False
    paths = git("diff", "--name-only", fork, layer, check=False).split()
    if not paths:
        return False
    return run(["git", "diff", "--quiet", layer, base, "--", *paths], check=False).returncode == 0


def broken_chain(names, branch):
    chain = list(names)
    if chain and chain[-1] != branch:
        chain.append(branch)
    for position in range(2, len(chain) + 1):
        lower, upper = chain[position - 2], chain[position - 1]
        if not was_ancestor(lower, upper):
            if absorbed_in_base(lower):
                continue
            return f"Re-cut: layer {position} of {len(chain)} is not a child of layer {position - 1}"
        count = git("rev-list", "--count", f"{lower}..{upper}", check=False)
        if not count.isdigit() or int(count) < 1:
            return f"Re-cut: layer {position} of {len(chain)} has no commits of its own"
    return None


def refuse_broken_chain(valid, names, branch):
    if "too-big" not in valid:
        return None
    note = broken_chain(names, branch)
    if not note:
        return None
    return {"outcome": "too-big", "note": note}


def marked_irreducible(text):
    return bool(re.search(r"\birreducible\b", text or "", re.IGNORECASE))


def oversized(layers, delivery, base, only=None):
    limit = layer_lines_limit()
    over = []
    if layers:
        for position, (index, name) in enumerate(layers, start=1):
            lower = base if position == 1 else layers[position - 2][1]
            count = diff_lines(lower, name)
            if count > limit and not marked_irreducible(delivery["layers"].get(index, "")):
                over.append(f"layer {position} of {len(layers)} is {count} lines")
    else:
        count = diff_lines(base, "HEAD")
        marker = delivery["layers"].get(only, "") if only else ""
        if count > limit and not marked_irreducible(marker) and not marked_irreducible(delivery["reasons"]):
            over.append(f"the one PR is {count} lines")
    suffix = (
        f", over {LAYER_LINES_LIMIT_KEY} {limit} and not marked irreducible"
    )
    return [item + suffix for item in over]


def show_step(step_id):
    proc = run(["lc", "show", step_id], check=False)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def repeat_recut(step_id, step, note):
    if not step.get("stage"):
        return None
    seen = {step_id}
    current = step
    while True:
        previous_id = current.get("previous_step")
        if not previous_id or previous_id in seen:
            return None
        seen.add(previous_id)
        current = show_step(previous_id)
        if current is None:
            return None
        if current.get("stage") == step.get("stage"):
            if current.get("outcome") == "too-big" and current.get("report") == note:
                return previous_id, current.get("report")
            return None


def layer_check_command(base):
    proc = run(["git", "show", f"{base}:{LAYER_CHECK_FILE}"], check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def layer_check_timeout():
    raw = os.environ.get(LAYER_CHECK_TIMEOUT_ENV, "").strip()
    if not raw:
        raise Fail(f"the config key {LAYER_CHECK_TIMEOUT_KEY} is required and is not set")
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0 or value > LAYER_CHECK_CEILING:
        raise Fail(
            f"the config key {LAYER_CHECK_TIMEOUT_KEY} must be a positive integer no greater than "
            f"{LAYER_CHECK_CEILING}, got {raw!r}"
        )
    return value


def run_layer_command(command, directory, limit):
    started = monotonic()
    code, output, timed_out = gitproc.run_combined(["sh", "-c", command], directory, limit)
    return {
        "code": code,
        "seconds": round(monotonic() - started),
        "output": output,
        "timed_out": timed_out,
    }


def run_layer_checks(layers, command, limit):
    directories = []
    try:
        for _, name in layers:
            directory = tempfile.mkdtemp(prefix="lc-layer-check-")
            directories.append(directory)
            run(["git", "worktree", "add", "--detach", directory, name])
        with ThreadPoolExecutor(max_workers=len(directories)) as pool:
            futures = [pool.submit(run_layer_command, command, d, limit) for d in directories]
            return [future.result() for future in futures]
    finally:
        for directory in directories:
            run(["git", "worktree", "remove", "--force", directory], check=False)
            shutil.rmtree(directory, ignore_errors=True)
        run(["git", "worktree", "prune"], check=False)


def layer_red_prefix(position, total, name):
    return f"Layer {position} of {total} ({name} at {git('rev-parse', '--short', name)})"


def tail_output(text):
    lines = text.splitlines()[-LAYER_CHECK_OUTPUT_LINES:]
    return "\n".join(lines)[-LAYER_CHECK_OUTPUT_CHARS:]


def repeat_layer_red(step_id, step, prefix):
    if not step.get("stage"):
        return None
    seen = {step_id}
    current = step
    while True:
        previous_id = current.get("previous_step")
        if not previous_id or previous_id in seen:
            return None
        seen.add(previous_id)
        current = show_step(previous_id)
        if current is None:
            return None
        if current.get("stage") == step.get("stage"):
            report = current.get("report") or ""
            if current.get("outcome") == "layer-red" and report.startswith(prefix):
                return previous_id
            return None


def check_layers(step_id, step, layers):
    base = base_ref()
    command = layer_check_command(base)
    if not command:
        return None, f"layer check skipped: no {LAYER_CHECK_FILE} at {base}"
    limit = layer_check_timeout()
    results = run_layer_checks(layers, command, limit)
    total = len(layers)
    for position, ((_, name), result) in enumerate(zip(layers, results), start=1):
        if result["code"] == 0 and not result["timed_out"]:
            continue
        prefix = layer_red_prefix(position, total, name)
        if result["timed_out"]:
            head = f"{prefix} layer check timed out after {limit} s"
        else:
            head = f"{prefix} failed the layer check: exit {result['code']} after {result['seconds']} s"
        repeat = repeat_layer_red(step_id, step, prefix)
        if repeat:
            raise Fail(
                f"Layer check loop: code-open-pr refused {prefix} twice running ({repeat} and "
                f"{step_id}) and the layer head did not change. A human must decide what to do."
            )
        note = f"{head}\n{command}\n{tail_output(result['output'])}"
        return {"outcome": "layer-red", "note": note}, ""
    timings = "; ".join(
        f"layer {position} of {total} passed in {result['seconds']} s"
        for position, result in enumerate(results, start=1)
    )
    return None, f"layer check: {timings}"


def abort_stale_rebase():
    for name in ("rebase-merge", "rebase-apply"):
        if os.path.exists(git("rev-parse", "--git-path", name)):
            run(["git", "rebase", "--abort"], check=False)
            return


def main():
    step_id = os.environ["LC_STEP"]
    step = json.loads(run(["lc", "show", step_id]).stdout)
    item = step["item"]
    previous = (step.get("inputs") or {}).get("previous") or {}
    quote = previous.get("report") or ""
    stage = previous.get("stage") or ""
    valid = step.get("valid_outcomes") or []
    recorded = next(
        (
            r.get("pr")
            for r in reversed(step.get("runs", []))
            if r.get("pass") == step.get("pass") and r.get("phase") == step.get("phase")
        ),
        None,
    )

    recorded_stack = next(
        (
            r.get("stack")
            for r in reversed(step.get("runs", []))
            if r.get("pass") == step.get("pass") and r.get("phase") == step.get("phase")
        ),
        None,
    )

    abort_stale_rebase()
    branch = git("branch", "--show-current")
    if not branch:
        raise Fail("the worktree is not on a branch")
    owner, repo = owner_repo()
    git("fetch", "origin")
    notes = [sync_to_remote(branch)]
    folded = fold_digest(item)
    if folded:
        print(folded, file=sys.stderr)
        notes.append(folded)
    paths = dirty_paths()
    if paths:
        raise Fail(
            f"the worktree has uncommitted changes in {paths}; commit or discard them, then re-run"
        )

    delivery = read_delivery(step)
    names = stack_branches(branch)
    layers = drop_merged(owner, repo, names, recorded_stack) if names else []
    only = layers[0][0] if len(layers) == 1 else None
    if len(layers) < 2:
        layers = []
    names = [name for _, name in layers]
    if names:
        notes.extend(sync_layers(names, branch))
        refused = refuse_broken_chain(valid, names, branch)
        if refused:
            return refused
    if "too-big" in valid and delivery:
        over = oversized(layers, delivery, base_ref(), only)
        if over:
            note = "Re-cut: " + "; ".join(over)
            repeat = repeat_recut(step_id, step, note)
            if repeat:
                raise Fail(
                    "Re-cut loop: code-open-pr refused with the same figure twice running and "
                    f"cut-delivery kept the cut. This pass: {note}. Previous pass ({repeat[0]}): "
                    f"{repeat[1]}. A human must decide whether the cut, the limit or an "
                    "`irreducible` marker should change."
                )
            return {"outcome": "too-big", "note": note}
    fallback = ""
    if names:
        conflict = rebase_stack(valid, names)
        if conflict:
            return conflict
        refused = refuse_broken_chain(valid, names, branch)
        if refused:
            return refused
        if "layer-red" in valid:
            refused, check_note = check_layers(step_id, step, layers)
            if refused:
                return refused
            notes.append(check_note)
        git("checkout", branch)
        dropped = recut_stack(owner, repo, names, recorded_stack)
        stack_url = submit_stack(branch)
        if stack_url:
            url = open_stack(
                owner, repo, item, quote, stage, layers, delivery, stack_url, recorded,
                replace=dropped is not None,
            )
            if dropped:
                close_dropped(owner, repo, dropped, url)
                notes.append(f"re-cut: closed {len(dropped)} dropped layer(s)")
            num = int(url.rstrip("/").rsplit("/", 1)[-1])
            replies = close_rework_loop(owner, repo, num)
            notes.append(f"stack {stack_url}, top PR {url}")
            if replies:
                notes.append(f"posted {replies} completion repl{'y' if replies == 1 else 'ies'}")
            return {"outcome": "done", "note": "; ".join(n for n in notes if n)}
        fallback = delivery_section(
            ["Stacks are not enabled for this repo; the reasons below apply to this one PR."]
            + (delivery_lines(delivery) if delivery else [])
        )
        notes.append("stacks not enabled for this repo; opened one PR")

    existing = find_pr(owner, repo, branch)
    if existing:
        git("push", "--force-with-lease", "-u", "origin", branch)
        resync_existing(existing, owner, repo, item, quote, stage, extra=fallback)
        url, num = existing["html_url"], existing["number"]
        if recorded != url:
            run(["lc", "attach", item, "pr", url])
    else:
        if recorded:
            raise Fail(
                f"this phase run's recorded PR {recorded} does not match its worktree's branch "
                f"{branch} (the pulls lookup for {branch} found nothing); resolve the divergence "
                "before opening or reusing a PR for this phase"
            )
        conflict = rebase_onto_base(valid)
        if conflict:
            return conflict
        git("push", "--force-with-lease", "-u", "origin", branch)
        url = create_pr(owner, repo, branch, item, quote, stage, extra=fallback)
        num = int(url.rstrip("/").rsplit("/", 1)[-1])
        run(["lc", "attach", item, "pr", url])

    replies = close_rework_loop(owner, repo, num)
    notes.append(f"PR {url}")
    if replies:
        notes.append(f"posted {replies} completion repl{'y' if replies == 1 else 'ies'}")
    return {"outcome": "done", "note": "; ".join(n for n in notes if n)}


if __name__ == "__main__":
    try:
        result = main()
    except Fail as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result))
