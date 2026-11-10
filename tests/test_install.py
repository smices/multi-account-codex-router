import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
PRESETS = ("AGENTS.md", "RTK.md", "config.toml", "efficient.config.toml",
           "quality.config.toml", "agents/luna-worker.toml", "agents/sol-general.toml")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project, self.home, self.bin = (self.root / "checkout", self.root / "home", self.root / "bin")
        self.project.mkdir()
        self.home.mkdir()
        self.bin.mkdir()
        shutil.copy(PROJECT / "install.sh", self.project / "install.sh")
        for name in ("pyproject.toml", "uv.lock"):
            shutil.copy(PROJECT / name, self.project / name)
        (self.project / "codex.sh").write_text("#!/bin/sh\n")
        (self.project / "_codex.py").write_text("pass\n")
        for file in PRESETS:
            target = self.project / "presets/sol-luna" / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("preset\n")
        self.log = self.root / "uv.log"
        uv = self.bin / "uv"
        uv.write_text(
            '#!/bin/sh\n'
            'printf \'%s\\n\' "$UV_PROJECT_ENVIRONMENT|$*" >> "$UV_LOG"\n'
            '[ "${UV_FAIL:-}" != 1 ] || exit 17\n'
            'mkdir -p "$UV_PROJECT_ENVIRONMENT/bin"\n'
            'printf \'#!/bin/sh\\nexec "%s" "$@"\\n\' "$PY_REAL" > "$UV_PROJECT_ENVIRONMENT/bin/python"\n'
            'if [ "${TOML_FAIL:-}" = 1 ]; then\n'
            '  printf \'#!/bin/sh\\nexit 1\\n\' > "$UV_PROJECT_ENVIRONMENT/bin/python"\n'
            'fi\n'
            'chmod +x "$UV_PROJECT_ENVIRONMENT/bin/python"\n'
        )
        uv.chmod(0o755)
        for name, body in (("codex", "exit 0"), ("rtk", "[ \"$1\" = --version ] || [ \"$1\" = gain ]")):
            path = self.bin / name
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(0o755)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "UV_LOG": str(self.log), "PY_REAL": sys.executable}

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *args, **env):
        return subprocess.run([str(self.project / "install.sh"), *args], env={**self.env, **env}, capture_output=True, text=True)

    def test_sync_is_pinned_and_home_launcher_created(self):
        override = self.root / "external-venv"
        result = self.run_install("--force", UV_PROJECT_ENVIRONMENT=str(override))
        self.assertEqual(result.returncode, 0, result.stderr)
        resolved = self.project.resolve()
        self.assertEqual(self.log.read_text().strip(), f"{resolved}/.venv|sync --locked --project {resolved}")
        self.assertFalse(override.exists())
        self.assertEqual(os.path.realpath(self.home / "codex.sh"), str((self.project / "codex.sh").resolve()))

    def test_help_and_invalid_extra_arguments_do_not_sync_or_touch_home(self):
        for args in (("--help",), ("-h",)):
            self.assertEqual(self.run_install(*args).returncode, 0)
        for args in (("--help", "garbage"), ("--force", "extra")):
            self.assertNotEqual(self.run_install(*args).returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(list(self.home.iterdir()), [])

    def test_sync_or_tomllib_failure_leaves_launcher_and_preset_untouched(self):
        shared = self.home / ".codex-router/shared"
        shared.mkdir(parents=True)
        (shared / "config.toml").write_text("old\n")
        launcher = self.home / "codex.sh"
        launcher.write_text("user file\n")
        for env in ({"UV_FAIL": "1"}, {"TOML_FAIL": "1"}):
            result = self.run_install("--force", **env)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(launcher.read_text(), "user file\n")
            self.assertEqual((shared / "config.toml").read_text(), "old\n")


if __name__ == "__main__":
    unittest.main()
