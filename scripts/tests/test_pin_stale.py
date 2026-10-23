import json
import os
import subprocess
import sys
import unittest

from tests.harness import SCRIPTS, ScriptCase

PIN = "a" * 40
MAIN = "b" * 40
OLD_ITEM_PIN = "c" * 40

CLAUDE_MD = (
    "# x\n\n## Engine pin\n\nThe pin is `ENGINE_PIN` in `.github/workflows/simulate.yml`.\n"
    "- ENGINE_REPO, the engine repo the pin points into, is `acme/engine`.\n\n## Other\n\nnope\n"
)
CLAUDE_MD_NO_ENGINE_REPO = "# x\n\n## Engine pin\n\nThe pin is `ENGINE_PIN` in `.github/workflows/simulate.yml`.\n\n## Other\n\nnope\n"
WORKFLOW = "env:\n  ENGINE_PIN: %s\nsteps:\n  - run: |\n      threshold=20\n" % PIN

GH = """#!%(python)s
import base64, json, os, sys
args = sys.argv[1:]
path = args[1]
files = {"CLAUDE.md": os.environ["T_CLAUDE"], ".github/workflows/simulate.yml": os.environ["T_WORKFLOW"]}
if "/contents/" in path:
    print(json.dumps({"content": base64.b64encode(files[path.split("/contents/")[1]].encode()).decode()}))
elif "/compare/" in path:
    if not path.startswith("repos/acme/engine/"):
        sys.exit(2)
    print(os.environ["T_AHEAD"])
elif path.endswith("/commits/main"):
    print(os.environ["T_MAIN"])
else:
    sys.exit(2)
""" % {"python": sys.executable}

LC = """#!%(python)s
import os, sys
sys.stdout.write(os.environ.get("T_SEARCH", ""))
""" % {"python": sys.executable}


class PinStaleTest(ScriptCase):
    def setUp(self):
        super().setUp()
        for name, body in (("gh", GH), ("lc", LC)):
            path = self.bin / name
            path.write_text(body)
            path.chmod(0o755)

    def guard(self, ahead, last_state=None, search="", repo="o/r", claude=CLAUDE_MD):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env.update(T_CLAUDE=claude, T_WORKFLOW=WORKFLOW, T_AHEAD=str(ahead), T_MAIN=MAIN, T_SEARCH=search)
        if repo:
            env["LC_SCHEDULE_PARAM_REPO"] = repo
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "pin-stale.py")],
            env=env,
            input=json.dumps({"schedule": "bump-engine-pin", "last_state": last_state}),
            capture_output=True,
            text=True,
        )

    def test_past_threshold_passes_naming_pin_main_and_threshold(self):
        result = self.guard(21)

        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(out["title"], "bump the engine pin (21 commits behind)")
        for needle in (PIN, MAIN, "threshold is 20"):
            self.assertIn(needle, out["description"])
        self.assertEqual(json.loads(out["state"]), {"pin": PIN, "main": MAIN})

    def test_at_threshold_fails(self):
        out = json.loads(self.guard(20).stdout)

        self.assertEqual(out["outcome"], "fail")

    def test_under_threshold_fails(self):
        out = json.loads(self.guard(3).stdout)

        self.assertEqual(out["outcome"], "fail")

    def test_earlier_item_still_open_fails_even_past_threshold(self):
        state = json.dumps({"pin": OLD_ITEM_PIN, "main": MAIN})
        search = "LC-9   running   proj   bump the engine pin (30 commits behind)\n"

        out = json.loads(self.guard(50, last_state=state, search=search).stdout)

        self.assertEqual(out["outcome"], "fail")
        self.assertIn("LC-9", out["note"])

    def test_earlier_item_done_allows_a_new_one(self):
        state = json.dumps({"pin": OLD_ITEM_PIN, "main": MAIN})
        search = "LC-9   done   proj   bump the engine pin (30 commits behind)\n"

        out = json.loads(self.guard(50, last_state=state, search=search).stdout)

        self.assertEqual(out["outcome"], "pass")

    def test_missing_engine_repo_line_is_a_violation(self):
        result = self.guard(50, claude=CLAUDE_MD_NO_ENGINE_REPO)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("ENGINE_REPO", result.stderr)

    def test_missing_repo_parameter_is_a_violation(self):
        result = self.guard(50, repo="")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
