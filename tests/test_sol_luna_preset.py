import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_under_test", PROJECT / "_codex.py")
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


class SolLunaPresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "router"
        self.original = (
            router.ROOT, router.CONFIG, router.LOCK, router.SHARED_HOME,
            router.default_codex_home,
        )
        router.ROOT = self.root
        router.CONFIG = self.root / "config.json"
        router.LOCK = self.root / "config.lock"
        router.SHARED_HOME = self.root / "shared"
        self.default_home = Path(self.temp.name) / ".codex"
        router.default_codex_home = lambda: self.default_home

    def tearDown(self):
        (
            router.ROOT, router.CONFIG, router.LOCK, router.SHARED_HOME,
            router.default_codex_home,
        ) = self.original
        self.temp.cleanup()

    def write_accounts(self, ids=()):
        accounts = []
        for account_id in ids:
            home = router.account_home(account_id)
            home.mkdir(parents=True)
            accounts.append({"id": account_id, "name": f"a{account_id}", "home": str(home)})
        router.ROOT.mkdir(parents=True, exist_ok=True)
        router.CONFIG.write_text(json.dumps({"accounts": accounts, "last_used": 0, "sessions": {}}))

    def apply(self):
        with redirect_stdout(io.StringIO()):
            return router.apply_sol_luna_preset()

    def test_empty_directory_creates_valid_preset(self):
        self.write_accounts()
        self.assertEqual(self.apply(), 0)
        config = router.SHARED_HOME / "config.toml"
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertEqual(
            (router.SHARED_HOME / "AGENTS.md").read_text(),
            (PROJECT / "presets/sol-luna/AGENTS.md").read_text(),
        )
        self.assertEqual(router.sol_luna_preset_status(), 0)

    def test_preserves_unrelated_toml_and_comments(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        config = router.SHARED_HOME / "config.toml"
        config.write_text("# keep me\nfeature_flag = true\n\n[experimental]\nmode = \"safe\"\n")
        self.apply()
        actual = config.read_text()
        self.assertIn("# keep me", actual)
        self.assertIn("feature_flag = true", actual)
        self.assertIn("[experimental]", actual)
        self.assertIn('mode = "safe"', actual)

    def test_replaces_legacy_keys_without_duplicates_and_is_byte_idempotent(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        config = router.SHARED_HOME / "config.toml"
        config.write_text(
            'model = "old"\nmodel_reasoning_effort = "high"\n\n[agents]\n'
            'default_subagent_model = "old-worker"\n'
            'default_subagent_reasoning_effort = "low"\n\n'
            '[agents.luna-worker]\ndescription = "old"\nconfig_file = "old.toml"\n'
        )
        self.apply()
        first = config.read_bytes()
        self.apply()
        self.assertEqual(config.read_bytes(), first)
        text = first.decode()
        self.assertEqual(text.count('model = "gpt-5.6-sol"'), 1)
        self.assertEqual(text.count('model_reasoning_effort = "max"'), 1)
        self.assertEqual(text.count('default_subagent_model = "gpt-5.6-luna"'), 1)
        self.assertEqual(text.count('default_subagent_reasoning_effort = "xhigh"'), 1)
        self.assertEqual(text.count('config_file = "agents/luna-worker.toml"'), 1)

    def test_merges_current_dotted_shape_without_duplicate_tables(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        config = router.SHARED_HOME / "config.toml"
        config.write_text(
            'model = "gpt-5.6-sol"\nmodel_reasoning_effort = "medium"\n'
            'agents.default_subagent_model = "gpt-5.6-luna"\n'
            'agents.default_subagent_reasoning_effort = "medium"\n'
            'agents.luna-worker.description = "old"\n'
            'agents.luna-worker.config_file = "old.toml"\n\n'
            '[personality]\nname = "preserved"\n\n[mcp]\nenabled = true\n'
        )
        self.apply()
        actual = config.read_text()
        parsed = router.tomllib.loads(actual)
        self.assertEqual(parsed["agents"]["default_subagent_model"], "gpt-5.6-luna")
        self.assertEqual(parsed["agents"]["luna-worker"]["config_file"], "agents/luna-worker.toml")
        self.assertIn('[personality]\nname = "preserved"', actual)
        self.assertIn('[mcp]\nenabled = true', actual)
        self.assertNotIn("[agents]", actual)
        self.assertNotIn("[agents.luna-worker]", actual)
        self.assertEqual(actual, router.merge_sol_luna_config(actual))
        preset = router.tomllib.loads((PROJECT / "presets/sol-luna/config.toml").read_text())
        for key in router.PRESET_CONFIG_KEYS:
            self.assertEqual(router._dotted_value(parsed, key), router._dotted_value(preset, key))

    def test_installs_switchable_reasoning_profiles(self):
        self.write_accounts((1, 2))
        self.default_home.mkdir(parents=True)
        self.apply()

        expected = {
            "efficient": ("high", "high", "agents/luna-worker-high.toml"),
            "quality": ("max", "xhigh", "agents/luna-worker.toml"),
            "ultra": ("ultra", "xhigh", "agents/luna-worker.toml"),
        }
        for name, values in expected.items():
            shared = router.SHARED_HOME / f"{name}.config.toml"
            profile = router.tomllib.loads(shared.read_text())
            self.assertEqual(profile["model_reasoning_effort"], values[0])
            self.assertEqual(profile["agents"]["default_subagent_reasoning_effort"], values[1])
            self.assertEqual(profile["agents"]["luna-worker"]["config_file"], values[2])
            for home in (self.default_home, router.account_home(1), router.account_home(2)):
                self.assertTrue((home / f"{name}.config.toml").is_symlink())

    def test_preserves_unmanaged_legacy_agent_table_keys(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        config = router.SHARED_HOME / "config.toml"
        config.write_text(
            '[agents]\ncustom_limit = 3\n\n[agents.luna-worker]\n'
            'timeout_seconds = 30\ndescription = "old"\n'
        )
        self.apply()
        actual = config.read_text()
        parsed = router.tomllib.loads(actual)
        self.assertEqual(parsed["agents"]["custom_limit"], 3)
        self.assertEqual(parsed["agents"]["luna-worker"]["timeout_seconds"], 30)
        self.assertIn("agents.custom_limit = 3", actual)
        self.assertIn("agents.luna-worker.timeout_seconds = 30", actual)

    def test_existing_files_are_backed_up_once_when_changed(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        (router.SHARED_HOME / "config.toml").write_text('model = "old"\n')
        self.apply()
        backups = list((router.ROOT / "backups").rglob("config.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'model = "old"\n')
        self.apply()
        self.assertEqual(len(list((router.ROOT / "backups").rglob("config.toml"))), 1)

    def test_status_detects_drift(self):
        self.write_accounts()
        self.apply()
        config = router.SHARED_HOME / "config.toml"
        config.write_text(config.read_text().replace('gpt-5.6-sol', 'wrong-model', 1))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(router.sol_luna_preset_status(), 1)

    def test_status_is_read_only_when_router_root_does_not_exist(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(router.sol_luna_preset_status(), 1)
        self.assertFalse(router.ROOT.exists())

    def test_backup_output_is_router_relative_and_static_artifacts_are_anonymous(self):
        self.write_accounts()
        router.SHARED_HOME.mkdir(parents=True)
        (router.SHARED_HOME / "config.toml").write_text('model = "old"\n')
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(router.apply_sol_luna_preset(), 0)
        self.assertIn("shared/config.toml -> backups/", output.getvalue())
        self.assertNotIn(str(router.ROOT), output.getvalue())
        for relative in (
            "README.md", "presets/sol-luna/config.toml",
            "presets/sol-luna/AGENTS.md", "presets/sol-luna/RTK.md",
            *(f"presets/sol-luna/{name}.config.toml"
              for name in router.PRESET_PROFILE_NAMES),
            *(f"presets/sol-luna/agents/{name}.toml"
              for name in router.PRESET_AGENT_FILES),
        ):
            text = (PROJECT / relative).read_text(encoding="utf-8")
            self.assertNotIn("/" + "Users/", text)
            self.assertNotIn("jack" + "y", text)

    def test_install_documents_and_checks_python_tomllib_before_launcher_changes(self):
        installer = (PROJECT / "install.sh").read_text(encoding="utf-8")
        readme = (PROJECT / "README.md").read_text(encoding="utf-8")
        gate = installer.index("python3 -c 'import tomllib'")
        apply = installer.index('"$VENV_DIR/bin/python" "$PROJECT_DIR/_codex.py" config apply')
        launcher = installer.index('if [[ -e "$HOME_LAUNCHER"')
        self.assertLess(gate, apply)
        self.assertLess(apply, launcher)
        self.assertIn("Python 3.11", readme)
        self.assertIn("tomllib", readme)
        self.assertIn("--force", installer)
        self.assertIn("[y/N]", installer)
        self.assertIn("[Y/n]", installer)

    def test_apply_syncs_every_usable_account_with_symlinks(self):
        self.write_accounts((1, 2))
        self.apply()
        for account_id in (1, 2):
            home = router.account_home(account_id)
            for item in ("config.toml", "AGENTS.md", "agents"):
                target = home / item
                self.assertTrue(target.is_symlink())
                self.assertEqual(os.path.realpath(target), os.path.realpath(router.SHARED_HOME / item))
        self.assertEqual(router.sol_luna_preset_status(), 0)

    def test_apply_migrates_rtk_and_removes_legacy_shared_instructions(self):
        self.write_accounts((1, 2))
        router.SHARED_HOME.mkdir(parents=True)
        self.default_home.mkdir(parents=True)
        (self.default_home / "RTK.md").write_text("rtk reference\n")
        for item in router.LEGACY_SHARED_PATHS:
            shared = router.SHARED_HOME / item
            shared.write_text(f"legacy {item}\n")
            os.symlink(shared, self.default_home / item)
            for account_id in (1, 2):
                os.symlink(shared, router.account_home(account_id) / item)

        self.apply()

        self.assertEqual(
            (router.SHARED_HOME / "RTK.md").read_text(),
            (PROJECT / "presets/sol-luna/RTK.md").read_text(),
        )
        self.assertEqual(
            (self.default_home / "RTK.md.shared-backup").read_text(),
            "rtk reference\n",
        )
        for home in (self.default_home, router.account_home(1), router.account_home(2)):
            self.assertTrue((home / "RTK.md").is_symlink())
            for item in router.LEGACY_SHARED_PATHS:
                self.assertFalse((home / item).exists())
                self.assertFalse((home / item).is_symlink())
        for item in router.LEGACY_SHARED_PATHS:
            self.assertFalse((router.SHARED_HOME / item).exists())
            backups = list((router.ROOT / "backups").rglob(item))
            self.assertEqual(len(backups), 1)
        self.assertEqual(router.sol_luna_preset_status(), 0)

    def test_main_dispatch_and_shell_config_never_forwards_to_codex(self):
        self.write_accounts()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(router.main(["config", "apply"]), 0)
        self.assertEqual(router.main(["config", "status"]), 0)
        env = {
            **os.environ,
            "HOME": self.temp.name,
            "CODEX_ROUTER_PYTHON": sys.executable,
            "CODEX_ROUTER_SCRIPT": str(PROJECT / "_codex.py"),
        }
        applied = subprocess.run(
            ["bash", str(PROJECT / "codex.sh"), "config", "apply"],
            env=env,
            text=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["bash", str(PROJECT / "codex.sh"), "config", "status"],
            env={
                **env,
            },
            text=True,
            capture_output=True,
        )
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Using account", applied.stdout + applied.stderr + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
