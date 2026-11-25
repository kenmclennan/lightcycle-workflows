import json
import os
import subprocess
import unittest

from tests.harness import HangCase, ScriptCase, sh


class OpenPrTest(ScriptCase):
    def test_first_push_creates_the_pr_and_attaches_it(self):
        self.feature_branch()
        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")

        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(len(creates), 1)
        fields = creates[0]["fields"]
        self.assertEqual(fields["title"], "feat(x): add the thing")
        self.assertEqual(fields["base"], "main")
        self.assertEqual(fields["head"], "feat/x")
        self.assertTrue(fields["body"].startswith(f"<!-- lc:item={self.item} -->\n<!-- lc:body -->"))
        self.assertIn("body line", fields["body"])
        self.assertNotIn("Closing note", fields["body"])
        self.assertNotIn("built the thing", fields["body"])
        self.assertTrue(fields["body"].endswith("<!-- /lc:body -->"))
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])
        remote = sh("git", "ls-remote", "--heads", "origin", "feat/x", cwd=self.work).stdout
        self.assertIn("refs/heads/feat/x", remote)

    def test_rework_resync_replaces_only_the_marked_block(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        pull = state["pulls"][0]
        pull["body"] = "human above\n" + pull["body"] + "\nhuman below"
        self.gh_state = state
        self.write_gh_state()
        self.lc_show["inputs"]["previous"]["report"] = "second round note"
        self.lc_show["runs"][0]["pr"] = pull["html_url"]
        self.write_lc_show()
        (self.work / "feature.txt").write_text("two\n")
        sh("git", "add", "feature.txt", cwd=self.work)
        sh("git", "commit", "--amend", "-m", "feat(x): redesigned thing\n\nnew body", cwd=self.work)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.read_gh_state()["pulls"][0]
        self.assertTrue(after["body"].startswith("human above\n"))
        self.assertTrue(after["body"].endswith("\nhuman below"))
        self.assertIn("new body", after["body"])
        self.assertNotIn("second round note", after["body"])
        self.assertNotIn("body line", after["body"])
        self.assertNotIn("built the thing", after["body"])
        self.assertEqual(after["title"], "feat(x): redesigned thing")
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(len(creates), 1)

    def test_spec_phase_pr_keeps_the_closing_note(self):
        self.lc_show["phase"] = "spec"
        self.lc_show["runs"][0]["phase"] = "spec"
        self.write_lc_show()
        self.feature_branch()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.read_gh_state()["pulls"][0]["body"]
        self.assertIn("## Closing note from write-code\n\nbuilt the thing", body)

    def message_branch(self, message):
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        self.commit("feature.txt", "one\n", message)

    def test_follow_ups_noticed_replaces_the_out_of_scope_label_in_the_body_only(self):
        self.message_branch("feat(x): add the thing\n\nbody line\n\nAlso found, out of scope: a stale label in util.")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.read_gh_state()["pulls"][0]["body"]
        self.assertIn("Follow-ups noticed: a stale label in util.", body)
        self.assertNotIn("Also found", body)
        pushed = sh("git", "log", "-1", "--format=%B", "origin/feat/x", cwd=self.work).stdout
        self.assertIn("Also found, out of scope: a stale label in util.", pushed)

    def test_tested_blocks_are_dropped_and_check_by_hand_is_kept(self):
        self.message_branch(
            "fix(deps): bump x to 3.0.7\n\nBumped x.\n\nTested:\n- unit suite\n  - nested\n\n"
            "Not tested here:\n- the packaged app\n\nCheck by hand: open the packaged app."
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.read_gh_state()["pulls"][0]["body"]
        self.assertIn("Bumped x.", body)
        self.assertIn("Check by hand: open the packaged app.", body)
        self.assertNotIn("Tested:", body)
        self.assertNotIn("Not tested here", body)
        self.assertNotIn("unit suite", body)
        self.assertNotIn("packaged app\n- ", body)

    def test_pipeline_word_in_the_commit_message_fails_the_stage(self):
        self.message_branch("feat(x): add the thing\n\nThis is routed to the reviewer.")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("routed", result.stderr)
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])
        remote = sh("git", "ls-remote", "--heads", "origin", "feat/x", cwd=self.work).stdout
        self.assertEqual(remote, "")

    def test_pipeline_word_check_names_the_previous_stage(self):
        self.message_branch("feat(x): add the thing\n\nBuilt in write-code.")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("write-code", result.stderr)

    def test_pipeline_word_check_is_whole_word(self):
        self.message_branch("feat(x): add the thing\n\nA specification of respect, a finding-aid and a spec-like thing.")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resync_leaves_a_body_without_markers_alone(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        state["pulls"][0]["body"] = "written by a human"
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        patches = [c for c in self.gh_calls() if c["method"] == "PATCH"]
        self.assertFalse([p for p in patches if "body" in p["fields"]])
        self.assertEqual(self.read_gh_state()["pulls"][0]["body"], "written by a human")

    def test_resync_adds_the_item_marker_when_absent(self):
        self.feature_branch()
        state = self.read_gh_state()
        state["pulls"].append({
            "number": 1,
            "html_url": "https://github.com/o/r/pull/1",
            "title": "feat(x): add the thing",
            "body": "<!-- lc:body -->\nold\n<!-- /lc:body -->",
        })
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.read_gh_state()["pulls"][0]["body"]
        self.assertTrue(body.startswith(f"<!-- lc:item={self.item} -->\n<!-- lc:body -->"))

    def test_failed_push_is_a_failure_with_no_outcome(self):
        self.feature_branch()
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho rejected by test >&2\nexit 1\n")
        hook.chmod(0o755)

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("rejected by test", result.stderr)
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])
        self.assertEqual(self.lc_calls(), [])

    def test_rebase_conflict_prints_conflicted_when_declared(self):
        self.commit("clash.txt", "main side\n", "chore: main change")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "conflicted")
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work).stdout, "")

    def test_rebase_conflict_fails_when_no_conflicted_outcome(self):
        self.lc_show["valid_outcomes"] = ["done"]
        self.write_lc_show()
        self.commit("clash.txt", "main side\n", "chore: main change")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("clash.txt", result.stderr)

    def test_rebase_failure_without_conflicts_fails_with_its_output(self):
        self.commit("later.txt", "later\n", "chore: main moves")
        sh("git", "push", "origin", "main", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("feature.txt", "one\n", "feat(x): add the thing")
        hook = self.work / ".git" / "hooks" / "pre-rebase"
        hook.write_text("#!/bin/sh\necho refused by test >&2\nexit 1\n")
        hook.chmod(0o755)

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("conflicted", result.stdout)
        self.assertIn("no conflicted paths", result.stderr)
        self.assertIn("origin/main", result.stderr)
        self.assertIn("refused by test", result.stderr)

    def test_branch_tip_amended_from_a_base_merge_commit_is_refused(self):
        sh("git", "checkout", "-b", "side", cwd=self.work)
        self.commit("side.txt", "side\n", "chore: side work")
        sh("git", "checkout", "main", cwd=self.work)
        self.commit("main.txt", "main\n", "chore: main work")
        sh("git", "merge", "--no-ff", "side", "-m", "Merge pull request #88", cwd=self.work)
        sh("git", "push", "origin", "main", cwd=self.work)
        merge = sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()
        sh("git", "checkout", "-b", "feat/x", cwd=self.work)
        (self.work / "feature.txt").write_text("one\n")
        sh("git", "add", "feature.txt", cwd=self.work)
        sh("git", "commit", "--amend", "-m", "feat(x): add the thing", cwd=self.work)
        amended = sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()
        self.assertEqual(sh("git", "rev-list", "--merges", "origin/main..HEAD", cwd=self.work).stdout.split(), [amended])

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(amended, result.stderr)
        self.assertIn("git reflog", result.stderr)
        self.assertIn("git reset --keep", result.stderr)
        self.assertNotEqual(amended, merge)
        self.assertEqual(sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip(), amended)
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work).stdout, "")
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])

    def test_origin_default_moved_after_clone_is_followed(self):
        self.feature_branch()
        sh("git", "branch", "-m", "main", "trunk", cwd=self.origin)

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(creates[0]["fields"]["base"], "trunk")
        head = sh("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=self.work).stdout.strip()
        self.assertEqual(head, "origin/trunk")

    def test_existing_pr_not_recorded_on_the_run_is_attached(self):
        self.feature_branch()
        state = self.read_gh_state()
        state["pulls"].append({
            "number": 1,
            "html_url": "https://github.com/o/r/pull/1",
            "title": "feat(x): add the thing",
            "body": "<!-- lc:body -->\nold\n<!-- /lc:body -->",
        })
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_existing_pr_already_recorded_is_not_attached_again(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/1"
        self.write_lc_show()
        (self.stub / "lc-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [])

    def test_rebase_in_progress_is_aborted_and_the_run_completes(self):
        self.feature_branch()
        sh("git", "fetch", "origin", cwd=self.work)
        env = {**os.environ, "GIT_SEQUENCE_EDITOR": "perl -pi -e 's/^pick/edit/'"}
        subprocess.run(
            ["git", "rebase", "-i", "origin/main"], cwd=self.work, env=env, check=True, capture_output=True
        )
        self.assertEqual(sh("git", "branch", "--show-current", cwd=self.work).stdout.strip(), "")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(sh("git", "branch", "--show-current", cwd=self.work).stdout.strip(), "feat/x")
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_recorded_pr_without_a_branch_pr_is_a_divergence(self):
        self.feature_branch()
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/9"
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("pull/9", result.stderr)
        self.assertFalse([c for c in self.gh_calls() if c["method"] == "POST"])

    def test_newest_run_of_the_pass_and_phase_decides_the_recorded_pr(self):
        self.feature_branch()
        older = dict(self.lc_show["runs"][0], id="older", pr="https://github.com/o/r/pull/9")
        newer = dict(self.lc_show["runs"][0], id="newer", pr=None)
        self.lc_show["runs"] = [older, newer]
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_create_error_that_succeeded_server_side_is_used(self):
        self.feature_branch()
        self.gh_state.update(create_error=True, create_server_side=True)
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.lc_calls(), [["attach", self.item, "pr", "https://github.com/o/r/pull/1"]])

    def test_create_error_with_no_pr_fails(self):
        self.feature_branch()
        self.gh_state.update(create_error=True)
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.lc_calls(), [])

    def test_stale_local_branch_is_reset_to_the_remote_head(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        local = sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()
        other = self.root / "other"
        sh("git", "clone", "-b", "feat/x", str(self.origin), str(other))
        sh("git", "config", "user.name", "T", cwd=other)
        sh("git", "config", "user.email", "t@example.com", cwd=other)
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(x): remote advance", cwd=other)
        sh("git", "push", "origin", "feat/x", cwd=other)
        remote = sh("git", "rev-parse", "HEAD", cwd=other).stdout.strip()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        note = json.loads(result.stdout)["note"]
        self.assertIn(local, note)
        self.assertIn(remote, note)
        self.assertEqual(sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip(), remote)

    def test_stale_local_branch_with_dirty_tree_fails(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        other = self.root / "other"
        sh("git", "clone", "-b", "feat/x", str(self.origin), str(other))
        sh("git", "config", "user.name", "T", cwd=other)
        sh("git", "config", "user.email", "t@example.com", cwd=other)
        (other / "more.txt").write_text("more\n")
        sh("git", "add", "more.txt", cwd=other)
        sh("git", "commit", "-m", "feat(x): remote advance", cwd=other)
        sh("git", "push", "origin", "feat/x", cwd=other)
        (self.work / "scratch.txt").write_text("dirty\n")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("scratch.txt", result.stderr)

    def test_untracked_file_refuses_to_open_a_pr(self):
        self.feature_branch()
        (self.work / "digest.md").write_text("late\n")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("digest.md", result.stderr)
        self.assertIn("uncommitted changes", result.stderr)
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.lc_calls(), [])

    def test_uncommitted_digest_alone_is_amended_into_the_commit(self):
        self.feature_branch()
        (self.work / f"{self.item}-digest.md").write_text("late digest\n")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("amended the uncommitted digest", result.stderr)
        self.assertEqual(
            sh("git", "show", f"HEAD:{self.item}-digest.md", cwd=self.work).stdout, "late digest\n"
        )
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work).stdout, "")
        self.assertEqual(sh("git", "rev-list", "--count", "origin/main..HEAD", cwd=self.work).stdout.strip(), "1")

    def test_digest_with_another_uncommitted_path_is_refused(self):
        self.feature_branch()
        (self.work / f"{self.item}-digest.md").write_text("late digest\n")
        (self.work / "scratch.txt").write_text("dirty\n")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncommitted changes", result.stderr)
        self.assertEqual(self.gh_calls(), [])

    def test_uncommitted_edit_refuses_to_update_an_open_pr(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        (self.work / "feature.txt").write_text("edited\n")
        (self.stub / "gh-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("feature.txt", result.stderr)
        self.assertEqual(self.gh_calls(), [])


class OpenPrNonMainBaseTest(ScriptCase):
    base_branch = "master"

    def test_pr_base_and_rebase_use_the_default_branch(self):
        self.commit("later.txt", "later\n", "chore: base moves")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("feature.txt", "one\n", "feat(x): add the thing")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        creates = [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith("/pulls")]
        self.assertEqual(creates[0]["fields"]["base"], "master")
        base = sh("git", "merge-base", "origin/master", "HEAD", cwd=self.work).stdout.strip()
        self.assertEqual(base, sh("git", "rev-parse", "origin/master", cwd=self.work).stdout.strip())

    def test_rebase_conflict_names_the_default_branch(self):
        self.lc_show["valid_outcomes"] = ["done"]
        self.write_lc_show()
        self.commit("clash.txt", "base side\n", "chore: base change")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("origin/master", result.stderr)
        self.assertIn("clash.txt", result.stderr)

    def test_rebase_conflict_prints_conflicted_when_declared(self):
        self.commit("clash.txt", "base side\n", "chore: base change")
        sh("git", "push", "origin", "master", cwd=self.work)
        sh("git", "checkout", "-b", "feat/x", "HEAD~1", cwd=self.work)
        self.commit("clash.txt", "branch side\n", "feat(x): clash")

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "conflicted")


class CompletionRepliesTest(ScriptCase):
    def decision(self, key, sha, decision="rework", path=None, watched="LC-1.3"):
        value = {"decision": decision, "sha": sha, "path": path, "watched": watched}
        return {"name": "feedback-decision", "label": key, "value": json.dumps(value)}

    def completed(self, key, sha="a" * 40):
        return {"name": "feedback-completed", "label": key, "value": sha}

    def inline(self, cid, login="operator", reply_to=None):
        comment = {
            "id": cid,
            "created_at": "2000-01-01T00:00:00Z",
            "user": {"login": login},
            "html_url": f"https://github.com/o/r/pull/1#discussion_r{cid}",
            "body": "bump it to 3.0.7",
        }
        if reply_to:
            comment["in_reply_to_id"] = reply_to
        return comment

    def seed(self, records, **lists):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        state = self.read_gh_state()
        state.update(lists)
        self.gh_state = state
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = records
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/1"
        self.write_lc_show()
        (self.stub / "gh-calls.jsonl").unlink()
        (self.stub / "lc-calls.jsonl").unlink(missing_ok=True)
        self.assertTrue(
            records and any(r["name"] == "feedback-decision" for r in records),
            "the seeded decision must be in the stubbed inputs.item",
        )

    def head(self):
        return sh("git", "rev-parse", "HEAD", cwd=self.work).stdout.strip()

    def posts(self, suffix):
        return [c for c in self.gh_calls() if c["method"] == "POST" and c["path"].endswith(suffix)]

    def replies(self):
        return [
            c for c in self.gh_calls()
            if c["method"] == "POST" and ("/replies" in c["path"] or c["path"].endswith("/issues/1/comments"))
        ]

    def completions(self):
        return [c for c in self.lc_calls() if "feedback-completed" in c]

    def test_mixed_case_completes_only_the_decisions_with_a_new_push(self):
        old = "b" * 40
        self.seed(
            [
                self.decision("mention:11", old),
                self.completed("mention:11"),
                self.decision("mention:12", "HEAD-PLACEHOLDER"),
                self.decision("inline:21", old, path="feature.txt"),
            ],
            issue_comments=[],
            review_comments=[self.inline(21, login="operator")],
            reviews=[],
        )
        records = self.lc_show["inputs"]["item"]
        records[2] = self.decision("mention:12", self.head())
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c[4] for c in self.completions()], ["inline:21"])
        self.assertEqual(len(self.replies()), 1)
        self.assertTrue(self.replies()[0]["path"].endswith("/pulls/1/comments/21/replies"))
        reactions = [c for c in self.gh_calls() if c["path"].endswith("/reactions")]
        self.assertEqual(len(reactions), 1)
        self.assertTrue(reactions[0]["path"].endswith("/pulls/comments/21/reactions"))

    def test_completion_reply_opens_with_the_robot_emoji(self):
        self.seed(
            [self.decision("inline:31", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(31)],
            reviews=[],
        )

        self.run_script("open-pr.py")

        body = self.replies()[0]["fields"]["body"]
        self.assertTrue(body.startswith("\U0001F916 <!-- lc -->\n"))
        self.assertNotIn("lc:completes", body)
        self.assertNotIn("does not verify", body)
        self.assertNotIn("AUTOMATED", body)

    def test_reply_stays_in_thread_when_the_root_is_the_authenticated_login(self):
        self.seed(
            [self.decision("inline:71", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(70, "operator"), self.inline(71, "lc-bot", reply_to=70)],
            reviews=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        posted = self.replies()
        self.assertEqual(len(posted), 1)
        self.assertTrue(posted[0]["path"].endswith("/pulls/1/comments/71/replies"))

    def test_reply_goes_top_level_when_the_root_is_someone_else(self):
        self.seed(
            [self.decision("inline:81", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(80, "reviewer"), self.inline(81, reply_to=80)],
            reviews=[],
            review_threads=[{"id": "T9", "comments": [80, 81]}],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        posted = self.replies()
        self.assertEqual(len(posted), 1)
        self.assertTrue(posted[0]["path"].endswith("/issues/1/comments"))
        body = posted[0]["fields"]["body"]
        self.assertTrue(body.startswith("\U0001F916"))
        self.assertIn("https://github.com/o/r/pull/1#discussion_r81", body)
        self.assertFalse([c for c in self.gh_calls() if "/replies" in c["path"]])
        self.assertFalse([c for c in self.gh_calls() if "resolveReviewThread" in c["fields"].get("query", "")])

    def test_mixed_threads_reply_in_one_and_top_level_in_the_other(self):
        self.seed(
            [
                self.decision("inline:71", "b" * 40, path="feature.txt"),
                self.decision("inline:81", "b" * 40, path="feature.txt"),
            ],
            issue_comments=[],
            review_comments=[
                self.inline(70, "operator"),
                self.inline(71, reply_to=70),
                self.inline(80, "reviewer"),
                self.inline(81, reply_to=80),
            ],
            reviews=[],
            review_threads=[{"id": "T1", "comments": [70, 71]}],
        )

        self.run_script("open-pr.py")

        posted = self.replies()
        self.assertEqual(len(posted), 2)
        self.assertEqual(sum(1 for c in posted if c["path"].endswith("/replies")), 1)
        self.assertEqual(sum(1 for c in posted if c["path"].endswith("/issues/1/comments")), 1)

    def test_unreadable_root_or_login_posts_top_level(self):
        self.seed(
            [self.decision("inline:91", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(91, reply_to=999)],
            reviews=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.replies()[0]["path"].endswith("/issues/1/comments"))

        state = self.read_gh_state()
        state.update(
            review_comments=[self.inline(70, "operator"), self.inline(71, reply_to=70)],
            user_error=True,
        )
        self.gh_state = state
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [self.decision("inline:71", "b" * 40, path="feature.txt")]
        self.write_lc_show()
        (self.stub / "gh-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.replies()[0]["path"].endswith("/issues/1/comments"))

    def test_top_level_request_gets_a_reaction_and_no_reply(self):
        self.seed(
            [self.decision("mention:31", "b" * 40)],
            issue_comments=[{"id": 31, "user": {"login": "operator"}, "body": "@lc do it"}],
            review_comments=[],
            reviews=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.replies(), [])
        self.assertEqual(len(self.posts("/issues/comments/31/reactions")), 1)
        self.assertEqual(self.posts("/issues/comments/31/reactions")[0]["fields"], {"content": "+1"})
        self.assertEqual(len(self.completions()), 1)

    def test_review_request_gets_a_reaction_and_no_reply(self):
        review = {"id": 41, "node_id": "PRR_41", "body": "please change"}
        self.seed([self.decision("review:41", "b" * 40)], issue_comments=[], review_comments=[], reviews=[review])

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.replies(), [])
        mutations = [c for c in self.gh_calls() if "addReaction" in c["fields"].get("query", "")]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0]["fields"]["subject"], "PRR_41")
        self.assertEqual(mutations[0]["fields"]["content"], "THUMBS_UP")

    def test_all_completed_posts_nothing(self):
        self.seed(
            [self.decision("mention:51", "b" * 40), self.completed("mention:51")],
            issue_comments=[],
            review_comments=[],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual(self.replies(), [])
        self.assertEqual([c for c in self.gh_calls() if c["method"] == "POST"], [])
        self.assertEqual(self.lc_calls(), [])

    def test_none_completed_completes_every_eligible(self):
        self.seed(
            [
                self.decision("mention:61", "b" * 40),
                self.decision("mention:62", "b" * 40),
                self.decision("inline:63", "b" * 40, path="feature.txt"),
            ],
            issue_comments=[],
            review_comments=[self.inline(63)],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual(len(self.completions()), 3)

    def test_decision_without_a_new_push_is_not_completed(self):
        self.seed([self.decision("mention:71", "x")], issue_comments=[], review_comments=[], reviews=[])
        self.lc_show["inputs"]["item"] = [self.decision("mention:71", self.head())]
        self.write_lc_show()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c for c in self.gh_calls() if c["method"] == "POST"], [])
        self.assertEqual(self.lc_calls(), [])

    def test_decision_with_a_completion_record_is_not_completed_again(self):
        self.seed(
            [self.decision("inline:72", "b" * 40, path="feature.txt"), self.completed("inline:72")],
            issue_comments=[],
            review_comments=[self.inline(72)],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual([c for c in self.gh_calls() if c["method"] == "POST"], [])
        self.assertEqual(self.lc_calls(), [])

    def test_answer_and_ignore_decisions_are_never_completed(self):
        self.seed(
            [
                self.decision("mention:73", "b" * 40, decision="answer", watched=None),
                self.decision("mention:74", "b" * 40, decision="ignore", watched=None),
            ],
            issue_comments=[],
            review_comments=[],
            reviews=[],
        )

        self.run_script("open-pr.py")

        self.assertEqual(self.lc_calls(), [])

    def test_completion_does_not_post_twice_after_a_partial_failure(self):
        short = None
        self.seed(
            [self.decision("inline:75", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(74, "operator"), self.inline(75, "operator", reply_to=74)],
            reviews=[],
        )
        short = self.head()[:7]
        state = self.read_gh_state()
        state["review_comments"].append({
            "id": 76,
            "in_reply_to_id": 74,
            "user": {"login": "operator"},
            "body": f"\U0001F916 <!-- lc -->\nDone in {short}: feat(x): add the thing.",
        })
        self.gh_state = state
        self.write_gh_state()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.replies(), [])
        self.assertEqual(len(self.completions()), 1)

    def test_inline_completion_resolves_the_thread_and_records_it(self):
        self.seed(
            [self.decision("inline:77", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(77, "operator")],
            reviews=[],
            review_threads=[{"id": "T-77", "comments": [77]}],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.gh_calls()
        order = [
            "reply" if "/replies" in c["path"] else
            "resolve" if "resolveReviewThread" in c["fields"].get("query", "") else
            "react" if c["path"].endswith("/reactions") else None
            for c in calls if c["method"] == "POST"
        ]
        self.assertEqual([o for o in order if o], ["reply", "resolve", "react"])
        resolve = next(c for c in calls if "resolveReviewThread" in c["fields"].get("query", ""))
        self.assertEqual(resolve["fields"]["thread"], "T-77")
        self.assertEqual(self.completions(), [["attach", self.item, "feedback-completed", "--label", "inline:77", self.head()]])
        self.assertIn("posted 1 completion reply", json.loads(result.stdout)["note"])

    def test_resolve_is_skipped_when_the_thread_is_not_found(self):
        self.seed(
            [self.decision("inline:78", "b" * 40, path="feature.txt")],
            issue_comments=[],
            review_comments=[self.inline(78, "operator")],
            reviews=[],
            review_threads=[],
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not found", json.loads(result.stdout)["note"])
        self.assertFalse([c for c in self.gh_calls() if "resolveReviewThread" in c["fields"].get("query", "")])
        self.assertEqual(len(self.completions()), 1)

    def test_a_failed_reaction_does_not_fail_the_stage(self):
        self.seed(
            [self.decision("mention:79", "b" * 40)],
            issue_comments=[],
            review_comments=[],
            reviews=[],
            reaction_error=True,
        )

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reaction on mention:79 failed", json.loads(result.stdout)["note"])
        self.assertEqual(len(self.completions()), 1)

    def test_replay_of_lightcycle_1287_one_inline_request(self):
        self.feature_branch()
        self.assertEqual(self.run_script("open-pr.py").returncode, 0)
        before = self.head()
        self.commit("deps.txt", "x 3.0.7\n", "chore(deps): bump x to 3.0.7")
        state = self.read_gh_state()
        state.update(
            issue_comments=[],
            review_comments=[self.inline(1287, "operator")],
            reviews=[],
            review_threads=[{"id": "T-1287", "comments": [1287]}],
        )
        self.gh_state = state
        self.write_gh_state()
        self.lc_show["inputs"]["item"] = [self.decision("inline:1287", before, path="feature.txt")]
        self.lc_show["runs"][0]["pr"] = "https://github.com/o/r/pull/1"
        self.write_lc_show()
        (self.stub / "gh-calls.jsonl").unlink()

        result = self.run_script("open-pr.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.gh_calls()
        short = self.head()[:7]
        self.assertEqual([c for c in calls if c["path"].endswith("/issues/1/comments") and c["method"] == "POST"], [])
        replies = [c for c in calls if c["path"].endswith("/pulls/1/comments/1287/replies")]
        self.assertEqual(len(replies), 1)
        text = replies[0]["fields"]["body"]
        self.assertTrue(text.startswith("\U0001F916 <!-- lc -->"))
        self.assertIn(f"Done in {short}: chore(deps): bump x to 3.0.7.", text)
        resolves = [c for c in calls if "resolveReviewThread" in c["fields"].get("query", "")]
        self.assertEqual(len(resolves), 1)
        thumbs = [c for c in calls if c["path"].endswith("/pulls/comments/1287/reactions")]
        self.assertEqual(len(thumbs), 1)
        self.assertEqual(len(self.completions()), 1)

        print("\n--- PR conversation (replay of lightcycle#1287) ---")
        print("operator (inline on feature.txt): bump it to 3.0.7")
        print("  reaction: eyes (from handle-feedback)")
        print(f"  lc reply: {text.splitlines()[0]} / {text.splitlines()[1]}")
        print("  thread resolved")
        print("  reaction: +1")
        print("---")


if __name__ == "__main__":
    unittest.main()


class OpenPrTimeoutTest(HangCase):
    def test_a_hung_git_fails_the_step_naming_the_command(self):
        self.feature_branch()
        self.hang("git", grandchild=True)

        result = self.run_limited("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("timed out", result.stderr)
        self.assertIn("git", result.stderr)

    def test_a_hung_gh_write_is_not_retried(self):
        self.feature_branch()
        sh("git", "push", "-u", "origin", "feat/x", cwd=self.work)
        self.hang("gh")

        result = self.run_limited("open-pr.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("timed out", result.stderr)
        writes = [c for c in self.calls("gh") if "-f" in c or "-F" in c or "-X" in c]
        self.assertLessEqual(len(writes), 1)
