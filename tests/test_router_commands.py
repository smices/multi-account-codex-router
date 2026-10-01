import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_commands", PROJECT / "_codex.py")
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


class RouterCommandTests(unittest.TestCase):
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
                (["account", "retry", "2"], ["account", "retry", "2"]),
                (["account", "default", "2"], ["account", "default", "2"]),
                (["-a", "2", "status"], ["status", "2"]),
            )
            for args, expected in cases:
                with self.subTest(args=args):
                    result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *args], env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    prefix = ["-c", 'cli_auth_credentials_store="file"'] if args[0] == "-q" else []
                    self.assertEqual(json.loads(result.stdout), prefix + expected)
            for args in (["status", "unexpected"], ["-a", "2", "account", "retry", "2"], ["login", "retry", "2"], ["-p", "ultra"], ["--profile", "ultra"], ["--profile=ultra"], ["-pultra"], ["exec", "-p", "ultra"]):
                result = subprocess.run(["bash", str(PROJECT / "codex.sh"), *args], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main()
