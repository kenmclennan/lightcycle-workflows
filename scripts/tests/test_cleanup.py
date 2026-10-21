import json
import unittest

from tests.harness import ScriptCase, sh


class CleanupTest(ScriptCase):
    def test_clean_worktree_prints_done(self):
        result = self.run_script("cleanup.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")
        self.assertEqual(sh("git", "status", "--porcelain", cwd=self.work).stdout, "")

    def test_dirty_worktree_is_refused_naming_the_path(self):
        (self.work / "unsaved.txt").write_text("work\n")

        result = self.run_script("cleanup.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("unsaved.txt", result.stderr)
        self.assertTrue((self.work / "unsaved.txt").exists())

    def test_modified_tracked_file_is_refused(self):
        (self.work / "README.md").write_text("edited\n")

        result = self.run_script("cleanup.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("README.md", result.stderr)

    def test_worktree_with_only_ignored_files_is_clean(self):
        (self.work / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
        sh("git", "add", ".gitignore", cwd=self.work)
        sh("git", "commit", "-m", "ignore caches", cwd=self.work)
        (self.work / "__pycache__").mkdir()
        (self.work / "__pycache__" / "mod.pyc").write_text("x")
        (self.work / ".pytest_cache").mkdir()
        (self.work / ".pytest_cache" / "v").write_text("x")

        result = self.run_script("cleanup.py")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["outcome"], "done")


if __name__ == "__main__":
    unittest.main()
