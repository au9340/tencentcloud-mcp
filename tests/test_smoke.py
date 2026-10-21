import base64
import json
import os
import unittest
from unittest import mock

from main import main_handler
from mcp_tc import sandbox, tc3
from mcp_tc.auth import AuthError, resolve_credentials
from mcp_tc.context import RequestContext
from mcp_tc.server import handle_http
from mcp_tc.tools import call_tool


class Tc3Test(unittest.TestCase):
    def test_signature_shape_and_date(self):
        url, headers = tc3.sign(
            secret_id="AKIDEXAMPLE",
            secret_key="SECRET",
            service="cvm",
            action="DescribeInstances",
            version="2017-03-12",
            payload="{}",
            region="ap-guangzhou",
            timestamp=1551113065,
        )
        self.assertEqual(url, "https://cvm.tencentcloudapi.com/")
        self.assertEqual(headers["X-TC-Action"], "DescribeInstances")
        self.assertEqual(headers["X-TC-Region"], "ap-guangzhou")
        self.assertIn("Credential=AKIDEXAMPLE/2019-02-25/cvm/tc3_request", headers["Authorization"])
        self.assertEqual(len(headers["Authorization"].rsplit("Signature=", 1)[1]), 64)

    def test_signature_is_stable(self):
        kwargs = dict(
            secret_id="id",
            secret_key="key",
            service="dnspod",
            action="DescribeDomainList",
            version="2021-03-23",
            payload='{"Limit":10}',
            timestamp=1_700_000_000,
        )
        self.assertEqual(tc3.sign(**kwargs)[1]["Authorization"], tc3.sign(**kwargs)[1]["Authorization"])
        self.assertIn("/2023-11-14/dnspod/tc3_request", tc3.sign(**kwargs)[1]["Authorization"])


class AuthTest(unittest.TestCase):
    def test_plain_bearer(self):
        creds = resolve_credentials({"authorization": "Bearer id:key:tok"})
        self.assertIsNotNone(creds)
        self.assertEqual(creds.secret_id, "id")
        self.assertEqual(creds.secret_key, "key")
        self.assertEqual(creds.token, "tok")

    def test_base64_bearer(self):
        raw = base64.b64encode(b"id:key").decode()
        creds = resolve_credentials({"authorization": f"Bearer {raw}"})
        self.assertEqual(creds.secret_key, "key")

    def test_missing_token_returns_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_credentials({}))

    def test_bad_bearer(self):
        with self.assertRaises(AuthError):
            resolve_credentials({"authorization": "Bearer onlyid"})


class SandboxTest(unittest.TestCase):
    def test_return_and_await(self):
        async def fake_request(**kwargs):
            return {"total": 2, "service": kwargs["service"]}

        class FakeTencent:
            request = staticmethod(fake_request)

        result = sandbox.run_code(
            'r = await tencent.request(service="cvm", action="DescribeInstances")\nreturn r["total"]',
            {"tencent": FakeTencent()},
        )
        self.assertEqual(result, 2)

    def test_last_expression_is_returned(self):
        self.assertEqual(sandbox.run_code("1 + 1", {}), 2)

    def test_import_is_rejected(self):
        with self.assertRaises(sandbox.CodeRejected):
            sandbox.run_code("import os", {})
        with self.assertRaises(sandbox.CodeRejected):
            sandbox.run_code("return __import__('os')", {})


class ProtocolTest(unittest.TestCase):
    def test_initialize_and_list(self):
        status, headers, body = handle_http(
            "POST",
            "/mcp",
            {},
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}),
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["result"]["serverInfo"]["name"], "tencentcloud-mcp")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

        status, _, body = handle_http("POST", "/mcp", {}, json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))
        self.assertEqual(status, 200)
        names = [tool["name"] for tool in json.loads(body)["result"]["tools"]]
        self.assertEqual(names, ["search", "execute", "docs", "whoami"])

    def test_notification_is_202(self):
        status, _, body = handle_http(
            "POST", "/mcp", {}, json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        self.assertEqual(status, 202)
        self.assertEqual(body, "")

    def test_tools_call_without_credentials(self):
        status, _, body = handle_http(
            "POST",
            "/mcp",
            {},
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}),
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["error"]["code"], -32001)

    def test_get_is_405(self):
        status, _, _ = handle_http("GET", "/mcp", {}, "")
        self.assertEqual(status, 405)


class ToolsTest(unittest.TestCase):
    def test_docs_offline(self):
        result = call_tool("docs", {"query": "cvm 实例"}, RequestContext())
        text = result["content"][0]["text"]
        self.assertIn("DescribeInstances", text)
        self.assertIn("cloud.tencent.com", text)

    def test_search_offline(self):
        result = call_tool(
            "search",
            {"code": 'return [a["action"] for a in spec["actions"] if a["service"] == "cvm"][:3]'},
            RequestContext(),
        )
        self.assertIn("DescribeInstances", result["content"][0]["text"])


class HandlerTest(unittest.TestCase):
    def test_main_handler_shapes_response(self):
        event = {
            "httpMethod": "POST",
            "path": "/mcp",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            "isBase64Encoded": False,
        }
        response = main_handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertFalse(response["isBase64Encoded"])
        self.assertIn("tools", response["body"])

    def test_main_handler_accepts_base64_body(self):
        event = {
            "httpMethod": "POST",
            "path": "/mcp",
            "headers": {},
            "body": base64.b64encode(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()).decode(),
            "isBase64Encoded": True,
        }
        response = main_handler(event, None)
        self.assertEqual(response["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
