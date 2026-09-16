from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import sync_client


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class JiraClientTests(unittest.TestCase):
    def client(self) -> sync_client.JiraClient:
        with patch.object(sync_client, "build_ssl_context", return_value=Mock()):
            return sync_client.JiraClient("https://jira.example.test/", "a@example.test", "token", throttle_seconds=0)

    def test_request_serializes_and_sends_http_payload(self) -> None:
        client = self.client()
        with patch("urllib.request.urlopen", return_value=Response({"ok": True})) as open_request:
            self.assertEqual(client.request("POST", "/rest/test", body={"name": "value"}), {"ok": True})
        request = open_request.call_args.args[0]
        self.assertEqual(request.full_url, "https://jira.example.test/rest/test")
        self.assertEqual(json.loads(request.data), {"name": "value"})
        self.assertEqual(request.get_header("Authorization"), f"Basic {client.authorization}")

    def test_retry_policy_and_error_reporting(self) -> None:
        client = self.client()
        rate_limited = urllib.error.HTTPError("url", 429, "rate", {"Retry-After": "2"}, None)
        server_error = urllib.error.HTTPError("url", 503, "bad", {}, None)
        permanent = urllib.error.HTTPError("url", 400, "bad", {}, None)
        with patch.object(sync_client.time, "sleep") as sleep:
            self.assertTrue(client._retry_http_error(rate_limited, "GET", 0))
            self.assertTrue(client._retry_http_error(server_error, "PUT", 0))
            self.assertFalse(client._retry_http_error(rate_limited, "POST", 0))
            self.assertFalse(client._retry_http_error(permanent, "GET", 0))
            self.assertTrue(client._retry_url_error(0, "GET"))
            self.assertFalse(client._retry_url_error(4, "GET"))
            self.assertFalse(client._retry_url_error(0, "POST"))
        self.assertEqual(sleep.call_count, 3)

        permanent.read = Mock(return_value=b"invalid request")
        with patch("urllib.request.urlopen", side_effect=permanent):
            with self.assertRaisesRegex(RuntimeError, "HTTP 400: invalid request"):
                client.request("GET", "/failure")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), patch.object(sync_client.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                client.request("GET", "/offline")

    def test_tracker_operations_shape_expected_requests(self) -> None:
        client = self.client()
        client.request = Mock(
            side_effect=[
                {"issues": [{"key": "PROJ-1"}]},
                {"issues": [{"key": "PROJ-2"}]},
                {"transitions": [{"id": "1"}]},
                {"fields": {"status": {"name": "Open"}}},
                [{"id": "1"}],
            ]
        )
        self.assertEqual(client.search_by_keys(["PROJ-1"]), {"PROJ-1": {"key": "PROJ-1"}})
        self.assertEqual(client.search_by_label("PROJ", "board"), [{"key": "PROJ-2"}])
        client.request.reset_mock()
        client.request.side_effect = None
        client.request.return_value = {"issues": [{"key": "PROJ-3"}]}
        self.assertEqual(client.search_by_asset_marker("PROJ", "E1"), [{"key": "PROJ-3"}])
        marker_request = client.request.call_args.kwargs["body"]["jql"]
        self.assertIn('project = "PROJ"', marker_request)
        self.assertIn("[E1]", marker_request)
        client.request.reset_mock()
        client.request.side_effect = [
            {"transitions": [{"id": "1"}]},
            {"fields": {"status": {"name": "Open"}}},
            [{"id": "1"}],
        ]
        self.assertEqual(client.transitions("PROJ-1"), [{"id": "1"}])
        self.assertEqual(client.issue_status("PROJ-1"), "Open")
        self.assertEqual(client.remote_links("PROJ-1"), [{"id": "1"}])
        client.request.reset_mock()
        client.request.side_effect = None
        client.request.return_value = None
        client.create_issue({"summary": "Issue"})
        client.update_issue("PROJ-1", {"summary": "Issue"})
        client.transition("PROJ-1", "1")
        client.create_remote_link("PROJ-1", {"globalId": "g", "url": "https://example.test", "title": "Evidence"})
        client.update_remote_link("PROJ-1", "2", {"globalId": "g", "url": "https://example.test", "title": "Evidence"})
        client.delete_remote_link("PROJ-1", "2")
        calls = client.request.call_args_list
        self.assertTrue(any(call.args[:2] == ("POST", "/rest/api/3/issue") for call in calls))
        self.assertTrue(any(call.args[:2] == ("DELETE", "/rest/api/3/issue/PROJ-1/remotelink/2") for call in calls))


if __name__ == "__main__":
    unittest.main()
