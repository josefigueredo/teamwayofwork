"""HTTP client for Jira-compatible tracker APIs."""
from __future__ import annotations

import base64
import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class WriteLimiter:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.last_write = 0.0


def build_ssl_context() -> ssl.SSLContext:
    ca_file = ("" + os.environ.get("SSL_CERT_FILE", "")).strip()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if ca_file:
        path = Path(ca_file).expanduser()
        if not path.is_file():
            raise RuntimeError(f"SSL_CERT_FILE is not a file: {path}")
        context.load_verify_locations(cafile=path)
    else:
        context.load_default_certs()
    return context


class JiraClient:
    def __init__(self, base_url: str, email: str, token: str, *, throttle_seconds: float | None = None, limiter: WriteLimiter | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.context = build_ssl_context()
        default_throttle = float(os.environ.get("JIRA_WRITE_THROTTLE", "1.5"))
        self.throttle_seconds = throttle_seconds if throttle_seconds is not None else default_throttle
        self.limiter = limiter or WriteLimiter()

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None, write: bool = False) -> Any:
        if write:
            self._wait_for_write_slot()
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode() if body else None,
            method=method,
            headers={"Authorization": f"Basic {self.authorization}", "Accept": "application/json", "Content-Type": "application/json"},
        )
        return self._send(request, method, path, write)

    def _wait_for_write_slot(self) -> None:
        with self.limiter.lock:
            delay = self.throttle_seconds - (time.monotonic() - self.limiter.last_write)
            if delay > 0:
                time.sleep(delay)
            self.limiter.last_write = time.monotonic()

    def _http_retry_delay(self, error: urllib.error.HTTPError, method: str, attempt: int) -> float | None:
        if method in {"GET", "PUT", "DELETE"} and error.code == 429 and attempt < 4:
            retry_after = error.headers.get("Retry-After", "")
            return float(retry_after) if retry_after.isdigit() else min(2**attempt, 30)
        if method in {"GET", "PUT", "DELETE"} and error.code in {502, 503} and attempt < 4:
            return min(2**attempt, 30)
        return None

    def _url_retry_delay(self, attempt: int) -> float | None:
        return min(2**attempt, 30) if attempt < 4 else None

    def _retry_http_error(self, error: urllib.error.HTTPError, method: str, attempt: int) -> bool:
        delay = self._http_retry_delay(error, method, attempt)
        if delay is None:
            return False
        time.sleep(delay)
        return True

    def _retry_url_error(self, attempt: int, method: str) -> bool:
        delay = self._url_retry_delay(attempt) if method in {"GET", "PUT", "DELETE"} else None
        if delay is None:
            return False
        time.sleep(delay)
        return True

    def _send(self, request: urllib.request.Request, method: str, path: str, write: bool) -> Any:
        retries = 5
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=60, context=self.context) as response:
                    raw = response.read()
                return json.loads(raw.decode()) if raw else None
            except urllib.error.HTTPError as exc:
                if self._retry_http_error(exc, method, attempt):
                    continue
                payload = exc.read().decode(errors="replace")
                raise RuntimeError(f"tracker {method} {path} failed with HTTP {exc.code}: {payload}") from exc
            except urllib.error.URLError as exc:
                if self._retry_url_error(attempt, method):
                    continue
                raise RuntimeError(f"tracker request failed: {exc.reason}") from exc
        raise RuntimeError(f"tracker {method} {path} failed after {retries} attempts")

    def search_by_keys(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        issues: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(keys), 50):
            query = ", ".join(keys[offset : offset + 50])
            for issue in self._search(f"key in ({query})", ["summary", "status", "assignee", "labels", "updated"]):
                issues[issue["key"]] = issue
        return issues

    def search_by_label(self, project_key: str, label: str) -> list[dict[str, Any]]:
        return self._search(f'project = {project_key} AND labels = "{label}" ORDER BY key ASC', ["summary"])

    def search_by_asset_marker(self, project_key: str, entity_id: str) -> list[dict[str, Any]]:
        """Find possible prior syncs without depending on result ordering."""
        marker = f'"[{entity_id}]"'.replace('"', '\\"')
        return self._search(
            f'project = "{project_key}" AND summary ~ "{marker}" ORDER BY key ASC',
            ["summary", "issuetype", "project", "labels", "updated", "status", "assignee"],
        )

    def _search(self, jql: str, fields: list[str]) -> list[dict[str, Any]]:
        data = self.request("POST", "/rest/api/3/search/jql", body={"jql": jql, "maxResults": 100, "fields": fields})
        return data.get("issues", []) if isinstance(data, dict) else []

    def create_issue(self, fields: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/rest/api/3/issue", body={"fields": fields}, write=True)

    def update_issue(self, key: str, fields: dict[str, Any]) -> None:
        self.request("PUT", f"/rest/api/3/issue/{key}", body={"fields": fields}, write=True)

    def transitions(self, key: str) -> list[dict[str, Any]]:
        data = self.request("GET", f"/rest/api/3/issue/{key}/transitions")
        return data.get("transitions", []) if isinstance(data, dict) else []

    def issue_status(self, key: str) -> str:
        data = self.request("GET", f"/rest/api/3/issue/{key}?fields=status")
        if not isinstance(data, dict):
            return ""
        return str(((data.get("fields") or {}).get("status") or {}).get("name") or "")

    def transition(self, key: str, transition_id: str) -> None:
        self.request("POST", f"/rest/api/3/issue/{key}/transitions", body={"transition": {"id": transition_id}}, write=True)

    def update_remote_link(self, key: str, link_id: str, link: dict[str, Any]) -> None:
        title = str(link.get("title", ""))
        if len(title) > 255:
            title = title[:252] + "..."
        self.request(
            "PUT",
            f"/rest/api/3/issue/{key}/remotelink/{link_id}",
            body={"globalId": link["globalId"], "object": {"url": link["url"], "title": title}},
            write=True,
        )

    def remote_links(self, key: str) -> list[dict[str, Any]]:
        data = self.request("GET", f"/rest/api/3/issue/{key}/remotelink")
        return data if isinstance(data, list) else []

    def create_remote_link(self, key: str, link: dict[str, Any]) -> None:
        title = str(link.get("title", ""))
        if len(title) > 255:
            title = title[:252] + "..."
        self.request(
            "POST",
            f"/rest/api/3/issue/{key}/remotelink",
            body={
                "globalId": link["globalId"],
                "object": {"url": link["url"], "title": title},
            },
            write=True,
        )

    def delete_remote_link(self, key: str, link_id: str) -> None:
        self.request("DELETE", f"/rest/api/3/issue/{key}/remotelink/{link_id}", write=True)
