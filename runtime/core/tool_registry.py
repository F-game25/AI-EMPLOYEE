"""Real tool registry — every tool executes or returns an explicit error.

Rules (non-negotiable):
  - execute() always returns {"status": "success"|"error", "output": any, "error": str}
  - If a tool is not configured, return {"status": "error", "error": "not_configured", ...}
  - NEVER return fake success
  - NEVER return simulated output as if it were real execution
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AI_HOME = Path(os.environ.get("AI_HOME", Path.home() / ".ai-employee"))
LEADS_FILE = AI_HOME / "state" / "leads.jsonl"
WORKSPACE_DIR = AI_HOME / "workspace"


# ── Base ──────────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    status: str          # "success" | "error"
    output: Any = None
    error: str = ""

    def to_dict(self) -> dict:
        d: dict = {"status": self.status}
        if self.output is not None:
            d["output"] = self.output
        if self.error:
            d["error"] = self.error
        return d


class Tool(ABC):
    name: str
    description: str
    required_params: list[str] = []

    def run(self, params: dict) -> dict:
        missing = [p for p in self.required_params if p not in params]
        if missing:
            return ToolResult(
                status="error",
                error=f"missing_required_params: {missing}",
            ).to_dict()
        try:
            result = self.execute(params)
            if not isinstance(result, dict) or result.get("status") not in ("success", "error"):
                return ToolResult(
                    status="error",
                    error=f"tool_returned_invalid_result: {result!r}",
                ).to_dict()
            return result
        except Exception as exc:
            logger.exception("Tool %s raised: %s", self.name, exc)
            return ToolResult(status="error", error=str(exc)).to_dict()

    @abstractmethod
    def execute(self, params: dict) -> dict:
        ...


# ── Web tools ─────────────────────────────────────────────────────────────────

class WebSearchTool(Tool):
    """Search the web via DuckDuckGo HTML endpoint. No API key required."""
    name = "web_search"
    description = "Search the web and return relevant results"
    required_params = ["query"]

    def execute(self, params: dict) -> dict:
        import requests as _requests
        query = str(params["query"])
        max_results = int(params.get("max_results", 5))

        # Use DDG HTML endpoint — returns real search results. Retry up to 3×.
        _user_agents = [
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
        ]
        resp = None
        last_exc = None
        for attempt, ua in enumerate(_user_agents):
            try:
                resp = _requests.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    headers={"User-Agent": ua},
                    timeout=12,
                    allow_redirects=True,
                )
                resp.raise_for_status()
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(0.5 * (attempt + 1))
                resp = None
        if resp is None:
            return ToolResult(status="error", error=f"web_search_failed: {last_exc}").to_dict()

        # Parse results with regex (avoids bs4 import issues)
        import re
        import html as _html
        results = []
        links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)', resp.text)
        snippets = re.findall(r'class="result__snippet"[^>]*>([^<]+)', resp.text)
        for i, (raw_url, title) in enumerate(links[:max_results]):
            real_url_match = re.search(r"uddg=([^&]+)", raw_url)
            real_url = urllib.parse.unquote(real_url_match.group(1)) if real_url_match else raw_url
            snippet = _html.unescape(snippets[i]) if i < len(snippets) else ""
            results.append({
                "title": _html.unescape(title.strip()),
                "url": real_url,
                "snippet": snippet.strip(),
                "source": "duckduckgo",
            })

        if not results:
            # Fallback: try DDG instant answer API for factual queries
            try:
                encoded = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1"})
                req = urllib.request.Request(
                    f"https://api.duckduckgo.com/?{encoded}",
                    headers={"User-Agent": "AI-Employee/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read().decode("utf-8", errors="replace"))
                if data.get("Abstract"):
                    results.append({
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", ""),
                        "snippet": data["Abstract"],
                        "source": data.get("AbstractSource", "duckduckgo"),
                    })
                for topic in data.get("RelatedTopics", [])[:max_results]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:80],
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                            "source": "duckduckgo",
                        })
            except Exception:
                pass

        if not results:
            return ToolResult(
                status="error",
                error="no_results_found",
                output={"query": query, "count": 0},
            ).to_dict()

        results = results[:max_results]
        return ToolResult(
            status="success",
            output={"query": query, "count": len(results), "results": results},
        ).to_dict()


class FetchPageTool(Tool):
    """Fetch a web page and return its text content."""
    name = "fetch_page"
    description = "Fetch the text content of a web page by URL"
    required_params = ["url"]

    def execute(self, params: dict) -> dict:
        url = str(params["url"])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Employee/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            return ToolResult(status="error", error=f"fetch_failed: {exc}").to_dict()

        # Strip HTML tags minimally via regex
        import re
        text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = text[:8000]  # cap at 8k chars

        return ToolResult(
            status="success",
            output={"url": url, "content": text, "length": len(text)},
        ).to_dict()


# ── Data tools ────────────────────────────────────────────────────────────────

class SaveLeadsTool(Tool):
    """Persist structured leads to the local CRM store."""
    name = "save_leads"
    description = "Save a list of leads to the CRM"
    required_params = ["leads"]

    def execute(self, params: dict) -> dict:
        leads = params["leads"]
        if not isinstance(leads, list):
            return ToolResult(status="error", error="leads must be a list").to_dict()
        LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        written = 0
        with LEADS_FILE.open("a", encoding="utf-8") as fh:
            for lead in leads:
                if isinstance(lead, dict):
                    lead.setdefault("saved_at", ts)
                    fh.write(json.dumps(lead) + "\n")
                    written += 1
        return ToolResult(
            status="success",
            output={"saved": written, "store": str(LEADS_FILE)},
        ).to_dict()


class ReadLeadsTool(Tool):
    """Read leads from the local CRM store."""
    name = "read_leads"
    description = "Read leads from the CRM"

    def execute(self, params: dict) -> dict:
        limit = int(params.get("limit", 50))
        if not LEADS_FILE.exists():
            return ToolResult(status="success", output={"leads": [], "count": 0}).to_dict()
        leads = []
        with LEADS_FILE.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        leads.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        leads = leads[-limit:]
        return ToolResult(
            status="success",
            output={"leads": leads, "count": len(leads)},
        ).to_dict()


class SaveFileTool(Tool):
    """Write content to a file in the workspace."""
    name = "save_file"
    description = "Save content to a named file in the workspace"
    required_params = ["filename", "content"]

    def execute(self, params: dict) -> dict:
        filename = Path(params["filename"]).name  # strip any directory traversal
        if not filename:
            return ToolResult(status="error", error="empty filename").to_dict()
        dest = WORKSPACE_DIR / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        content_str = str(params["content"])
        dest.write_text(content_str, encoding="utf-8")
        return ToolResult(
            status="success",
            output={
                "path": str(dest),
                "bytes": dest.stat().st_size,
                "content": content_str[:50000],
                "filename": filename,
            },
        ).to_dict()


# ── LLM tools (valid — LLM as a real processor, not a fake executor) ──────────

class LLMExtractTool(Tool):
    """Use LLM to extract structured data from raw text. This is genuine extraction
    from real source material, not fabrication."""
    name = "llm_extract"
    description = "Extract structured data from raw text using LLM"
    required_params = ["text", "schema"]

    def execute(self, params: dict) -> dict:
        from core.tool_llm_caller import call_llm_for_tool
        text = str(params["text"])[:6000]
        schema = params["schema"]
        prompt = (
            f"Extract the following fields from the text below. "
            f"Return ONLY a JSON object matching this schema: {json.dumps(schema)}\n\n"
            f"Text:\n{text}\n\n"
            f"JSON output:"
        )
        raw = call_llm_for_tool(prompt)
        if raw is None:
            return ToolResult(status="error", error="llm_unavailable").to_dict()
        import re
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return ToolResult(status="error", error=f"llm_returned_no_json: {raw[:200]}").to_dict()
        try:
            extracted = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            return ToolResult(status="error", error=f"json_parse_failed: {exc}").to_dict()
        return ToolResult(status="success", output=extracted).to_dict()


class LLMGenerateTool(Tool):
    """Generate content using LLM. Valid tool — produces real text output."""
    name = "llm_generate"
    description = "Generate content (emails, posts, reports) using LLM"
    required_params = ["prompt"]

    def execute(self, params: dict) -> dict:
        from core.tool_llm_caller import call_llm_for_tool
        full_prompt = str(params["prompt"])
        if params.get("context"):
            full_prompt = f"Context:\n{params['context']}\n\n{full_prompt}"
        result = call_llm_for_tool(full_prompt)
        if result is None:
            return ToolResult(status="error", error="llm_unavailable").to_dict()
        return ToolResult(status="success", output={"content": result}).to_dict()


# ── Communication tools (fail explicitly when not configured) ─────────────────

class SendEmailTool(Tool):
    """Send a real email. Returns error if SMTP/SendGrid not configured."""
    name = "send_email"
    description = "Send an email via SMTP or SendGrid"
    required_params = ["to", "subject", "body"]

    def execute(self, params: dict) -> dict:
        sg_key = os.environ.get("SENDGRID_API_KEY", "")
        smtp_host = os.environ.get("SMTP_HOST", "")
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")

        if not sg_key and not (smtp_host and smtp_user and smtp_pass):
            return ToolResult(
                status="error",
                error="not_configured",
                output={
                    "required": "Set SENDGRID_API_KEY or SMTP_HOST+SMTP_USER+SMTP_PASS in ~/.ai-employee/.env",
                    "dry_run_result": {"to": params["to"], "subject": params["subject"]},
                },
            ).to_dict()

        to = params["to"]
        subject = params["subject"]
        body = params["body"]

        if sg_key:
            return self._send_sendgrid(to, subject, body, sg_key)
        return self._send_smtp(to, subject, body, smtp_host, smtp_user, smtp_pass)

    def _send_sendgrid(self, to: str, subject: str, body: str, api_key: str) -> dict:
        payload = json.dumps({
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": os.environ.get("FROM_EMAIL", "ai@ai-employee.io")},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }).encode()
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return ToolResult(
                    status="success",
                    output={"to": to, "subject": subject, "provider": "sendgrid", "http_status": resp.status},
                ).to_dict()
        except urllib.error.HTTPError as exc:
            return ToolResult(status="error", error=f"sendgrid_error:{exc.code}:{exc.reason}").to_dict()

    def _send_smtp(self, to: str, subject: str, body: str, host: str, user: str, password: str) -> dict:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        port = int(os.environ.get("SMTP_PORT", 587))
        try:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
            return ToolResult(
                status="success",
                output={"to": to, "subject": subject, "provider": "smtp"},
            ).to_dict()
        except Exception as exc:
            return ToolResult(status="error", error=f"smtp_error:{exc}").to_dict()


# ── API-backed tools (explicit error when keys missing) ───────────────────────

class ApolloSearchTool(Tool):
    """Search Apollo.io for leads. Returns explicit error if APOLLO_API_KEY unset."""
    name = "apollo_search"
    description = "Search Apollo.io for leads by ICP (Ideal Customer Profile)"
    required_params = ["icp"]

    def execute(self, params: dict) -> dict:
        api_key = os.environ.get("APOLLO_API_KEY", "")
        if not api_key:
            return ToolResult(
                status="error",
                error="not_configured",
                output={
                    "required_env_vars": ["APOLLO_API_KEY"],
                    "setup": "Add APOLLO_API_KEY to ~/.ai-employee/.env",
                    "get_key": "https://app.apollo.io/#/settings/integrations/api",
                },
            ).to_dict()

        icp = params["icp"]
        limit = int(params.get("limit", 10))
        payload = json.dumps({
            "api_key": api_key,
            "q_keywords": icp if isinstance(icp, str) else json.dumps(icp),
            "per_page": min(limit, 25),
            "page": 1,
        }).encode()
        req = urllib.request.Request(
            "https://api.apollo.io/api/v1/mixed_people/search",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "AI-Employee/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return ToolResult(status="error", error=f"apollo_api_error:{exc.code}:{err_body[:200]}").to_dict()
        except Exception as exc:
            return ToolResult(status="error", error=f"apollo_request_failed:{exc}").to_dict()

        people = body.get("people", [])
        leads = []
        for p in people[:limit]:
            leads.append({
                "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                "title": p.get("title", ""),
                "company": (p.get("organization") or {}).get("name", ""),
                "email": p.get("email", ""),
                "linkedin": p.get("linkedin_url", ""),
                "source": "apollo",
            })
        return ToolResult(
            status="success",
            output={"leads": leads, "count": len(leads), "source": "apollo"},
        ).to_dict()


class LinkedInPostTool(Tool):
    """Publish a post to LinkedIn via UGC API. Returns error if tokens unset."""
    name = "linkedin_post"
    description = "Publish a post to LinkedIn"
    required_params = ["content"]

    def execute(self, params: dict) -> dict:
        token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
        person_urn = os.environ.get("LINKEDIN_PERSON_URN", "")
        if not token or not person_urn:
            return ToolResult(
                status="error",
                error="not_configured",
                output={
                    "required_env_vars": ["LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN"],
                    "setup": "Add LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN to ~/.ai-employee/.env",
                    "docs": "https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api",
                },
            ).to_dict()

        content = str(params["content"])
        payload = json.dumps({
            "author": f"urn:li:person:{person_urn}",
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": content},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }).encode()
        req = urllib.request.Request(
            "https://api.linkedin.com/v2/ugcPosts",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202401",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                post_id = resp.headers.get("x-restli-id", "unknown")
                return ToolResult(
                    status="success",
                    output={"post_id": post_id, "content_length": len(content), "provider": "linkedin"},
                ).to_dict()
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            return ToolResult(status="error", error=f"linkedin_api_error:{exc.code}:{err_body[:200]}").to_dict()
        except Exception as exc:
            return ToolResult(status="error", error=f"linkedin_request_failed:{exc}").to_dict()


class WebsiteBuilderTool(Tool):
    """Generate an HTML website via LLM and save to workspace."""
    name = "website_builder"
    description = "Generate a complete HTML website for a given purpose and save to workspace"
    required_params = ["purpose"]

    def execute(self, params: dict) -> dict:
        from core.tool_llm_caller import call_llm_for_tool
        purpose = str(params["purpose"])
        style = params.get("style", "modern, professional, clean")
        prompt = (
            f"Generate a complete, single-file HTML website for: {purpose}\n"
            f"Style: {style}\n"
            f"Requirements:\n"
            f"- Full HTML5 document with embedded CSS in <style> tags\n"
            f"- Professional design: hero section, features/benefits, call-to-action\n"
            f"- Mobile-responsive using CSS flexbox/grid\n"
            f"- No external dependencies (no CDN links, no JavaScript frameworks)\n"
            f"- Return ONLY the complete HTML document, starting with <!DOCTYPE html>"
        )
        result = call_llm_for_tool(prompt)
        if result is None:
            return ToolResult(status="error", error="llm_unavailable").to_dict()

        import re as _re
        html_match = _re.search(r"<!DOCTYPE html>[\s\S]*", result, _re.IGNORECASE)
        html_content = html_match.group(0) if html_match else result

        filename = Path(params.get("filename", "index.html")).name or "index.html"
        dest = WORKSPACE_DIR / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html_content, encoding="utf-8")
        return ToolResult(
            status="success",
            output={
                "path": str(dest),
                "bytes": dest.stat().st_size,
                "purpose": purpose,
                "deploy_hint": f"Upload {dest} to any static host (Netlify, Vercel, GitHub Pages).",
                "html_content": html_content,
                "filename": filename,
            },
        ).to_dict()


class NotConfiguredStubTool(Tool):
    """Placeholder for tools that require external API keys not yet configured."""

    def __init__(self, name: str, description: str, required_env: list[str]) -> None:
        self.name = name
        self.description = description
        self._required_env = required_env

    def execute(self, params: dict) -> dict:
        return ToolResult(
            status="error",
            error="not_configured",
            output={
                "tool": self.name,
                "required_env_vars": self._required_env,
                "setup": "Add the required keys to ~/.ai-employee/.env to enable this tool",
            },
        ).to_dict()


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, Tool] = {}


def _build_registry() -> dict[str, Tool]:
    tools: list[Tool] = [
        WebSearchTool(),
        FetchPageTool(),
        SaveLeadsTool(),
        ReadLeadsTool(),
        SaveFileTool(),
        LLMExtractTool(),
        LLMGenerateTool(),
        SendEmailTool(),
        ApolloSearchTool(),
        LinkedInPostTool(),
        WebsiteBuilderTool(),
        NotConfiguredStubTool(
            "twitter_post",
            "Post a tweet",
            ["TWITTER_API_KEY", "TWITTER_API_SECRET", "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"],
        ),
        NotConfiguredStubTool(
            "phantombuster_run",
            "Run a PhantomBuster automation phantom",
            ["PHANTOMBUSTER_API_KEY"],
        ),
    ]
    return {t.name: t for t in tools}


def get_tool(name: str) -> Tool | None:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = _build_registry()
    return _REGISTRY.get(name)


def list_tools() -> list[dict]:
    global _REGISTRY
    if not _REGISTRY:
        _REGISTRY = _build_registry()
    return [
        {"name": t.name, "description": t.description, "required_params": getattr(t, "required_params", [])}
        for t in _REGISTRY.values()
    ]
