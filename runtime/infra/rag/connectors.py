"""Enterprise data source connectors.

Each connector implements:
  list_changed(since_ts)  → list[SourceDocument]  (incremental sync)
  fetch(source_id)        → SourceDocument         (on-demand fetch)

Connectors are intentionally thin — they translate source-native objects
into SourceDocument, deferring chunking/embedding to the pipeline.

Credentials are read from the SecretsBroker (never hardcoded).
Missing env/secrets → connector returns empty list (graceful degradation).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from infra.rag.schema import SourceDocument, SourceType

logger = logging.getLogger("rag.connectors")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _now() -> float:
    return time.time()


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseConnector(ABC):
    source_type: SourceType

    def __init__(self, tenant_id: str, credentials: dict[str, Any]) -> None:
        self.tenant_id = tenant_id
        self._creds = credentials

    @abstractmethod
    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        """Return documents modified after since_ts (unix seconds)."""

    @abstractmethod
    async def fetch(self, source_id: str) -> SourceDocument | None:
        """Fetch a single document by source-native ID."""

    async def list_all(self) -> list[SourceDocument]:
        return await self.list_changed(0.0)

    def _make_doc(
        self,
        source_id: str,
        title: str,
        url: str,
        raw_text: str,
        metadata: dict,
        permissions: list[str],
        modified_at: float | None = None,
        content_type: str = "text/plain",
    ) -> SourceDocument:
        doc_id = f"{self.source_type.value}::{self.tenant_id}::{source_id}"
        return SourceDocument(
            id=doc_id,
            source_type=self.source_type,
            source_id=source_id,
            tenant_id=self.tenant_id,
            title=title,
            url=url,
            content_hash=_hash(raw_text),
            raw_text=raw_text,
            metadata=metadata,
            permissions=permissions,
            ingested_at=_now(),
            modified_at=modified_at or _now(),
            content_type=content_type,
        )


# ── SharePoint connector ──────────────────────────────────────────────────────

class SharePointConnector(BaseConnector):
    """Microsoft Graph API connector for SharePoint / OneDrive."""
    source_type = SourceType.SHAREPOINT

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        token = self._creds.get("access_token")
        if not token:
            logger.debug("SharePoint: no access_token — skipping")
            return []
        try:
            import httpx
            since_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(since_ts)) if since_ts else ""
            filter_q = f"lastModifiedDateTime ge {since_iso}" if since_iso else ""
            params = {"$select": "id,name,webUrl,lastModifiedDateTime,createdBy,file", "$top": 200}
            if filter_q:
                params["$filter"] = filter_q

            site_id = self._creds.get("site_id", "root")
            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root/children"
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
                if not resp.is_success:
                    return []
                items = resp.json().get("value", [])

            docs: list[SourceDocument] = []
            for item in items:
                if "file" not in item:
                    continue
                content = await self._download(client, token, item["id"], site_id)
                if content is None:
                    continue
                docs.append(self._make_doc(
                    source_id=item["id"],
                    title=item.get("name", ""),
                    url=item.get("webUrl", ""),
                    raw_text=content,
                    metadata={"author": item.get("createdBy", {}).get("user", {}).get("displayName", "")},
                    permissions=["org"],
                    modified_at=self._parse_ts(item.get("lastModifiedDateTime", "")),
                ))
            return docs
        except Exception as e:
            logger.warning("SharePoint connector error: %s", e)
            return []

    async def _download(self, client: Any, token: str, item_id: str, site_id: str) -> str | None:
        try:
            import httpx
            url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/{item_id}/content"
            async with httpx.AsyncClient(timeout=30.0) as c:
                r = await c.get(url, headers={"Authorization": f"Bearer {token}"}, follow_redirects=True)
                return r.text if r.is_success else None
        except Exception:
            return None

    async def fetch(self, source_id: str) -> SourceDocument | None:
        docs = await self.list_changed(0.0)
        return next((d for d in docs if d.source_id == source_id), None)

    @staticmethod
    def _parse_ts(iso: str) -> float:
        import datetime
        try:
            return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            return _now()


# ── Google Drive connector ────────────────────────────────────────────────────

class GoogleDriveConnector(BaseConnector):
    source_type = SourceType.GOOGLE_DRIVE

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        sa_json = self._creds.get("service_account_json")
        if not sa_json:
            logger.debug("GoogleDrive: no service_account_json — skipping")
            return []
        try:
            import httpx, datetime
            q = "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
            if since_ts:
                since_iso = datetime.datetime.utcfromtimestamp(since_ts).strftime("%Y-%m-%dT%H:%M:%SZ")
                q += f" and modifiedTime > '{since_iso}'"
            token = await self._get_oauth_token(sa_json)
            if not token:
                return []
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": q, "fields": "files(id,name,webViewLink,modifiedTime,owners)", "pageSize": 200},
                )
                if not resp.is_success:
                    return []
                files = resp.json().get("files", [])
            docs: list[SourceDocument] = []
            for f in files:
                content = await self._export(token, f["id"])
                if not content:
                    continue
                docs.append(self._make_doc(
                    source_id=f["id"],
                    title=f.get("name", ""),
                    url=f.get("webViewLink", ""),
                    raw_text=content,
                    metadata={"owners": f.get("owners", [])},
                    permissions=["org"],
                    modified_at=self._parse_ts(f.get("modifiedTime", "")),
                ))
            return docs
        except Exception as e:
            logger.warning("GoogleDrive connector error: %s", e)
            return []

    async def _get_oauth_token(self, sa_json: str) -> str | None:
        try:
            import httpx, json as _json, time as _time
            sa = _json.loads(sa_json) if isinstance(sa_json, str) else sa_json
            # In production: use google-auth library; here we signal the pattern
            return sa.get("_dev_token")  # dev fallback
        except Exception:
            return None

    async def _export(self, token: str, file_id: str) -> str | None:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"mimeType": "text/plain"},
                )
                return resp.text if resp.is_success else None
        except Exception:
            return None

    async def fetch(self, source_id: str) -> SourceDocument | None:
        docs = await self.list_changed(0.0)
        return next((d for d in docs if d.source_id == source_id), None)

    @staticmethod
    def _parse_ts(iso: str) -> float:
        import datetime
        try:
            return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            return _now()


# ── Slack connector ───────────────────────────────────────────────────────────

class SlackConnector(BaseConnector):
    source_type = SourceType.SLACK

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        token = self._creds.get("bot_token")
        if not token:
            logger.debug("Slack: no bot_token — skipping")
            return []
        try:
            import httpx
            headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                channels_resp = await client.get(
                    "https://slack.com/api/conversations.list",
                    headers=headers,
                    params={"types": "public_channel,private_channel", "limit": 200},
                )
                channels = channels_resp.json().get("channels", [])
                docs: list[SourceDocument] = []
                for ch in channels:
                    msgs = await self._fetch_messages(client, headers, ch["id"], since_ts)
                    if not msgs:
                        continue
                    text = "\n".join(f"[{m.get('user','')}] {m.get('text','')}" for m in msgs)
                    docs.append(self._make_doc(
                        source_id=f"channel::{ch['id']}",
                        title=f"#{ch.get('name', ch['id'])}",
                        url=f"https://slack.com/archives/{ch['id']}",
                        raw_text=text,
                        metadata={"channel_id": ch["id"], "channel_name": ch.get("name", "")},
                        permissions=ch.get("members", ["org"]),
                        modified_at=_now(),
                    ))
            return docs
        except Exception as e:
            logger.warning("Slack connector error: %s", e)
            return []

    async def _fetch_messages(self, client: Any, headers: dict, channel: str, since_ts: float) -> list[dict]:
        try:
            params: dict = {"channel": channel, "limit": 200}
            if since_ts:
                params["oldest"] = str(since_ts)
            resp = await client.get("https://slack.com/api/conversations.history", headers=headers, params=params)
            return resp.json().get("messages", [])
        except Exception:
            return []

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return None


# ── Gmail connector ───────────────────────────────────────────────────────────

class GmailConnector(BaseConnector):
    source_type = SourceType.GMAIL

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        token = self._creds.get("access_token")
        if not token:
            logger.debug("Gmail: no access_token — skipping")
            return []
        try:
            import httpx, base64
            after = int(since_ts) if since_ts else 0
            q = f"after:{after}" if after else ""
            async with httpx.AsyncClient(timeout=20.0) as client:
                headers = {"Authorization": f"Bearer {token}"}
                list_resp = await client.get(
                    "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                    headers=headers,
                    params={"q": q, "maxResults": 200},
                )
                messages = list_resp.json().get("messages", [])
                docs: list[SourceDocument] = []
                for msg in messages[:50]:  # cap per cycle
                    detail = await client.get(
                        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg['id']}",
                        headers=headers,
                        params={"format": "full"},
                    )
                    d = detail.json()
                    body = self._extract_body(d)
                    subject = next((h["value"] for h in d.get("payload", {}).get("headers", []) if h["name"] == "Subject"), "")
                    from_h = next((h["value"] for h in d.get("payload", {}).get("headers", []) if h["name"] == "From"), "")
                    docs.append(self._make_doc(
                        source_id=msg["id"],
                        title=subject,
                        url=f"https://mail.google.com/mail/u/0/#inbox/{msg['id']}",
                        raw_text=body,
                        metadata={"from": from_h, "subject": subject},
                        permissions=["user"],
                        modified_at=int(d.get("internalDate", 0)) / 1000,
                    ))
            return docs
        except Exception as e:
            logger.warning("Gmail connector error: %s", e)
            return []

    @staticmethod
    def _extract_body(msg: dict) -> str:
        import base64
        parts = msg.get("payload", {}).get("parts", [msg.get("payload", {})])
        for p in parts:
            if p.get("mimeType") == "text/plain":
                data = p.get("body", {}).get("data", "")
                try:
                    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                except Exception:
                    pass
        return ""

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return None


# ── Jira connector ────────────────────────────────────────────────────────────

class JiraConnector(BaseConnector):
    source_type = SourceType.JIRA

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        base_url = self._creds.get("base_url")
        token = self._creds.get("api_token")
        email = self._creds.get("email")
        if not (base_url and token and email):
            logger.debug("Jira: missing credentials — skipping")
            return []
        try:
            import httpx, datetime
            since_str = datetime.datetime.utcfromtimestamp(since_ts).strftime("%Y-%m-%d") if since_ts else ""
            jql = f"updated >= '{since_str}'" if since_str else "ORDER BY updated DESC"
            auth = (email, token)
            async with httpx.AsyncClient(timeout=20.0, auth=auth) as client:
                resp = await client.get(
                    f"{base_url}/rest/api/3/search",
                    params={"jql": jql, "maxResults": 200, "fields": "summary,description,assignee,updated,status,project"},
                )
                if not resp.is_success:
                    return []
                issues = resp.json().get("issues", [])
            docs: list[SourceDocument] = []
            for issue in issues:
                fields = issue.get("fields", {})
                desc = self._extract_adf(fields.get("description") or {})
                text = f"{fields.get('summary','')}\n\n{desc}"
                docs.append(self._make_doc(
                    source_id=issue["id"],
                    title=f"[{issue['key']}] {fields.get('summary','')}",
                    url=f"{base_url}/browse/{issue['key']}",
                    raw_text=text,
                    metadata={"key": issue["key"], "status": fields.get("status", {}).get("name", ""),
                              "assignee": (fields.get("assignee") or {}).get("displayName", "")},
                    permissions=["org"],
                    modified_at=self._parse_ts(fields.get("updated", "")),
                ))
            return docs
        except Exception as e:
            logger.warning("Jira connector error: %s", e)
            return []

    @staticmethod
    def _extract_adf(node: dict) -> str:
        if not node:
            return ""
        if node.get("type") == "text":
            return node.get("text", "")
        content = node.get("content", [])
        return " ".join(JiraConnector._extract_adf(c) for c in content)

    @staticmethod
    def _parse_ts(iso: str) -> float:
        import datetime
        try:
            return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
        except Exception:
            return _now()

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return None


# ── Confluence connector ──────────────────────────────────────────────────────

class ConfluenceConnector(BaseConnector):
    source_type = SourceType.CONFLUENCE

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        base_url = self._creds.get("base_url")
        token = self._creds.get("api_token")
        email = self._creds.get("email")
        if not (base_url and token and email):
            logger.debug("Confluence: missing credentials — skipping")
            return []
        try:
            import httpx, datetime
            since_str = datetime.datetime.utcfromtimestamp(since_ts).strftime("%Y-%m-%d") if since_ts else ""
            cql = f'type=page and lastModified > "{since_str}"' if since_str else "type=page ORDER BY lastModified DESC"
            auth = (email, token)
            async with httpx.AsyncClient(timeout=20.0, auth=auth) as client:
                resp = await client.get(
                    f"{base_url}/rest/api/content/search",
                    params={"cql": cql, "limit": 200, "expand": "body.storage,version,space"},
                )
                if not resp.is_success:
                    return []
                pages = resp.json().get("results", [])
            docs: list[SourceDocument] = []
            for page in pages:
                body_html = page.get("body", {}).get("storage", {}).get("value", "")
                text = self._strip_html(body_html)
                docs.append(self._make_doc(
                    source_id=page["id"],
                    title=page.get("title", ""),
                    url=f"{base_url}{page.get('_links', {}).get('webui', '')}",
                    raw_text=text,
                    metadata={"space": page.get("space", {}).get("key", ""),
                              "version": page.get("version", {}).get("number", 0)},
                    permissions=["org"],
                    modified_at=_now(),
                ))
            return docs
        except Exception as e:
            logger.warning("Confluence connector error: %s", e)
            return []

    @staticmethod
    def _strip_html(html: str) -> str:
        import re
        return re.sub(r"<[^>]+>", " ", html).strip()

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return None


# ── CRM connector (generic REST) ──────────────────────────────────────────────

class CRMConnector(BaseConnector):
    """Generic CRM connector. Supports HubSpot / Salesforce via config."""
    source_type = SourceType.CRM

    async def list_changed(self, since_ts: float) -> list[SourceDocument]:
        crm_type = self._creds.get("crm_type", "hubspot")
        if crm_type == "hubspot":
            return await self._hubspot(since_ts)
        return []

    async def _hubspot(self, since_ts: float) -> list[SourceDocument]:
        token = self._creds.get("access_token")
        if not token:
            logger.debug("CRM/HubSpot: no access_token — skipping")
            return []
        try:
            import httpx
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            body: dict = {"limit": 200, "properties": ["firstname", "lastname", "email", "company", "notes_last_updated"]}
            if since_ts:
                body["filterGroups"] = [{"filters": [{"propertyName": "notes_last_updated",
                                                       "operator": "GT", "value": int(since_ts * 1000)}]}]
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post("https://api.hubapi.com/crm/v3/objects/contacts/search",
                                         headers=headers, json=body)
                if not resp.is_success:
                    return []
                contacts = resp.json().get("results", [])
            docs: list[SourceDocument] = []
            for c in contacts:
                props = c.get("properties", {})
                name = f"{props.get('firstname','')} {props.get('lastname','')}".strip()
                text = f"Contact: {name}\nEmail: {props.get('email','')}\nCompany: {props.get('company','')}"
                docs.append(self._make_doc(
                    source_id=c["id"],
                    title=name or c["id"],
                    url=f"https://app.hubspot.com/contacts/{c['id']}",
                    raw_text=text,
                    metadata=props,
                    permissions=["crm_users"],
                    modified_at=_now(),
                ))
            return docs
        except Exception as e:
            logger.warning("CRM/HubSpot connector error: %s", e)
            return []

    async def fetch(self, source_id: str) -> SourceDocument | None:
        return None


# ── Registry ──────────────────────────────────────────────────────────────────

_CONNECTOR_MAP: dict[SourceType, type[BaseConnector]] = {
    SourceType.SHAREPOINT:   SharePointConnector,
    SourceType.GOOGLE_DRIVE: GoogleDriveConnector,
    SourceType.SLACK:        SlackConnector,
    SourceType.GMAIL:        GmailConnector,
    SourceType.JIRA:         JiraConnector,
    SourceType.CONFLUENCE:   ConfluenceConnector,
    SourceType.CRM:          CRMConnector,
}


def get_connector(source_type: SourceType, tenant_id: str, credentials: dict) -> BaseConnector:
    cls = _CONNECTOR_MAP.get(source_type)
    if not cls:
        raise ValueError(f"No connector for source type: {source_type}")
    return cls(tenant_id, credentials)
