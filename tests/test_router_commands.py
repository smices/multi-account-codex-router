import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_commands", PROJECT / "_codex.py")
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


class RouterCommandTests(unittest.TestCase):
    def test_next_account_id_reuses_first_unoccupied_gap(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(router, "account_home", side_effect=lambda account_id: Path(directory) / f"account-{account_id}"):
            for account_id in (1, 3):
                (Path(directory) / f"account-{account_id}").mkdir()
            self.assertEqual(router.next_account_id({"accounts": [{"id": 1}, {"id": 3}, {"id": 4}]}), 2)

    def test_login_add_saves_accounts_sorted_and_failed_login_unregistered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {"accounts": [{"id": 3, "name": "account-3", "home": str(root / "account-3")}, {"id": 4, "name": "account-4", "home": str(root / "account-4")}]}
            for account_id in (1, 3, 4):
                (root / f"account-{account_id}").mkdir()
            config_path = root / "config.json"
            def load():
                return json.loads(config_path.read_text()) if config_path.exists() else config
            with patch.object(router, "account_home", side_effect=lambda account_id: root / f"account-{account_id}"), patch.object(router, "config_lock", return_value=nullcontext()), patch.object(router, "load_config", side_effect=load), patch.object(router, "save_config", side_effect=lambda cfg: config_path.write_text(json.dumps(cfg))), patch.object(router, "run_login", return_value=0), patch.object(router, "seed_shared_from_accounts"), patch.object(router, "sync_shared_for_account"), patch.object(router, "login_set_default"), redirect_stdout(io.StringIO()):
                self.assertEqual(router.login_add(), 0)
            self.assertEqual([account["id"] for account in load()["accounts"]], [2, 3, 4])

            failed = {"accounts": [{"id": 1, "name": "account-1", "home": str(root / "account-1")}]}
            with patch.object(router, "load_config", return_value=failed), patch.object(router, "run_login", return_value=7), patch.object(router, "save_config") as save, patch.object(router, "account_home", side_effect=lambda account_id: root / f"account-{account_id}"), patch.object(router, "config_lock", return_value=nullcontext()), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(router.login_add(), 7)
            save.assert_not_called()
            self.assertFalse((root / "account-5").exists())
            self.assertTrue((root / "account-1").is_dir())
            self.assertEqual([account["id"] for account in failed["accounts"]], [1])

    def test_sourcing_in_bash_and_zsh_preserves_caller_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "launcher with spaces.sh"
            launcher.symlink_to(PROJECT / "codex.sh")
            for shell in ("bash", "zsh"):
                if shutil.which(shell) is None:
                    continue
                for args, expected in ((["--help"], 0), (["-a", "0"], 2)):
                    with self.subTest(shell=shell, args=args):
                        result = subprocess.run(
                            [shell, "-fc", 'set -u; before_options="$-"; before_pwd="$PWD"; launcher="$1"; shift; if . "$launcher" "$@"; then source_result=0; else source_result=$?; fi; test "$before_options" = "$-" && test "$before_pwd" = "$PWD" || exit 99; printf "SOURCE_STATUS=%s\\nCALLER_ALIVE\\n" "$source_result"', shell, str(launcher), *args],
                            capture_output=True, text=True,
                            env={**os.environ, **({"ZSH_VERSION": "inherited"} if shell == "bash" else {})},
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn(f"SOURCE_STATUS={expected}", result.stdout)
                        self.assertIn("CALLER_ALIVE", result.stdout)
                        if expected == 0:
                            self.assertIn("Codex Router", result.stdout)
                            self.assertEqual(result.stderr, "")

    def test_first_add_with_existing_codex_directory_but_no_file_auth_logs_in(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".codex").mkdir()
            with patch.object(router.Path, "home", return_value=home), patch.object(router, "config_lock", return_value=nullcontext()), patch.object(router, "load_config", return_value={"accounts": []}), patch.object(router, "login_add", return_value=0) as login, redirect_stdout(io.StringIO()):
                self.assertEqual(router.login_first(), 0)
                login.assert_called_once_with()

    def test_route_hint_reports_actual_selection_including_resume_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            account = {"id": 2, "name": "work", "home": directory}
            cases = (
                (["--account", "2"], None, None, "forced"),
                (["resume", "12345678"], account, None, "resume"),
                (["resume", "12345678"], None, 2, "default"),
                (["resume", "12345678"], None, None, "rotate"),
                (["exec", "--account", "literal"], None, 2, "default"),
            )
            for args, session_account, default_id, expected in cases:
                output = io.StringIO()
                config = {"accounts": [account], "last_used": 0, "sessions": {}}
                with self.subTest(args=args, mode=expected), patch.object(router, "config_lock", return_value=nullcontext()), patch.object(router, "load_config", return_value=config), patch.object(router, "seed_shared_from_accounts"), patch.object(router, "sync_shared_for_account"), patch.object(router, "save_config"), patch.object(router, "account_for_session", return_value=session_account), patch.object(router, "default_account_id", return_value=default_id), redirect_stdout(output):
                    self.assertEqual(router.choose(["--route-info", *args]), 0)
                self.assertEqual(output.getvalue().strip().split("\t"), [directory, expected])

    def test_login_uses_file_storage_and_checks_actual_auth_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(router, "require_codex"), patch.object(router.subprocess, "run") as run:
            run.return_value.returncode = 0
            with self.assertRaisesRegex(router.RouterError, "未生成文件认证"):
                router.run_login(Path(directory))
            (Path(directory) / "auth.json").write_text("{}")
            self.assertEqual(router.run_login(Path(directory)), 0)
            self.assertEqual(run.call_args.args[0], ["codex", "-c", 'cli_auth_credentials_store="file"', "login", "--device-auth"])
            self.assertEqual(run.call_args.kwargs["env"]["CODEX_HOME"], directory)
            run.return_value.returncode = 7
            self.assertEqual(router.run_login(Path(directory)), 7)

    def test_public_account_commands_dispatch_to_the_matching_function(self):
        cases = (
            (["account", "list"], "list_accounts", ()),
            (["account", "retry", "2"], "login_retry", (2,)),
            (["account", "default", "2"], "login_set_default", (2,)),
            (["account", "rename", "2", "work"], "login_rename", (2, "work")),
            (["account", "sync-shared"], "sync_shared", ()),
            (["status"], "status_accounts", ()),
            (["status", "2"], "status_accounts", (2,)),
        )
        for args, function, expected in cases:
            with self.subTest(args=args), patch.object(router, function, return_value=0) as call:
                self.assertEqual(router.main(args), 0)
                call.assert_called_once_with(*expected)

    def test_relogin_hint_dispatches_to_retry(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, patch.object(router, "default_account_id", return_value=None), redirect_stdout(output):
            router.print_accounts({"accounts": [{"id": 2, "name": "work", "home": directory}]})
        command = next(line.split("relogin: ", 1)[1] for line in output.getvalue().splitlines() if "relogin:" in line)
        with patch.object(router, "login_retry", return_value=0) as retry:
            self.assertEqual(router.main(command.split()[1:]), 0)
            retry.assert_called_once_with(2)

    def test_missing_directory_does_not_offer_an_unusable_retry(self):
        output = io.StringIO()
        with patch.object(router, "default_account_id", return_value=None), redirect_stdout(output):
            router.print_accounts({"accounts": [{"id": 2, "name": "work", "home": "/missing-router-test-home"}]})
        self.assertIn("请先恢复目录", output.getvalue())
        self.assertNotIn("account retry", output.getvalue())

    def test_first_add_uses_bootstrap_and_later_add_uses_login(self):
        for accounts, expected in (([], "login_first"), ([{"id": 1}], "login_add")):
            with tempfile.TemporaryDirectory() as directory, patch.object(router, "ROOT", Path(directory)), patch.object(router, "LOCK", Path(directory) / "lock"), patch.object(router, "load_config", return_value={"accounts": accounts}), patch.object(router, expected, return_value=0) as call:
                self.assertEqual(router.main(["account", "add"]), 0)
                call.assert_called_once_with()

    def test_shell_preserves_native_arguments_and_matches_management_help(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            stub = temporary / "router.py"
            stub.write_text(
                "import json, sys\n"
                f"print({str(temporary / 'account-2') + chr(9) + 'rotate'!r} if sys.argv[1] == 'choose' else json.dumps(sys.argv[1:]))\n"
            )
            codex = temporary / "codex"
            codex.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            codex.chmod(0o755)
            env = {
                **os.environ, "HOME": directory, "PATH": directory + os.pathsep + os.environ["PATH"],
                "CODEX_ROUTER_PYTHON": sys.executable, "CODEX_ROUTER_SCRIPT": str(stub),
            }
            cases = (
                (["-q", "exec", "--help"], ["exec", "--help"]),
                (["-q", "exec", "-a", "never", "task"], ["exec", "-a", "never", "task"]),
                (["-q", "exec", "--", "-h", "-a", "literal"], ["exec", "--", "-h", "-a", "literal"]),
                (["-q", "help", "exec"], ["help", "exec"]),
                (["-q", "exec", "echo", "--profile=ultra"], ["exec", "echo", "--profile=ultra"]),
                (["-q", "exec", "-p", "ultra"], ["exec", "-p", "ultra"]),
                (["-q", "--profile=ultra"], ["--profile=ultra"]),
                (["account", "retry", "2"], ["account", "retry", "2"]),
                (["account", "default", "2"], ["account", "default", "2"]),
                (["account", "remove", "2"], ["account", "remove", "2"]),
                (["-a", "2", "status"], ["status", "2"]),
            )
            for args, expected in cases:
                with self.subTest(args=args):
                    result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *args], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    prefix = ["-c", 'cli_auth_credentials_store="file"'] if args[0] == "-q" else []
                    self.assertEqual(json.loads(result.stdout), prefix + expected)
            for args in (["status", "unexpected"], ["-a", "2", "account", "retry", "2"], ["login", "retry", "2"]):
                result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *args], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_management_help_needs_no_installation_and_does_not_create_state(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "HOME": directory, "CODEX_ROUTER_PYTHON": str(Path(directory) / "missing")}
            commands = (
                [], ["account"], ["config"], ["status"], ["update"],
                *(["account", command] for command in ("add", "list", "remove", "retry", "default", "rename", "sync-shared")),
                ["account", "remove", "2"], ["config", "apply"], ["config", "status"],
            )
            for command in commands:
                for flag in ("-h", "--help"):
                    with self.subTest(command=command, flag=flag):
                        result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *command, flag], env=env, capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertIn("account remove <id>", result.stdout)
                        self.assertEqual(list(Path(directory).iterdir()), [])

    def test_native_help_skips_account_selection_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            codex = Path(directory) / "codex"
            codex.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
            codex.chmod(0o755)
            env = {
                **os.environ, "HOME": directory, "PATH": directory + os.pathsep + os.environ["PATH"],
                "CODEX_ROUTER_PYTHON": str(Path(directory) / "missing"),
            }
            for args, expected in (
                (["exec", "--help"], ["exec", "--help"]),
                (["mcp", "-h"], ["mcp", "-h"]),
                (["help", "mcp", "add"], ["help", "mcp", "add"]),
                (["--", "--help"], ["--help"]),
            ):
                with self.subTest(args=args):
                    result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *args], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), ["-c", 'cli_auth_credentials_store="file"', *expected])
                    self.assertFalse((Path(directory) / ".codex-router").exists())


class AccountRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "router"
        self.default = Path(self.temp.name) / "default"
        for name, value in (
            ("ROOT", self.root), ("CONFIG", self.root / "config.json"),
            ("LOCK", self.root / "config.lock"), ("SHARED_HOME", self.root / "shared"),
        ):
            patcher = patch.object(router, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(router, "default_codex_home", return_value=self.default)
        patcher.start()
        self.addCleanup(patcher.stop)
        accounts = []
        for account_id in (1, 2):
            home = router.account_home(account_id)
            (home / "sessions").mkdir(parents=True)
            (home / "auth.json").write_text("{}")
            (home / "sessions" / "saved.jsonl").write_text("retained")
            accounts.append({"id": account_id, "name": f"account-{account_id}", "home": str(home)})
        router.save_config({"accounts": accounts, "last_used": 7, "sessions": {"12345678": 1, "abcdefab": 2}})
        self.default.mkdir()
        for item in ("auth.json", "sessions"):
            (self.default / item).symlink_to(router.account_home(1) / item)
        router.SHARED_HOME.mkdir()
        (router.SHARED_HOME / "config.toml").write_text("# shared")

    def test_remove_clears_registration_and_owned_default_links_but_retains_data(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(router.main(["account", "remove", "1"]), 0)
        config = router.load_config()
        self.assertEqual([account["id"] for account in config["accounts"]], [2])
        self.assertEqual(config["sessions"], {"abcdefab": 2})
        self.assertEqual(config["last_used"], 7)
        for item in ("auth.json", "sessions"):
            self.assertFalse((self.default / item).is_symlink())
        self.assertEqual((router.account_home(1) / "auth.json").read_text(), "{}")
        self.assertEqual((router.account_home(1) / "sessions" / "saved.jsonl").read_text(), "retained")
        self.assertEqual((router.SHARED_HOME / "config.toml").read_text(), "# shared")
        self.assertEqual(router.next_account_id(config), 3)

    def test_removing_nondefault_and_last_account_preserves_other_links(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(router.main(["account", "remove", "2"]), 0)
            self.assertEqual(router.default_account_id(router.load_config()), 1)
            self.assertTrue((self.default / "sessions").is_symlink())
            self.assertEqual(router.main(["account", "remove", "1"]), 0)
        self.assertEqual(router.load_config()["accounts"], [])
        self.assertEqual(router.load_config()["sessions"], {})

    def test_missing_account_directory_can_be_unregistered(self):
        shutil.rmtree(router.account_home(1))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(router.main(["account", "remove", "1"]), 0)
        self.assertFalse((self.default / "auth.json").is_symlink())
        self.assertEqual([item["id"] for item in router.load_config()["accounts"]], [2])

    def test_save_failure_restores_default_links_and_keeps_registration(self):
        before = router.CONFIG.read_bytes()
        with patch.object(router, "save_config", side_effect=router.RouterError("save failed")):
            with self.assertRaisesRegex(router.RouterError, "save failed"):
                router.main(["account", "remove", "1"])
        self.assertEqual(router.CONFIG.read_bytes(), before)
        self.assertEqual(router.default_account_id(router.load_config()), 1)
        self.assertTrue((self.default / "sessions").is_symlink())

    def test_unlink_failure_restores_links_without_saving(self):
        before = router.CONFIG.read_bytes()
        unlink = Path.unlink
        def fail_sessions(path, *args, **kwargs):
            if path == self.default / "sessions":
                raise PermissionError("unlink denied")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", fail_sessions):
            with self.assertRaisesRegex(router.RouterError, "unlink denied"):
                router.main(["account", "remove", "1"])
        self.assertEqual(router.CONFIG.read_bytes(), before)
        self.assertEqual(router.default_account_id(router.load_config()), 1)
        self.assertTrue((self.default / "sessions").is_symlink())

    def test_remove_preserves_default_links_to_other_data(self):
        (self.default / "auth.json").unlink()
        unrelated = Path(self.temp.name) / "unrelated.json"
        unrelated.write_text("untouched")
        (self.default / "auth.json").symlink_to(unrelated)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(router.main(["account", "remove", "1"]), 0)
        self.assertEqual((self.default / "auth.json").resolve(), unrelated.resolve())
        self.assertEqual(unrelated.read_text(), "untouched")

    def test_resume_with_profile_prefix_uses_session_account_before_default(self):
        for profile in (["-p", "quality"], ["--profile", "efficient"], ["--profile=quality"], ["-pefficient"]):
            output = io.StringIO()
            with self.subTest(profile=profile), redirect_stdout(output):
                self.assertEqual(router.choose(["--route-info", *profile, "resume", "abcdefab"]), 0)
            self.assertEqual(output.getvalue().strip().split("\t"), [str(router.account_home(2)), "resume"])
            self.assertEqual(router.load_config()["last_used"], 7)

    def test_invalid_remove_does_not_change_registration_or_default(self):
        before = router.CONFIG.read_bytes()
        for args in (["remove"], ["remove", "0"], ["remove", "bad"], ["remove", "3"], ["remove", "1", "extra"]):
            with self.subTest(args=args), self.assertRaises(router.RouterError) as error:
                router.main(["account", *args])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(router.CONFIG.read_bytes(), before)
            self.assertEqual(router.default_account_id(router.load_config()), 1)


if __name__ == "__main__":
    unittest.main()
