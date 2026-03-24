"""Newsletter Bot — personalized email newsletter automation.

Reads RSS feeds, uses AI to curate and rewrite content, manages a subscriber
list with segments, generates full newsletter HTML/text, and sends via SMTP
or saves to an outbox when credentials are absent.

Commands:
  newsletter create <topic>          — generate a complete newsletter issue
  newsletter subscribe <email> [seg] — add subscriber to list
  newsletter unsubscribe <email>     — remove subscriber
  newsletter send <issue_id>         — format and send (or save to outbox)
  newsletter subscribers             — show subscriber count by segment
  newsletter rss <url>               — add RSS feed to monitoring list
  newsletter feeds                   — show monitored RSS feeds + last fetch
  newsletter preview <topic>         — generate newsletter preview (300 chars/section)
  newsletter status                  — issues created, subscribers, last send
"""
import json, os, re, sys, time, smtplib
import urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

AI_HOME         = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE      = AI_HOME / "state" / "newsletter-bot.state.json"
CHATLOG         = AI_HOME / "state" / "chatlog.jsonl"
SUBSCRIBERS_FILE = AI_HOME / "state" / "newsletter-subscribers.json"
ISSUES_DIR      = AI_HOME / "state" / "newsletter-issues"
FEEDS_FILE      = AI_HOME / "config" / "newsletter-feeds.json"
OUTBOX_FILE     = AI_HOME / "state" / "newsletter-outbox.jsonl"

POLL_INTERVAL       = int(os.environ.get("NEWSLETTER_POLL_INTERVAL", "5"))
NEWSLETTER_NAME     = os.environ.get("NEWSLETTER_NAME", "AI Newsletter")
NEWSLETTER_FREQ     = os.environ.get("NEWSLETTER_FREQUENCY", "weekly")
SMTP_HOST           = os.environ.get("SMTP_HOST", "")
SMTP_PORT           = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER           = os.environ.get("SMTP_USER", "")
SMTP_PASS           = os.environ.get("SMTP_PASS", "")
SMTP_FROM           = os.environ.get("SMTP_FROM", "")
MAILCHIMP_API_KEY   = os.environ.get("MAILCHIMP_API_KEY", "")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai as _query_ai, search_web as _search_web  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


# ── helpers ───────────────────────────────────────────────────────────────────

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, indent=2))

def load_chatlog():
    if not CHATLOG.exists():
        return []
    try:
        return [json.loads(l) for l in CHATLOG.read_text().splitlines() if l.strip()]
    except Exception:
        return []

def append_chatlog(e):
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(e) + "\n")

def _ai(prompt: str, system: str = "") -> str:
    if not _AI_AVAILABLE:
        return "[AI unavailable — install deps]"
    return (_query_ai(prompt, system_prompt=system) or {}).get("answer", "")

def load_subscribers() -> dict:
    if not SUBSCRIBERS_FILE.exists():
        return {"subscribers": [], "updated_at": now_iso()}
    try:
        return json.loads(SUBSCRIBERS_FILE.read_text())
    except Exception:
        return {"subscribers": [], "updated_at": now_iso()}

def save_subscribers(data: dict):
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    SUBSCRIBERS_FILE.write_text(json.dumps(data, indent=2))

def load_feeds() -> list[dict]:
    if not FEEDS_FILE.exists():
        return []
    try:
        data = json.loads(FEEDS_FILE.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []

def save_feeds(feeds: list[dict]):
    FEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDS_FILE.write_text(json.dumps(feeds, indent=2))

def next_issue_id() -> str:
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(ISSUES_DIR.glob("issue_*.json"))
    return f"issue_{len(existing) + 1}"

def save_issue(issue_id: str, issue: dict):
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    (ISSUES_DIR / f"{issue_id}.json").write_text(json.dumps(issue, indent=2))

def load_issue(issue_id: str) -> dict | None:
    path = ISSUES_DIR / f"{issue_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def append_outbox(item: dict):
    OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTBOX_FILE, "a") as f:
        f.write(json.dumps(item) + "\n")


# ── RSS fetching ──────────────────────────────────────────────────────────────

