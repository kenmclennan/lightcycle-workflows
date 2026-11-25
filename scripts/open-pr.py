#!/usr/bin/env python3
import json
import os
import re
import sys
import tempfile
from datetime import datetime

import gitproc

BODY_OPEN = "<!-- lc:body -->"
BODY_CLOSE = "<!-- /lc:body -->"
CODE_PHASES = ("code", "change")
PIPELINE_WORDS = ("specs", "spec", "driver", "findings", "finding", "carve-out", "routed")
ROBOT = "\U0001F916"


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


def gh_graphql(query, **variables):
    args = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if isinstance(value, int):
            args += ["-F", f"{key}={value}"]
        else:
            args += ["-f", f"{key}={value}"]
    return json.loads(run(args, retry=False).stdout or "{}")


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


TESTED_HEADING = re.compile(r"^(Tested|Not tested here):")


def code_message(message):
    lines = []
    skipping = False
    for line in message.splitlines():
        if skipping:
            if line.strip() and (line[0].isspace() or line.lstrip().startswith("-")):
                continue
            skipping = False
        if TESTED_HEADING.match(line):
            skipping = True
            continue
        if line.startswith("Also found, out of scope:"):
            line = "Follow-ups noticed:" + line[len("Also found, out of scope:"):]
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def pipeline_hits(text, stage):
    words = list(PIPELINE_WORDS)
    if stage:
        words.append(stage)
    pattern = re.compile(
        r"(?<![\w-])(" + "|".join(re.escape(w) for w in words) + r")(?![\w-])", re.IGNORECASE
    )
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in pattern.finditer(line):
            hits.append(f"{match.group(1)!r} on line {number}")
    return hits


def check_pipeline_words(stage):
    message = code_message(git("log", "-1", "--format=%B"))
    hits = pipeline_hits(message, stage)
    if hits:
        raise Fail(
            "the commit message is the PR description and must not use pipeline words: "
            + "; ".join(hits)
            + ". Reword the commit message in plain words, then re-run."
        )


def managed_block(quote, stage, code):
    message = git("log", "-1", "--format=%B").rstrip()
    if code:
        return f"\n{code_message(message)}\n"
    return f"\n{message}{quote_block(quote, stage)}\n"


def new_body(item, quote, stage, code):
    return f"<!-- lc:item={item} -->\n{BODY_OPEN}{managed_block(quote, stage, code)}{BODY_CLOSE}"


def resync_body(body, item, quote, stage, code):
    start = body.find(BODY_OPEN)
    end = body.find(BODY_CLOSE)
    if start == -1 or end == -1 or end < start:
        return None
    head = body[:start]
    if f"<!-- lc:item={item} -->" not in body:
        head += f"<!-- lc:item={item} -->\n"
    return head + BODY_OPEN + managed_block(quote, stage, code) + body[end:]


def resync_existing(pr, owner, repo, item, quote, stage, code):
    num = pr["number"]
    path = f"repos/{owner}/{repo}/pulls/{num}"
    current = gh_json(path)[0]
    fields = {}
    current_body = current.get("body") or ""
    updated = resync_body(current_body, item, quote, stage, code)
    if updated is not None and updated != current_body:
        fields["body"] = updated
    title = git("log", "-1", "--format=%s")
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


