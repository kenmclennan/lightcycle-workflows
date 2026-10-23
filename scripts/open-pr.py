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


def managed_block(quote, stage):
    message = git("log", "-1", "--format=%B").rstrip()
    return f"\n{message}{quote_block(quote, stage)}\n"


def new_body(item, quote, stage):
    return f"<!-- lc:item={item} -->\n{BODY_OPEN}{managed_block(quote, stage)}{BODY_CLOSE}"


def resync_body(body, item, quote, stage):
    start = body.find(BODY_OPEN)
    end = body.find(BODY_CLOSE)
    if start == -1 or end == -1 or end < start:
        return None
    head = body[:start]
    if f"<!-- lc:item={item} -->" not in body:
        head += f"<!-- lc:item={item} -->\n"
    return head + BODY_OPEN + managed_block(quote, stage) + body[end:]


def resync_existing(pr, owner, repo, item, quote, stage):
    num = pr["number"]
    path = f"repos/{owner}/{repo}/pulls/{num}"
    current = gh_json(path)[0]
    fields = {}
    updated = resync_body(current.get("body") or "", item, quote, stage)
    if updated is not None and updated != (current.get("body") or ""):
        fields["body"] = updated
    title = git("log", "-1", "--format=%s")
    if title != current.get("title"):
        fields["title"] = title
    if fields:
        gh_write(path, fields, method="PATCH")


def create_pr(owner, repo, branch, item, quote, stage):
    title = git("log", "-1", "--format=%s")
    fields = {
        "title": title,
        "body": new_body(item, quote, stage),
        "head": branch,
        "base": "main",
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


def rebase_onto_main(valid_outcomes):
    git("fetch", "origin")
    proc = run(["git", "rebase", "origin/main"], check=False)
    if proc.returncode == 0:
        return None
    paths = git("diff", "--name-only", "--diff-filter=U", check=False).split()
    run(["git", "rebase", "--abort"], check=False)
    if "conflicted" in valid_outcomes:
        return {"outcome": "conflicted", "note": f"rebase conflicts in {', '.join(paths)}"}
    raise Fail(
        f"rebase onto origin/main conflicts in {', '.join(paths)}; this stage has no conflicted outcome"
    )


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

    existing = find_pr(owner, repo, branch)
    if existing:
        git("push", "--force-with-lease", "-u", "origin", branch)
        resync_existing(existing, owner, repo, item, quote, stage)
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
        conflict = rebase_onto_main(valid)
        if conflict:
            return conflict
        git("push", "--force-with-lease", "-u", "origin", branch)
        url = create_pr(owner, repo, branch, item, quote, stage)
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
