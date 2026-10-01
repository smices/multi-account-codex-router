import importlib.util
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_under_test", PROJECT / "_codex.py")
router = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(router)


class FakeStdin:
    def __init__(self):
        self.data = bytearray()
        self.closed_data = b""

    def write(self, data):
        self.data.extend(data)

    def flush(self):
        pass

    def close(self):
        self.closed_data = bytes(self.data)


class FakeStdout:
    def __init__(self, messages):
        init = {"id": 1, "result": {"userAgent": "codex"}}
        chunks = [init, *messages]
        self.chunks = ["".join(json.dumps(m) + "\n" for m in group).encode()
                       for group in (chunks[:1], chunks[1:])]

    def fileno(self):
        return 17

    def read(self, _size):
        return self.chunks.pop(0) if self.chunks else b""


class FakeProcess:
    def __init__(self, messages):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(messages)

    def poll(self):
        return 0


class AppServerCompatibilityTests(unittest.TestCase):
    def request(self, messages):
        process = FakeProcess(messages)
        with patch.object(router.subprocess, "Popen", return_value=process) as popen, patch.object(
            router.select, "select", side_effect=lambda streams, _w, _x, _timeout: (streams, [], [])
        ), patch.object(router.os, "read", side_effect=lambda _fd, size: process.stdout.read(size)):
            result = router.app_server_request(Path("/isolated/codex-home"))
        requests = [json.loads(line) for line in process.stdin.closed_data.decode().splitlines()]
        return result, requests, popen.call_args.args[0]

    def test_current_account_and_rate_limit_methods_accept_out_of_order_responses(self):
        result, requests, command = self.request([
            {"id": 3, "result": {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 25}}}}},
            {"id": 2, "result": {"account": {"type": "chatgpt", "email": "a@example.com"}}},
        ])
        self.assertIsNone(result[1])
        self.assertEqual(result[0]["account"]["email"], "a@example.com")
        self.assertIn("account/read", [r["method"] for r in requests])
        self.assertIn("account/rateLimits/read", [r["method"] for r in requests])
        self.assertIn('cli_auth_credentials_store="file"', command)
        self.assertLess(
            [r["method"] for r in requests].index("initialize"),
            [r["method"] for r in requests].index("initialized"),
        )

    def test_only_auth_errors_suggest_reauthentication(self):
        auth_required_result, _, _ = self.request([
            {"id": 2, "result": {"account": None, "requiresOpenaiAuth": True}},
            {"id": 3, "result": {}},
        ])
        auth_result, _, _ = self.request([
            {"id": 2, "result": {"account": None}},
            {"id": 3, "error": {"code": -32600, "message": "codex account authentication required to read rate limits"}},
        ])
        generic_result, _, _ = self.request([
            {"id": 2, "result": {"account": None}},
            {"id": 3, "error": {"code": -32600, "message": "service unavailable"}},
        ])
        self.assertEqual(auth_required_result[1], "认证已失效，请重新登录")
        self.assertEqual(auth_result[1], "认证已失效，请重新登录")
        self.assertIn("额度读取失败", generic_result[1])

    def test_requires_openai_auth_does_not_mark_an_existing_account_expired(self):
        result, _, _ = self.request([
            {"id": 2, "result": {
                "account": {"type": "chatgpt", "email": "a@example.com"},
                "requiresOpenaiAuth": True,
            }},
            {"id": 3, "result": {"rateLimitsByLimitId": {"codex": {}}}},
        ])
        self.assertIsNone(result[1])
        self.assertEqual(result[0]["account"]["email"], "a@example.com")

    def test_api_key_auth_has_explicit_quota_limitation(self):
        result, _, _ = self.request([
            {"id": 2, "result": {"account": {"type": "apiKey"}, "requiresOpenaiAuth": True}},
            {"id": 3, "error": {"code": -32600, "message": "codex account authentication required to read rate limits"}},
        ])
        self.assertEqual(result[1], "API key 模式不支持 ChatGPT 额度查询")

    def test_status_selects_only_the_requested_account_and_rejects_unknown_id(self):
        with tempfile.TemporaryDirectory() as temp:
            homes = [Path(temp) / str(i) for i in (1, 2)]
            for home in homes:
                home.mkdir()
            config = {"accounts": [
                {"id": i, "name": f"account-{i}", "home": str(home)}
                for i, home in zip((1, 2), homes)
            ]}
            output = StringIO()
            with patch.object(router, "require_codex"), patch.object(
                router, "config_lock", return_value=nullcontext()
            ), patch.object(router, "load_config", return_value=config), patch.object(
                router, "app_server_request", return_value=(None, "读取超时")
            ) as request, redirect_stdout(output):
                router.status_accounts(2)
            self.assertIn("2: account-2", output.getvalue())
            self.assertNotIn("1: account-1", output.getvalue())
            self.assertEqual(request.call_count, 1)
            self.assertEqual(request.call_args.args[0], homes[1])

            with patch.object(router, "require_codex"), patch.object(
                router, "config_lock", return_value=nullcontext()
            ), patch.object(router, "load_config", return_value=config):
                with self.assertRaisesRegex(router.RouterError, "账号 99 不存在"):
                    router.status_accounts(99)

    def test_status_suggests_retry_only_for_authentication_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp) / "account"
            home.mkdir()
            config = {"accounts": [{"id": 4, "name": "four", "home": str(home)}]}
            patches = (
                patch.object(router, "require_codex"),
                patch.object(router, "config_lock", return_value=nullcontext()),
                patch.object(router, "load_config", return_value=config),
            )
            with patches[0], patches[1], patches[2], patch.object(
                router, "app_server_request", return_value=(None, "认证已失效，请重新登录")
            ), redirect_stdout(StringIO()) as output:
                router.status_accounts(4)
            self.assertIn("~/codex.sh account retry 4", output.getvalue())

            for failure in ("读取超时", "服务端已关闭连接", "API key 模式不支持 ChatGPT 额度查询", "额度读取失败: service unavailable"):
                with patches[0], patches[1], patches[2], patch.object(
                    router, "app_server_request", return_value=(None, failure)
                ), redirect_stdout(StringIO()) as output:
                    router.status_accounts(4)
                self.assertNotIn("处理:", output.getvalue(), failure)

            missing_config = {"accounts": [{"id": 4, "name": "four", "home": str(Path(temp) / "missing")}]}
            with patch.object(router, "require_codex"), patch.object(
                router, "config_lock", return_value=nullcontext()
            ), patch.object(router, "load_config", return_value=missing_config), redirect_stdout(StringIO()) as output:
                router.status_accounts(4)
            self.assertIn("账号目录不存在", output.getvalue())
            self.assertNotIn("处理:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
