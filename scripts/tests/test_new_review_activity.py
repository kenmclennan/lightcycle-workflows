import json
import os
import subprocess
import sys
import unittest
from datetime import datetime

from tests.harness import SCRIPTS, ScriptCase

TODAY = datetime.now().astimezone().date().isoformat()
THROUGH = "2026-10-19"

LC = """#!%(python)s
import os, sys
args = sys.argv[1:]
with open(os.environ["T_LOG"], "a") as log:
    log.write(" ".join(args) + "\\n")
if args[0] == "review-yield":
    if os.environ.get("T_YIELD_FAILS"):
        sys.stderr.write("engine too old\\n"); sys.exit(2)
    sys.stdout.write(os.environ["T_YIELD"])
elif args[0] == "search":
    sys.stdout.write(os.environ.get("T_SEARCH", ""))
""" % {"python": sys.executable}


def report(verdicts=(), escapes=(), unattributed=()):
    return {
        "since": THROUGH,
        "stages": [
            {
                "workflow": "w/x",
                "stage": "s",
                "verdict_rows": [{"step": step, "item": "LC-1", "closed_at": at} for step, at in verdicts],
                "escape_rows": list(escapes),
            }
        ],
        "unattributed_escapes": list(unattributed),
        "undeclared_steps": 0,
    }


class NewReviewActivityTest(ScriptCase):
    def setUp(self):
        super().setUp()
        path = self.bin / "lc"
        path.write_text(LC)
        path.chmod(0o755)
        self.log = self.root / "lc-calls.log"

    def guard(self, yield_report=None, last_state=None, search="", floor="0.5", repeat_min="3", fails=False):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        env.update(T_LOG=str(self.log), T_YIELD=json.dumps(yield_report or report()), T_SEARCH=search)
        if fails:
            env["T_YIELD_FAILS"] = "1"
        for key, value in (("CATCH_RATE_FLOOR", floor), ("REPEAT_MIN", repeat_min)):
            env.pop("LC_SCHEDULE_PARAM_" + key, None)
            if value:
                env["LC_SCHEDULE_PARAM_" + key] = value
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "new-review-activity.py")],
            env=env,
            input=json.dumps({"schedule": "review-yield", "last_state": last_state}),
            capture_output=True,
            text=True,
        )

    def calls(self):
        return self.log.read_text() if self.log.exists() else ""

    def test_missing_floor_is_a_violation_before_any_lc_call(self):
        result = self.guard(floor="")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("catch-rate-floor", result.stderr)
        self.assertEqual(self.calls(), "")

    def test_missing_repeat_min_is_a_violation_before_any_lc_call(self):
        result = self.guard(repeat_min="")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("repeat-min", result.stderr)
        self.assertEqual(self.calls(), "")

    def test_first_firing_omits_since_and_passes_with_none(self):
        out = json.loads(self.guard(report(verdicts=[("LC-1.4", TODAY)])).stdout)

        self.assertEqual(out["outcome"], "pass")
        self.assertNotIn("--since", self.calls())
        self.assertIn("since: none", out["description"])
        self.assertIn("previous: none", out["description"])
        self.assertIn("floor: 0.5", out["description"])
        self.assertIn("repeat-min: 3", out["description"])
        self.assertEqual(json.loads(out["state"]), {"through": TODAY, "boundary": ["LC-1.4"]})

    def test_only_boundary_day_rows_already_counted_fails(self):
        state = json.dumps({"through": THROUGH, "boundary": ["LC-1.4"]})

        out = json.loads(self.guard(report(verdicts=[("LC-1.4", THROUGH)]), last_state=state).stdout)

        self.assertEqual(out["outcome"], "fail")
        self.assertIn("--since " + THROUGH, self.calls())

    def test_new_row_after_boundary_passes_and_names_counted_keys(self):
        state = json.dumps({"through": THROUGH, "boundary": ["LC-1.4"]})
        verdicts = [("LC-1.4", THROUGH), ("LC-2.4", TODAY)]
        search = "LC-77   done   proj   Review yield - 2026-10-19\nLC-9   done   proj   Review yield - 2026-10-12\nLC-80   running   proj   Review yield - x\n"

        out = json.loads(self.guard(report(verdicts=verdicts), last_state=state, search=search).stdout)

        self.assertEqual(out["outcome"], "pass")
        self.assertIn("since: " + THROUGH, out["description"])
        self.assertIn("already-counted: LC-1.4", out["description"])
        self.assertIn("previous: LC-77", out["description"])

    def test_post_merge_escape_counts_as_new(self):
        state = json.dumps({"through": THROUGH, "boundary": []})
        escape = {"kind": "post-merge", "item": "LC-5", "linked_item": "LC-3", "at": TODAY}

        out = json.loads(self.guard(report(unattributed=[escape]), last_state=state).stdout)

        self.assertEqual(out["outcome"], "pass")
        self.assertEqual(json.loads(out["state"])["boundary"], ["LC-5|LC-3"])

    def test_no_rows_fails(self):
        out = json.loads(self.guard(report()).stdout)

        self.assertEqual(out["outcome"], "fail")

    def test_review_yield_failure_is_a_violation(self):
        result = self.guard(fails=True)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("engine too old", result.stderr)


if __name__ == "__main__":
    unittest.main()
