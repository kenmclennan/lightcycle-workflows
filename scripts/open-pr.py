#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

BODY_OPEN = "<!-- lc:body -->"
BODY_CLOSE = "<!-- /lc:body -->"


class Fail(Exception):
    pass


def run(args, check=True):
    proc = subprocess.run(args, capture_output=True, text=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"{' '.join(args)} failed ({proc.returncode}): {detail}")
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
                handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
                handle.write(value)
                handle.close()
                tmp.append(handle.name)
                args += ["-F", f"body=@{handle.name}"]
            else:
                args += ["-f", f"{key}={value}"]
        return json.loads(run(args).stdout or "{}")
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


def rebase_onto_base(valid_outcomes):
    git("fetch", "origin")
    base = base_ref()
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
    proc = run(["gh", "stack", "view", "--json"], check=False)
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


STACK_URL = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/stack/\d+")
STACKS_DISABLED = 9


def rebase_stack(valid_outcomes):
    git("fetch", "origin")
    proc = run(["gh", "stack", "rebase"], check=False)
    if proc.returncode == 0:
        return None
    paths = git("diff", "--name-only", "--diff-filter=U", check=False).split()
    run(["gh", "stack", "rebase", "--abort"], check=False)
    if not paths:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"gh stack rebase failed with no conflicted paths: {detail}")
    if "conflicted" in valid_outcomes:
        return {"outcome": "conflicted", "note": f"stack rebase conflicts in {', '.join(paths)}"}
    raise Fail(
        f"stack rebase conflicts in {', '.join(paths)}; this stage has no conflicted outcome"
    )


def submit_stack(branch):
    proc = run(["gh", "stack", "submit", "--auto"], check=False)
    if proc.returncode == STACKS_DISABLED:
        return None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        raise Fail(f"gh stack submit --auto failed ({proc.returncode}): {detail}")
    found = STACK_URL.search(proc.stdout + proc.stderr)
    if not found:
        found = STACK_URL.search(run(["gh", "stack", "view", "--json"], check=False).stdout)
    if not found:
        raise Fail("gh stack submit --auto succeeded but printed no stack url")
    return found.group(0)


def open_stack(owner, repo, item, quote, stage, names, delivery, stack_url, recorded):
    top_url = None
    for index, name in enumerate(names, start=1):
        pr = find_pr(owner, repo, name)
        if not pr:
            raise Fail(f"gh stack submit --auto left no open PR for layer {index} ({name})")
        lines = []
        if delivery and delivery["layers"].get(index):
            lines.append(f"Layer {index}: {delivery['layers'][index]}")
        top = index == len(names)
        if top and delivery:
            lines = delivery_lines(delivery) + lines
        resync_existing(
            pr, owner, repo, item, quote if top else "", stage, ref=name,
            extra=delivery_section(lines), adopt=True,
        )
        if top:
            top_url = pr["html_url"]
    run(["lc", "attach", item, "stack", stack_url])
    if recorded != top_url:
        run(["lc", "attach", item, "pr", top_url])
    return top_url


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

    abort_stale_rebase()
    branch = git("branch", "--show-current")
    if not branch:
        raise Fail("the worktree is not on a branch")
    owner, repo = owner_repo()
    git("fetch", "origin")
    notes = [sync_to_remote(branch)]
    paths = dirty_paths()
    if paths:
        raise Fail(
            f"the worktree has uncommitted changes in {paths}; commit or discard them, then re-run"
        )

    delivery = read_delivery(step)
    names = stack_branches(branch)
    fallback = ""
    if names:
        conflict = rebase_stack(valid)
        if conflict:
            return conflict
        git("checkout", branch)
        stack_url = submit_stack(branch)
        if stack_url:
            url = open_stack(owner, repo, item, quote, stage, names, delivery, stack_url, recorded)
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