def fetch_rss(url: str, timeout: int = 10) -> list[dict]:
    """Fetch and parse an RSS feed using urllib + regex (no external libs)."""
    items: list[dict] = []
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NewsletterBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[{now_iso()}] RSS fetch error for {url}: {exc}")
        return items

    # Extract <item> or <entry> blocks
    entry_pattern = re.compile(r"<(?:item|entry)>(.*?)</(?:item|entry)>", re.DOTALL)
    tag_pattern   = re.compile(r"<([a-z:]+)[^>]*>([^<]*)</\1>", re.IGNORECASE)

    for match in entry_pattern.finditer(raw):
        block = match.group(1)
        fields: dict[str, str] = {}
        for tag_m in tag_pattern.finditer(block):
            tag  = tag_m.group(1).lower().split(":")[-1]  # strip namespace
            text = re.sub(r"<[^>]+>", "", tag_m.group(2)).strip()
            if tag in ("title", "link", "description", "summary", "pubdate", "published"):
                fields[tag] = text
        if fields.get("title"):
            items.append({
                "title":       fields.get("title", ""),
                "link":        fields.get("link", ""),
                "description": fields.get("description") or fields.get("summary", ""),
                "published":   fields.get("pubdate") or fields.get("published", ""),
            })
        if len(items) >= 10:
            break
    return items


# ── newsletter builder ────────────────────────────────────────────────────────

def build_newsletter_content(topic: str, rss_items: list[dict], preview: bool = False) -> dict:
    """Generate full newsletter content using AI with optional RSS context."""
    rss_context = ""
    if rss_items:
        rss_context = "\n\nRecent news items:\n" + "\n".join(
            f"- {item['title']}: {item['description'][:120]}" for item in rss_items[:5]
        )

    limit = " Keep each section to 1-2 sentences (preview mode)." if preview else ""

    prompt = (
        f"Generate a complete email newsletter issue about: '{topic}'.{limit}\n\n"
        f"Structure with these exact sections:\n"
        f"## Executive Summary\n(2-3 sentence overview)\n\n"
        f"## Top Stories\n(3-5 curated news items with a 2-sentence rewrite each)\n\n"
        f"## Deep Dive\n(1 topic expanded: 150 words of analysis)\n\n"
        f"## Trending Now\n(3 trending topics with 1 sentence each)\n\n"
        f"## Call to Action\n(1 clear CTA relevant to the topic)\n"
        f"{rss_context}"
    )
    content = _ai(prompt, system=f"You are the editor of '{NEWSLETTER_NAME}', a high-quality curated newsletter.")

    sections: dict[str, str] = {}
    section_re = re.compile(r"##\s*(.+?)\n(.*?)(?=\n##\s|\Z)", re.DOTALL)
    for m in section_re.finditer(content):
        key = m.group(1).strip().lower().replace(" ", "_")
        sections[key] = m.group(2).strip()

    return {
        "full_text": content,
        "sections":  sections,
        "topic":     topic,
        "rss_items": len(rss_items),
    }


# ── SMTP / sending ────────────────────────────────────────────────────────────

