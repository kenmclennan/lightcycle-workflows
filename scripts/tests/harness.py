import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent

GH_STUB = """#!%(python)s
import json, os, re, sys
state_path = os.environ["STUB_DIR"] + "/gh-state.json"
log_path = os.environ["STUB_DIR"] + "/gh-calls.jsonl"
state = json.load(open(state_path))
args = sys.argv[1:]
if args[0] == "stack":
    with open(log_path, "a") as log:
        log.write(json.dumps({"method": "STACK", "path": " ".join(args[1:]), "fields": {}}) + "\\n")
    cfg = state.get("stack")
    sub = args[1]
    if sub == "view":
        if not cfg or not cfg.get("branches"):
            sys.stderr.write("not in a stack\\n"); sys.exit(1)
        print(json.dumps({"trunk": "main", "branches": [{"name": n} for n in cfg["branches"]]}))
    elif sub == "rebase":
        sys.exit(cfg.get("rebase_rc", 0))
    elif sub == "unstack":
        cfg.pop("github", None)
        json.dump(state, open(state_path, "w"))
    elif sub == "init":
        pass
    elif sub == "submit":
        rc = cfg.get("submit_rc", 0)
        if rc:
            sys.stderr.write("stacks are not enabled\\n"); sys.exit(rc)
        for name in cfg["branches"]:
            if not any(p.get("head") == name for p in state["pulls"]):
                num = len(state["pulls"]) + 1
                state["pulls"].append({"number": num, "html_url": "https://github.com/o/r/pull/%%d" %% num,
                                       "title": "auto " + name, "body": "auto body", "head": name})
        json.dump(state, open(state_path, "w"))
        print("Stack: https://github.com/o/r/stack/%%d" %% cfg.get("submit_stack", 7))
    sys.exit(0)
assert args[0] == "api"
method, fields, path = None, {}, None
gh_stack = (state.get("stack") or {}).get("github")
i = 1
while i < len(args):
    a = args[i]
    if a == "-X":
        method = args[i + 1]; i += 2
    elif a in ("-f", "-F"):
        key, _, value = args[i + 1].partition("=")
        if a == "-F" and value.startswith("@"):
            value = open(value[1:]).read()
        fields[key] = value; i += 2
    elif a.startswith("--"):
        i += 1
    else:
        path = a; i += 1
method = method or ("POST" if fields else "GET")
with open(log_path, "a") as log:
    log.write(json.dumps({"method": method, "path": path, "fields": fields}) + "\\n")

def save():
    json.dump(state, open(state_path, "w"))

def out(value):
    print(json.dumps(value))

bare = path.split("?")[0]
if method == "GET" and re.search(r"/stacks/\\d+$", bare):
    if not gh_stack:
        sys.stderr.write("gh: HTTP 404\\n"); sys.exit(1)
    out({"base": {"ref": "main"}, "pull_requests": [
        {"number": p["number"], "state": p.get("state", "open"), "head": {"ref": p["head"], "sha": "x"}}
        for h in gh_stack["heads"] for p in state["pulls"] if p["head"] == h]})
elif method == "DELETE":
    out({})
elif method == "GET" and bare.endswith("/pulls"):
    wanted = path.partition("head=")[2].partition("&")[0].partition(":")[2]
    out([p for p in state["pulls"] if not wanted or p.get("head", wanted) == wanted])
elif method == "POST" and bare.endswith("/pulls"):
    if state.get("create_error"):
        if state.get("create_server_side"):
            num = len(state["pulls"]) + 1
            state["pulls"].append({"number": num, "html_url": "https://github.com/o/r/pull/%%d" %% num,
                                   "title": fields["title"], "body": fields["body"], "head": fields["head"]})
            save()
        sys.stderr.write("gh: HTTP 502\\n"); sys.exit(1)
    num = len(state["pulls"]) + 1
    pull = {"number": num, "html_url": "https://github.com/o/r/pull/%%d" %% num,
            "title": fields["title"], "body": fields["body"], "head": fields["head"]}
    state["pulls"].append(pull); save(); out(pull)
elif re.search(r"/pulls/\\d+$", bare):
    num = int(bare.rsplit("/", 1)[1])
    pull = next(p for p in state["pulls"] if p["number"] == num)
    if method == "PATCH":
        pull.update(fields); save()
    out(pull)
elif method == "GET" and re.search(r"/issues/\\d+/comments$", bare):
    out(state.get("issue_comments", []))
elif method == "GET" and re.search(r"/pulls/\\d+/comments$", bare):
    out(state.get("review_comments", []))
elif method == "GET" and re.search(r"/pulls/\\d+/reviews$", bare):
    out(state.get("reviews", []))
elif method == "POST":
    out({"id": 999})
else:
    sys.stderr.write("stub gh: unhandled %%s %%s\\n" %% (method, path)); sys.exit(2)
""" % {"python": sys.executable}

