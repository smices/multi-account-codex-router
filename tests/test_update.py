import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "router"
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.repo.mkdir()
        self.git("init", cwd=self.repo)
        self.git("config", "user.email", "test@example.invalid", cwd=self.repo)
        self.git("config", "user.name", "Update Test", cwd=self.repo)
        shutil.copy(PROJECT / "update.sh", self.repo / "update.sh")
        (self.repo / "install.sh").write_text(
            '#!/usr/bin/env bash\nset -e\nprintf "install:%s\\n" "$*" >> "$TRACE"\n'
        )
        (self.repo / "codex.sh").write_text(
            '#!/usr/bin/env bash\nset -e\nprintf "codex:%s\\n" "$*" >> "$TRACE"\n'
        )
        (self.repo / "version").write_text("one\n")
        self.commit("initial")
        self.git("branch", "-M", "main", cwd=self.repo)
        self.git("remote", "add", "origin", str(self.remote), cwd=self.repo)
        self.git("push", "-u", "origin", "main", cwd=self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, cwd):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
        )

    def commit(self, message):
        self.git("add", "-A", cwd=self.repo)
        self.git("commit", "-m", message, cwd=self.repo)

    def run_update(self):
        return subprocess.run(
            ["bash", str(self.repo / "update.sh")],
            cwd=self.root,
            env={**os.environ, "TRACE": str(self.root / "trace")},
            capture_output=True,
            text=True,
        )

    def test_fast_forward_updates_then_runs_install_and_config_status(self):
        clone = self.root / "clone"
        self.git("clone", "--branch", "main", str(self.remote), str(clone), cwd=self.root)
        self.git("config", "user.email", "test@example.invalid", cwd=clone)
        self.git("config", "user.name", "Update Test", cwd=clone)
        (clone / "version").write_text("two\n")
        (clone / "install.sh").write_text(
            '#!/usr/bin/env bash\nprintf "install-v2:%s\\n" "$*" >> "$TRACE"\n'
        )
        self.git("add", "version", "install.sh", cwd=clone)
        self.git("commit", "-m", "new installer version", cwd=clone)
        self.git("push", "origin", "main", cwd=clone)
        expected = self.git("rev-parse", "--short", "HEAD", cwd=clone).stdout.strip()

        result = self.run_update()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "version").read_text(), "two\n")
        self.assertIn(f"Updated to {expected}.", result.stdout)
        self.assertEqual(
            (self.root / "trace").read_text().splitlines(),
            ["install-v2:--force", "codex:config status"],
        )

    def test_dirty_tree_aborts_without_changing_work_or_running_scripts(self):
        (self.repo / "local.txt").write_text("keep me\n")

        result = self.run_update()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Working tree has changes", result.stderr)
        self.assertEqual((self.repo / "local.txt").read_text(), "keep me\n")
        self.assertFalse((self.root / "trace").exists())

    def test_diverged_branch_refuses_update_without_running_scripts(self):
        clone = self.root / "clone"
        self.git("clone", "--branch", "main", str(self.remote), str(clone), cwd=self.root)
        self.git("config", "user.email", "test@example.invalid", cwd=clone)
        self.git("config", "user.name", "Update Test", cwd=clone)
        (clone / "version").write_text("remote\n")
        self.git("add", "version", cwd=clone)
        self.git("commit", "-m", "remote", cwd=clone)
        self.git("push", "origin", "main", cwd=clone)
        (self.repo / "version").write_text("local\n")
        self.commit("local divergence")
        before = self.git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()

        result = self.run_update()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Update failed", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=self.repo).stdout.strip(), before)
        self.assertFalse((self.root / "trace").exists())

    def test_install_failure_stops_before_config_status(self):
        (self.repo / "install.sh").write_text("#!/usr/bin/env bash\nexit 7\n")
        self.commit("failing installer")

        result = self.run_update()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Updated installer failed", result.stderr)
        self.assertFalse((self.root / "trace").exists())


if __name__ == "__main__":
    unittest.main()