def create_pr(owner, repo, branch, item, quote, stage, code):
    title = git("log", "-1", "--format=%s")
    fields = {
        "title": title,
        "body": new_body(item, quote, stage, code),
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


def authenticated_login():
    try:
        login = gh_json("user")[0]["login"]
    except (Fail, ValueError, LookupError):
        return None
    return (login or "").casefold() or None


def thread_is_ours(comment, review_comments, login):
    if not login:
        return False
    root = comment
    if comment.get("in_reply_to_id"):
        root = next((c for c in review_comments if c.get("id") == comment["in_reply_to_id"]), None)
    if root is None:
        return False
    author = (root.get("user") or {}).get("login") or ""
    return author.casefold() == login


REACTIONS = {"+1": "THUMBS_UP", "eyes": "EYES"}
REACTION_MUTATION = (
    "mutation($subject: ID!, $content: ReactionContent!) "
    "{ addReaction(input: {subjectId: $subject, content: $content}) { reaction { content } } }"
)
THREADS_QUERY = (
    "query($owner: String!, $repo: String!, $num: Int!) { repository(owner: $owner, name: $repo) "
    "{ pullRequest(number: $num) { reviewThreads(first: 100) { pageInfo { hasNextPage } "
    "nodes { id comments(first: 100) { nodes { databaseId } } } } } } }"
)
RESOLVE_MUTATION = (
    "mutation($thread: ID!) { resolveReviewThread(input: {threadId: $thread}) "
    "{ thread { id isResolved } } }"
)


def react(owner, repo, kind, cid, content, node_id=None):
    base = f"repos/{owner}/{repo}"
    if kind == "mention":
        gh_write(f"{base}/issues/comments/{cid}/reactions", {"content": content})
    elif kind == "inline":
        gh_write(f"{base}/pulls/comments/{cid}/reactions", {"content": content})
    else:
        if not node_id:
            raise Fail(f"review {cid} has no node_id to react on")
        gh_graphql(REACTION_MUTATION, subject=node_id, content=REACTIONS[content])


def resolve_thread(owner, repo, num, comment_id):
    data = gh_graphql(THREADS_QUERY, owner=owner, repo=repo, num=num)
    pull = ((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {}
    threads = pull.get("reviewThreads") or {}
    for thread in threads.get("nodes") or []:
        ids = [c.get("databaseId") for c in (thread.get("comments") or {}).get("nodes") or []]
        if comment_id in ids:
            gh_graphql(RESOLVE_MUTATION, thread=thread["id"])
            return None
    if (threads.get("pageInfo") or {}).get("hasNextPage"):
        return f"thread for comment {comment_id} not resolved: the PR has more than 100 threads"
    return f"thread for comment {comment_id} not found, so it was not resolved"


def latest_records(step, name):
    latest = {}
    for entry in (step.get("inputs") or {}).get("item") or []:
        if entry.get("name") == name and entry.get("label"):
            latest[entry["label"]] = entry.get("value") or ""
    return latest


def parse_decision(value):
    try:
        parsed = json.loads(value)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def attempt(issues, label, call, *args):
    try:
        return call(*args)
    except (Fail, ValueError, KeyError) as error:
        issues.append(f"{label} failed: {error}")
        return None


def close_rework_loop(owner, repo, num, item, step):
    base = f"repos/{owner}/{repo}"
    decisions = latest_records(step, "feedback-decision")
    completed = latest_records(step, "feedback-completed")
    sha = git("rev-parse", "HEAD")
    short = sha[:7]
    subject = git("log", "-1", "--format=%s")
    eligible = []
    for key, value in decisions.items():
        decision = parse_decision(value)
        if decision.get("decision") != "rework" or key in completed:
            continue
        if decision.get("sha") == sha:
            continue
        kind, _, cid = key.partition(":")
        if kind not in ("inline", "review", "mention") or not cid.isdigit():
            continue
        eligible.append((key, kind, int(cid)))
    done, reacted, issues = 0, 0, []
    if not eligible:
        return done, reacted, issues
    lists = {}

    def listing(name):
        if name not in lists:
            lists[name] = gh_json(f"{base}/{name}", "--paginate")
        return lists[name]

    login = None
    login_read = False
    for key, kind, cid in eligible:
        if kind == "inline":
            if not login_read:
                login, login_read = authenticated_login(), True
            comments = listing(f"pulls/{num}/comments")
            comment = next((c for c in comments if c.get("id") == cid), None)
            in_thread = comment is not None and thread_is_ours(comment, comments, login)
            link = ""
            if not in_thread and comment is not None and comment.get("html_url"):
                link = f"In reply to {comment['html_url']}\n"
            if in_thread:
                root_id = comment.get("in_reply_to_id") or cid
                pool = [c for c in comments if c.get("id") == root_id or c.get("in_reply_to_id") == root_id]
            else:
                pool = listing(f"issues/{num}/comments")
            already = bool(login) and any(
                ((c.get("user") or {}).get("login") or "").casefold() == login
                and f"Done in {short}" in (c.get("body") or "")
                and (not link or link.strip() in (c.get("body") or ""))
                for c in pool
            )
            if not already:
                reply = f"{ROBOT} <!-- lc -->\n{link}Done in {short}: {subject}."
                if in_thread:
                    gh_write(f"{base}/pulls/{num}/comments/{cid}/replies", {"body": reply})
                else:
                    gh_write(f"{base}/issues/{num}/comments", {"body": reply})
            if in_thread:
                problem = attempt(issues, f"resolving {key}", resolve_thread, owner, repo, num, cid)
                if problem:
                    issues.append(problem)
        node_id = None
        if kind == "review":
            review = next((r for r in listing(f"pulls/{num}/reviews") if r.get("id") == cid), {})
            node_id = review.get("node_id")
        before = len(issues)
        attempt(issues, f"reaction on {key}", react, owner, repo, kind, cid, "+1", node_id)
        if len(issues) == before:
            reacted += 1
        run(["lc", "attach", item, "feedback-completed", "--label", key, sha])
        done += 1
    return done, reacted, issues


def refuse_merge_commits(base):
    merges = git("rev-list", "--merges", f"{base}..HEAD", check=False).split()
    if merges:
        raise Fail(
            f"HEAD holds merge commit(s) {', '.join(merges)} ahead of {base}; a rebase would drop "
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
    code = step.get("phase") in CODE_PHASES
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
    folded = fold_digest(item)
    if folded:
        print(folded, file=sys.stderr)
        notes.append(folded)
    paths = dirty_paths()
    if paths:
        raise Fail(
            f"the worktree has uncommitted changes in {paths}; commit or discard them, then re-run"
        )

    if code:
        check_pipeline_words(stage)

    existing = find_pr(owner, repo, branch)
    if existing:
        git("push", "--force-with-lease", "-u", "origin", branch)
        resync_existing(existing, owner, repo, item, quote, stage, code)
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
        url = create_pr(owner, repo, branch, item, quote, stage, code)
        num = int(url.rstrip("/").rsplit("/", 1)[-1])
        run(["lc", "attach", item, "pr", url])

    completed, reacted, issues = close_rework_loop(owner, repo, num, item, step)
    notes.append(f"PR {url}")
    if completed:
        notes.append(f"posted {completed} completion repl{'y' if completed == 1 else 'ies'}")
        notes.append(f"reacted {reacted}")
    notes.extend(issues)
    return {"outcome": "done", "note": "; ".join(n for n in notes if n)}


if __name__ == "__main__":
    try:
        result = main()
    except Fail as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result))