def send_via_smtp(subject: str, body_text: str, recipients: list[str]) -> tuple[bool, str]:
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM]):
        return False, "SMTP credentials incomplete (SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM required)"
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
        msg["To"]      = ", ".join(recipients[:5])  # batch cap for safety
        msg.attach(MIMEText(body_text, "plain"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, recipients, msg.as_string())
        return True, f"Sent to {len(recipients)} recipients via {SMTP_HOST}"
    except Exception as exc:
        return False, f"SMTP error: {exc}"


# ── command handlers ──────────────────────────────────────────────────────────

def cmd_newsletter_create(topic: str) -> str:
    feeds = load_feeds()
    rss_items: list[dict] = []
    for feed in feeds[:3]:
        items = fetch_rss(feed["url"])
        feed["last_fetched"] = now_iso()
        rss_items.extend(items)
    if feeds:
        save_feeds(feeds)

    issue_id = next_issue_id()
    content_data = build_newsletter_content(topic, rss_items)
    issue = {
        "id":         issue_id,
        "topic":      topic,
        "name":       NEWSLETTER_NAME,
        "content":    content_data["full_text"],
        "sections":   content_data["sections"],
        "rss_items":  content_data["rss_items"],
        "status":     "draft",
        "created_at": now_iso(),
        "sent_at":    None,
    }
    save_issue(issue_id, issue)
    preview = content_data["full_text"][:500]
    return (
        f"[{now_iso()}] Newsletter issue '{issue_id}' created for topic '{topic}'.\n"
        f"RSS items included: {content_data['rss_items']}\n\n"
        f"Preview:\n{preview}...\n\n"
        f"Use 'newsletter send {issue_id}' to send."
    )

def cmd_subscribe(email: str, segment: str = "general") -> str:
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return f"[{now_iso()}] Invalid email address: {email}"
    data = load_subscribers()
    existing = [s for s in data["subscribers"] if s["email"] == email]
    if existing:
        return f"[{now_iso()}] {email} is already subscribed (segment: {existing[0].get('segment','general')})."
    data["subscribers"].append({"email": email, "segment": segment, "subscribed_at": now_iso()})
    save_subscribers(data)
    return f"[{now_iso()}] Subscribed {email} to segment '{segment}'."

def cmd_unsubscribe(email: str) -> str:
    data = load_subscribers()
    before = len(data["subscribers"])
    data["subscribers"] = [s for s in data["subscribers"] if s["email"] != email]
    if len(data["subscribers"]) == before:
        return f"[{now_iso()}] {email} not found in subscriber list."
    save_subscribers(data)
    return f"[{now_iso()}] Unsubscribed {email}."

def cmd_send(issue_id: str) -> str:
    issue = load_issue(issue_id)
    if not issue:
        return f"[{now_iso()}] Issue '{issue_id}' not found."

    data = load_subscribers()
    recipients = [s["email"] for s in data["subscribers"]]
    subject    = f"{NEWSLETTER_NAME}: {issue['topic']}"
    body       = issue["content"]

    if MAILCHIMP_API_KEY:
        # Mailchimp stub — requires list ID and full API implementation
        note = (
            "NOTE: MAILCHIMP_API_KEY is set. To enable Mailchimp sending:\n"
            "  1. Use the Mailchimp Campaigns API: POST /3.0/campaigns\n"
            "  2. Set campaign content: PUT /3.0/campaigns/{id}/content\n"
            "  3. Send: POST /3.0/campaigns/{id}/actions/send\n"
            "  Implement with your Mailchimp list_id and audience settings."
        )
        append_outbox({"issue_id": issue_id, "recipients": len(recipients),
                       "subject": subject, "ts": now_iso(), "channel": "mailchimp_stub"})
        return f"[{now_iso()}] Mailchimp stub triggered for '{issue_id}'.\n{note}"

    if not recipients:
        append_outbox({"issue_id": issue_id, "subject": subject, "ts": now_iso(),
                       "reason": "no subscribers"})
        return f"[{now_iso()}] No subscribers found. Issue saved to outbox."

    ok, msg = send_via_smtp(subject, body, recipients)
    if ok:
        issue["status"] = "sent"
        issue["sent_at"] = now_iso()
        save_issue(issue_id, issue)
        return f"[{now_iso()}] {msg}"
    else:
        append_outbox({"issue_id": issue_id, "subject": subject,
                       "recipients": len(recipients), "ts": now_iso(), "error": msg})
        return (
            f"[{now_iso()}] SMTP unavailable — saved to outbox. Error: {msg}\n"
            f"Set SMTP_HOST, SMTP_USER, SMTP_PASS, SMTP_FROM to enable sending."
        )

def cmd_subscribers() -> str:
    data = load_subscribers()
    subs = data.get("subscribers", [])
    by_seg: dict[str, int] = {}
    for s in subs:
        seg = s.get("segment", "general")
        by_seg[seg] = by_seg.get(seg, 0) + 1
    lines = [f"[{now_iso()}] Subscribers: {len(subs)} total"]
    for seg, count in sorted(by_seg.items(), key=lambda x: -x[1]):
        lines.append(f"  {seg:20s}: {count}")
    return "\n".join(lines)

def cmd_add_rss(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return f"[{now_iso()}] Invalid URL: {url}"
    feeds = load_feeds()
    if any(f["url"] == url for f in feeds):
        return f"[{now_iso()}] Feed already in list: {url}"
    feeds.append({"url": url, "added_at": now_iso(), "last_fetched": None})
    save_feeds(feeds)
    # Quick test fetch
    items = fetch_rss(url)
    return f"[{now_iso()}] Added RSS feed: {url} ({len(items)} items fetched on first pull)"

def cmd_feeds() -> str:
    feeds = load_feeds()
    if not feeds:
        return f"[{now_iso()}] No RSS feeds configured. Use 'newsletter rss <url>' to add one."
    lines = [f"[{now_iso()}] RSS Feeds ({len(feeds)} configured):"]
    for f in feeds:
        last = f.get("last_fetched") or "never"
        lines.append(f"  {f['url'][:60]:<60s} | last: {last}")
    return "\n".join(lines)

def cmd_preview(topic: str) -> str:
    content_data = build_newsletter_content(topic, [], preview=True)
    sections = content_data.get("sections", {})
    lines = [f"[{now_iso()}] Newsletter Preview — '{topic}'\n"]
    section_order = ["executive_summary", "top_stories", "deep_dive", "trending_now", "call_to_action"]
    for key in section_order:
        text = sections.get(key, "")
        heading = key.replace("_", " ").title()
        lines.append(f"  ## {heading}")
        lines.append(f"  {text[:300]}{'...' if len(text) > 300 else ''}\n")
    return "\n".join(lines)

def cmd_newsletter_status() -> str:
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    issues = list(ISSUES_DIR.glob("issue_*.json"))
    sent_issues = []
    for path in issues:
        try:
            issue = json.loads(path.read_text())
            if issue.get("sent_at"):
                sent_issues.append(issue)
        except Exception:
            pass
    data = load_subscribers()
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    lines = [
        f"[{now_iso()}] Newsletter Bot Status",
        f"  Newsletter name : {NEWSLETTER_NAME}",
        f"  Frequency       : {NEWSLETTER_FREQ}",
        f"  Issues created  : {len(issues)}",
        f"  Issues sent     : {len(sent_issues)}",
        f"  Subscribers     : {len(data.get('subscribers', []))}",
        f"  RSS feeds       : {len(load_feeds())}",
        f"  SMTP configured : {'yes' if SMTP_HOST else 'no'}",
        f"  Mailchimp key   : {'set' if MAILCHIMP_API_KEY else 'not set'}",
        f"  Last heartbeat  : {state.get('ts', 'n/a')}",
    ]
    if sent_issues:
        last = max(sent_issues, key=lambda x: x.get("sent_at", ""))
        lines.append(f"  Last send       : {last.get('sent_at')} ({last.get('topic','')})")
    return "\n".join(lines)


# ── chatlog processor ─────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        response: str | None = None

        if msg_lower.startswith("newsletter create "):
            topic = msg[len("newsletter create "):].strip()
            response = cmd_newsletter_create(topic) if topic else "Usage: newsletter create <topic>"
        elif msg_lower.startswith("newsletter subscribe "):
            parts = msg.split()[2:]  # email [segment]
            if parts:
                response = cmd_subscribe(parts[0], parts[1] if len(parts) > 1 else "general")
            else:
                response = "Usage: newsletter subscribe <email> [segment]"
        elif msg_lower.startswith("newsletter unsubscribe "):
            email = msg.split()[-1]
            response = cmd_unsubscribe(email)
        elif msg_lower.startswith("newsletter send "):
            issue_id = msg.split()[-1]
            response = cmd_send(issue_id)
        elif msg_lower == "newsletter subscribers":
            response = cmd_subscribers()
        elif msg_lower.startswith("newsletter rss "):
            url = msg[len("newsletter rss "):].strip()
            response = cmd_add_rss(url) if url else "Usage: newsletter rss <url>"
        elif msg_lower == "newsletter feeds":
            response = cmd_feeds()
        elif msg_lower.startswith("newsletter preview "):
            topic = msg[len("newsletter preview "):].strip()
            response = cmd_preview(topic) if topic else "Usage: newsletter preview <topic>"
        elif msg_lower == "newsletter status":
            response = cmd_newsletter_status()

        if response:
            print(response)
            append_chatlog({"type": "bot", "bot": "newsletter-bot", "message": response, "ts": now_iso()})

    return new_idx


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[{now_iso()}] newsletter-bot started; poll={POLL_INTERVAL}s")
    last_idx = len(load_chatlog())
    write_state({"bot": "newsletter-bot", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] newsletter-bot error: {exc}")
        write_state({"bot": "newsletter-bot", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