LC_STUB = """#!%(python)s
import json, os, sys
stub = os.environ["STUB_DIR"]
args = sys.argv[1:]
if args[0] == "show":
    print(open(stub + "/lc-show.json").read())
elif args[0] == "attach":
    with open(stub + "/lc-calls.jsonl", "a") as log:
        log.write(json.dumps(args) + "\\n")
else:
    sys.exit(2)
""" % {"python": sys.executable}


def sh(*args, cwd=None, check=True):
    return subprocess.run(args, cwd=cwd, check=check, capture_output=True, text=True)


class ScriptCase(unittest.TestCase):
    item = "LC-1"
    step = "LC-1.4"
    base_branch = "main"

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.stub = self.root / "stub"
        self.bin = self.root / "bin"
        self.stub.mkdir()
        self.bin.mkdir()
        self.origin = self.root / "origin" / "repo.git"
        self.origin.parent.mkdir()
        sh("git", "init", "--bare", "-b", self.base_branch, str(self.origin))
        self.work = self.root / "work"
        sh("git", "clone", str(self.origin), str(self.work))
        sh("git", "config", "user.name", "Tester", cwd=self.work)
        sh("git", "config", "user.email", "t@example.com", cwd=self.work)
        sh("git", "checkout", "-b", self.base_branch, cwd=self.work, check=False)
        self.commit("README.md", "base\n", "chore: base")
        sh("git", "push", "-u", "origin", self.base_branch, cwd=self.work)
        for name, body in (("gh", GH_STUB), ("lc", LC_STUB)):
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)
        self.gh_state = {"pulls": []}
        self.write_gh_state()
        self.lc_show = {
            "item": self.item,
            "pass": "p1",
            "phase": "code",
            "valid_outcomes": ["done", "conflicted"],
            "inputs": {"previous": {"stage": "write-code", "report": "built the thing"}},
            "runs": [{"pass": "p1", "phase": "code", "pr": None}],
        }
        self.write_lc_show()

    def commit(self, name, content, message):
        (self.work / name).write_text(content)
        sh("git", "add", name, cwd=self.work)
        sh("git", "commit", "-m", message, cwd=self.work)

    def feature_branch(self, name="feat/x"):
        sh("git", "checkout", "-b", name, cwd=self.work)
        self.commit("feature.txt", "one\n", "feat(x): add the thing\n\nbody line")
        return name

    def write_gh_state(self):
        (self.stub / "gh-state.json").write_text(json.dumps(self.gh_state))

    def write_lc_show(self):
        (self.stub / "lc-show.json").write_text(json.dumps(self.lc_show))

    def read_gh_state(self):
        return json.loads((self.stub / "gh-state.json").read_text())

    def gh_calls(self):
        path = self.stub / "gh-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def lc_calls(self):
        path = self.stub / "lc-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def run_script(self, name, extra_env=None):
        env = dict(os.environ)
        env["LC_WORKFLOW_CONFIG_LAYER_LINES_LIMIT"] = "400"
        for key, value in (extra_env or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env["STUB_DIR"] = str(self.stub)
        env["LC_STEP"] = self.step
        env["LC_ITEM"] = self.item
        env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            [sys.executable, str(SCRIPTS / name)],
            cwd=self.work,
            env=env,
            input="{}",
            capture_output=True,
            text=True,
        )
