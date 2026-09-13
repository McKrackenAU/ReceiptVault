from __future__ import annotations

import time
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.services import graph_mock
from app.services.oauth import MS_SCOPES

GRAPH_ROOT = "https://graph.microsoft.com/v1.0/"
TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


class GraphError(Exception):
    def __init__(self, status: int, detail: str, retry_after: float | None = None):
        self.status = status
        self.detail = detail
        self.retry_after = retry_after
        super().__init__(detail)


class GraphClient:
    def __init__(self, settings: Settings, access_token: str, mock_identity: str | None = None):
        self.settings = settings
        self.access_token = access_token
        self.mock_identity = mock_identity

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if self.mock_identity:
            raise RuntimeError("live request attempted in mock client")
        last_error = None
        for attempt in range(6):
            with httpx.Client(timeout=60.0) as client:
                response = client.request(method, url, headers=self._headers(), **kwargs)
            if response.status_code in {429, 503, 504}:
                retry = float(response.headers.get("Retry-After", 1 + attempt * 2))
                jitter = 0.25 * attempt
                time.sleep(retry + jitter)
                last_error = GraphError(response.status_code, response.text[:300], retry)
                continue
            if response.status_code >= 400:
                raise GraphError(response.status_code, response.text[:300])
            return response
        raise last_error or GraphError(429, "throttled")

    def profile(self) -> dict:
        if self.mock_identity:
            return graph_mock.MOCK_IDENTITIES[self.mock_identity]
        return self._request("GET", urljoin(GRAPH_ROOT, "me")).json()

    def list_folders(self) -> list[dict]:
        if self.mock_identity:
            return graph_mock.folders()
        data = self._request("GET", urljoin(GRAPH_ROOT, "me/mailFolders?$top=100")).json()
        return data.get("value", [])

    def iter_messages(self, folder_id: str, cursor: str | None = None, page_size: int = 25):
        if self.mock_identity:
            messages = graph_mock.messages_for(self.mock_identity)
            if folder_id != "inbox":
                messages = []
            start = int(cursor or 0)
            page = messages[start : start + page_size]
            nxt = start + page_size if start + page_size < len(messages) else None
            yield page, str(nxt) if nxt is not None else None
            return
        url = cursor or urljoin(
            GRAPH_ROOT,
            f"me/mailFolders/{folder_id}/messages?$top={page_size}&$select=id,subject,from,toRecipients,receivedDateTime,sentDateTime,hasAttachments,internetMessageId,body,parentFolderId",
        )
        while url:
            data = self._request("GET", url).json()
            yield data.get("value", []), data.get("@odata.nextLink")
            url = None

    def message_mime(self, message_id: str) -> bytes:
        if self.mock_identity:
            for item in graph_mock.messages_for(self.mock_identity):
                if item["id"] == message_id:
                    return item["mime"]
            return b""
        response = self._request("GET", urljoin(GRAPH_ROOT, f"me/messages/{message_id}/$value"))
        return response.content

    def attachments(self, message_id: str) -> list[dict]:
        if self.mock_identity:
            for item in graph_mock.messages_for(self.mock_identity):
                if item["id"] == message_id:
                    return item["attachments"]
            return []
        data = self._request("GET", urljoin(GRAPH_ROOT, f"me/messages/{message_id}/attachments")).json()
        items = []
        for att in data.get("value", []):
            raw = att.get("contentBytes")
            if isinstance(raw, str):
                import base64

                raw = base64.b64decode(raw)
            items.append(
                {
                    "id": att.get("id"),
                    "name": att.get("name"),
                    "contentType": att.get("contentType"),
                    "contentBytes": raw or b"",
                    "size": att.get("size"),
                }
            )
        return items


def start_device_code(settings: Settings) -> dict:
    if settings.graph_mock:
        return {
            "device_code": "mock-device",
            "user_code": "RV-MOCK",
            "verification_uri": "https://www.microsoft.com/link",
            "verification_uri_complete": "https://www.microsoft.com/link",
            "expires_in": 900,
            "interval": 2,
            "message": "Demo mode: wait a moment and the mock inbox will connect.",
        }
    if not settings.ms_client_id:
        raise GraphError(400, "Missing Entra app client ID")
    url = f"https://login.microsoftonline.com/{settings.ms_tenant}/oauth2/v2.0/devicecode"
    data = {"client_id": settings.ms_client_id, "scope": " ".join(MS_SCOPES)}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, data=data)
    if response.status_code >= 400:
        raise GraphError(response.status_code, response.text[:400])
    return response.json()


def poll_device_code(settings: Settings, device_code: str) -> dict:
    if settings.graph_mock or device_code == "mock-device":
        return {
            "access_token": "mock-access-hotmail-one",
            "refresh_token": "mock-refresh-hotmail-one",
            "expires_in": 3600,
            "mock_identity": "hotmail-one",
        }
    url = TOKEN_URL.format(tenant=settings.ms_tenant)
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": settings.ms_client_id,
        "device_code": device_code,
    }
    if settings.ms_client_secret:
        data["client_secret"] = settings.ms_client_secret
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, data=data)
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        err = body.get("error") or "token_error"
        desc = body.get("error_description") or response.text[:400]
        raise GraphError(response.status_code, f"{err}: {desc}")
    return body


def exchange_code(settings: Settings, code: str, verifier: str) -> dict:
    if settings.graph_mock or code.startswith("mock-code-"):
        identity = code.removeprefix("mock-code-") or "hotmail-one"
        profile = graph_mock.MOCK_IDENTITIES[identity]
        return {
            "access_token": f"mock-access-{identity}",
            "refresh_token": f"mock-refresh-{identity}",
            "expires_in": 3600,
            "id_token_claims": profile,
            "mock_identity": identity,
        }
    url = TOKEN_URL.format(tenant=settings.ms_tenant)
    data = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oauth_redirect_uri,
        "code_verifier": verifier,
        "scope": " ".join(MS_SCOPES),
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, data=data)
    if response.status_code >= 400:
        raise GraphError(response.status_code, response.text[:400])
    return response.json()


def refresh_access(settings: Settings, refresh_token: str) -> dict:
    if settings.graph_mock or refresh_token.startswith("mock-refresh-"):
        return {"access_token": refresh_token.replace("refresh", "access"), "refresh_token": refresh_token, "expires_in": 3600}
    url = TOKEN_URL.format(tenant=settings.ms_tenant)
    data = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(MS_SCOPES),
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, data=data)
    if response.status_code >= 400:
        raise GraphError(response.status_code, "refresh failed")
    return response.json()


def mask_address(address: str) -> str:
    if "@" not in address:
        return "***"
    local, domain = address.split("@", 1)
    shown = local[:1] + "***" if local else "***"
    return f"{shown}@{domain}"
