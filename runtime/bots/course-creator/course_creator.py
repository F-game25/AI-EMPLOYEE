"""Course Creator Bot — online course creation and marketing automation.

Given any topic, generates a complete course package: a full module/lesson
outline, rich lesson content (~1,000 words each), module quiz questions,
Teachable/Gumroad setup instructions, a 5-email launch sequence, pricing
strategy with upsell tiers, and a sales-page copy block — everything needed
to publish and sell an evergreen online course from scratch.

Commands:
  course create <topic>               — full package: outline + intro lesson + quiz + pricing + marketing copy
  course outline <topic>              — course structure only (modules + lessons list)
  course lesson <module> <lesson>     — full lesson content (~1000 words, objectives, examples, exercises)
  course quiz <module>                — 10 quiz questions with answers for a module
  course market <topic>               — sales page copy + 5-email launch sequence + social proof templates + FAQ
  course price <topic>                — pricing tiers (free/basic/premium/VIP) + upsell structure
  course status                       — courses created, lessons generated, revenue potential
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "course-creator.state.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
POLL_INTERVAL = int(os.environ.get("COURSE_CREATOR_POLL_INTERVAL", "5"))
DEFAULT_PLATFORM = os.environ.get("COURSE_DEFAULT_PLATFORM", "teachable")
PRICE_RANGE = os.environ.get("COURSE_PRICE_RANGE", "97-497")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))
try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False

COURSES_DIR = AI_HOME / "state" / "courses"


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


def _ai(prompt, system=""):
    if not _AI_AVAILABLE:
        return "[AI unavailable]"
    return (_query_ai_for_agent("course-creator", prompt, system_prompt=system) or {}).get("answer", "")


def _safe_topic(topic: str) -> str:
    return re.sub(r"[^\w-]", "_", topic.strip().lower())[:60]


def _course_path(topic: str) -> Path:
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    return COURSES_DIR / f"{_safe_topic(topic)}_course.json"


def _load_course(topic: str) -> dict:
    path = _course_path(topic)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"topic": topic, "created_at": now_iso(), "modules": [], "lessons": [], "quizzes": []}


def _save_course(topic: str, data: dict):
    path = _course_path(topic)
    data["updated_at"] = now_iso()
    path.write_text(json.dumps(data, indent=2))
    return path


def _list_courses() -> list:
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    courses = []
    for p in COURSES_DIR.glob("*_course.json"):
        try:
            d = json.loads(p.read_text())
            courses.append(d)
        except Exception:
            pass
    return courses


# ── generation helpers ────────────────────────────────────────────────────────

def _gen_outline(topic: str) -> dict:
    system = (
        "You are an expert instructional designer with experience creating 6-figure online courses "
        f"on {DEFAULT_PLATFORM}. You structure courses for maximum completion and student transformation."
    )
    prompt = (
        f"Create a comprehensive online course outline for: '{topic}'\n"
        "Requirements:\n"
        "- 5-8 modules\n"
        "- Each module: 3-5 lessons\n"
        "- Each lesson: title + one-sentence learning objective\n"
        "Return as JSON:\n"
        "{\n"
        "  \"course_title\": \"...\",\n"
        "  \"tagline\": \"...\",\n"
        "  \"target_audience\": \"...\",\n"
        "  \"transformation\": \"...\",\n"
        "  \"modules\": [\n"
        "    {\"module\": 1, \"title\": \"...\", \"goal\": \"...\",\n"
        "     \"lessons\": [{\"lesson\": 1, \"title\": \"...\", \"objective\": \"...\"}]}\n"
        "  ]\n"
        "}\n"
        "Return ONLY valid JSON."
    )
    raw = _ai(prompt, system)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        return json.loads(m.group()) if m else {"course_title": topic, "modules": []}
    except Exception:
        return {"course_title": topic, "modules": []}


def _gen_lesson(module: str, lesson_title: str) -> str:
    system = (
        "You are an expert online course instructor. Write engaging, actionable lessons "
        "that deliver real transformation to students."
    )
    prompt = (
        f"Write a complete online course lesson.\n"
        f"Module: {module}\n"
        f"Lesson title: {lesson_title}\n\n"
        "Structure (~1000 words):\n"
        "## Learning Objectives (3 bullet points)\n"
        "## Introduction (hook + why this matters)\n"
        "## Core Content (3-4 sections with explanations and examples)\n"
        "## Real-World Example (detailed case study or story)\n"
        "## Exercise (actionable student task)\n"
        "## Key Takeaways (3-5 bullet points)\n"
        "## Next Steps (bridge to next lesson)\n"
        "Write in a warm, direct teaching voice."
    )
    return _ai(prompt, system)


def _gen_quiz(module: str) -> str:
    system = "You are an instructional designer creating assessments that reinforce learning."
    prompt = (
        f"Create 10 quiz questions for the course module: '{module}'\n"
        "Mix of question types: multiple choice (A/B/C/D), true/false, and short-answer.\n"
        "For each question provide:\n"
        "Q[N]. [question text]\n"
        "A) ... B) ... C) ... D) ...\n"
        "ANSWER: [correct answer + brief explanation]\n\n"
        "Questions should test comprehension, application, and critical thinking."
    )
    return _ai(prompt, system)


def _gen_marketing(topic: str) -> str:
    system = "You are a direct-response copywriter specialising in online course launches."
    prompt = (
        f"Generate a complete marketing pack for an online course about: '{topic}'\n\n"
        "Include:\n"
        "## SALES PAGE COPY\n"
        "- Hero headline + sub-headline\n"
        "- Problem section (3 pain points)\n"
        "- Solution intro\n"
        "- What you'll learn (5 bullet outcomes)\n"
        "- Who it's for\n"
        "- Instructor bio template\n"
        "- Money-back guarantee block\n\n"
        "## 5-EMAIL LAUNCH SEQUENCE\n"
        "Email 1 (Day 0): Story + problem\n"
        "Email 2 (Day 2): Teaching email (value)\n"
        "Email 3 (Day 4): Case study / social proof\n"
        "Email 4 (Day 6): Objections + FAQ\n"
        "Email 5 (Day 7): Last chance + scarcity\n\n"
        "## SOCIAL PROOF TEMPLATES\n"
        "3 student testimonial request scripts\n\n"
        "## FAQ\n"
        "8 common objections with responses"
    )
    return _ai(prompt, system)


def _gen_pricing(topic: str) -> str:
    system = "You are a course pricing strategist who maximises revenue with tiered offers."
    prompt = (
        f"Create a complete pricing strategy for an online course about: '{topic}'\n"
        f"Target price range: ${PRICE_RANGE}\n\n"
        "Include:\n"
        "## TIER STRUCTURE\n"
        "1. FREE PREVIEW: What to include (1-2 lessons), purpose\n"
        f"2. BASIC ($97-$147): Features list\n"
        f"3. PREMIUM ($197-$297): Features + bonuses\n"
        f"4. VIP ($497+): Features + 1:1 element + community\n\n"
        "## UPSELL FLOW\n"
        "- Order bump (low-ticket add-on)\n"
        "- Upsell 1 (post-purchase)\n"
        "- Downsell (if declined)\n\n"
        "## LAUNCH PRICING\n"
        "- Early bird strategy\n"
        "- Bonuses to add/remove for urgency\n\n"
        "## REVENUE PROJECTIONS\n"
        "Estimate for 100 / 500 / 1000 students at each tier"
    )
    return _ai(prompt, system)


def _gen_intro_lesson(topic: str) -> str:
    system = "You write compelling course welcome lessons that reduce refund rates."
    prompt = (
        f"Write a welcome/intro lesson for an online course about: '{topic}'\n\n"
        "Include:\n"
        "- Personal welcome message\n"
        "- What students will achieve by end of course\n"
        "- How to get the most from this course\n"
        "- Quick win exercise to complete before Module 1\n"
        "- Community/support information\n"
        "Length: ~400 words. Warm and motivating tone."
    )
    return _ai(prompt, system)


def _bot_reply(message: str):
    append_chatlog({"type": "bot", "bot": "course-creator", "message": message, "ts": now_iso()})
    print(f"[{now_iso()}] course-creator reply: {message[:120]}")


# ── command processing ────────────────────────────────────────────────────────

def process_chatlog(last_idx: int) -> int:
    chatlog = load_chatlog()
    new_entries = chatlog[last_idx:]
    new_idx = len(chatlog)

    for entry in new_entries:
        if entry.get("type") != "user":
            continue
        msg = entry.get("message", "").strip()
        msg_lower = msg.lower()

        if not msg_lower.startswith("course"):
            continue

        # course status
        if msg_lower in ("course status", "course stats"):
            courses = _list_courses()
            total_lessons = sum(len(c.get("lessons", [])) for c in courses)
            tip = (
                "Evergreen course + email funnel = passive income. "
                "Target: 'AI for beginners' at $197 = 100 sales = $19,700. "
                "Scale with affiliates."
            )
            reply = (
                f"🎓 Course Creator Bot Status\n"
                f"  Courses created    : {len(courses)}\n"
                f"  Lessons generated  : {total_lessons}\n"
                f"  Default platform   : {DEFAULT_PLATFORM}\n"
                f"  Price range        : ${PRICE_RANGE}\n"
                f"  Courses dir        : {COURSES_DIR}\n"
                f"  💰 Revenue tip: {tip}"
            )
            _bot_reply(reply)
            continue

        # course outline <topic>
        if msg_lower.startswith("course outline "):
            topic = msg[len("course outline "):].strip()
            if not topic:
                _bot_reply("Usage: course outline <topic>")
                continue
            outline = _gen_outline(topic)
            course = _load_course(topic)
            course["outline"] = outline
            course["modules"] = outline.get("modules", [])
            _save_course(topic, course)
            modules = outline.get("modules", [])
            lines = [f"📚 Course Outline — {outline.get('course_title', topic)}",
                     f"  Tagline: {outline.get('tagline', '')}",
                     f"  Audience: {outline.get('target_audience', '')}",
                     ""]
            for mod in modules:
                lines.append(f"Module {mod.get('module')}: {mod.get('title')}")
                for les in mod.get("lessons", []):
                    lines.append(f"  {les.get('lesson')}. {les.get('title')}")
            _bot_reply("\n".join(lines))
            continue

        # course lesson <module> <lesson_title>
        if msg_lower.startswith("course lesson "):
            rest = msg[len("course lesson "):].strip()
            parts = rest.split(" ", 1)
            if len(parts) < 2:
                _bot_reply("Usage: course lesson <module name/number> <lesson title>")
                continue
            module, lesson_title = parts[0], parts[1]
            _bot_reply(f"✍️ Generating lesson: '{lesson_title}' (Module {module})…")
            content = _gen_lesson(module, lesson_title)
            # store in the first found course or a generic store
            all_courses = _list_courses()
            if all_courses:
                course = all_courses[0]
                course.setdefault("lessons", []).append({
                    "module": module, "title": lesson_title,
                    "content": content, "generated_at": now_iso()
                })
                _save_course(course["topic"], course)
            _bot_reply(f"📖 Lesson: {lesson_title}\n\n{content}")
            continue

        # course quiz <module>
        if msg_lower.startswith("course quiz "):
            module = msg[len("course quiz "):].strip()
            if not module:
                _bot_reply("Usage: course quiz <module name or number>")
                continue
            quiz = _gen_quiz(module)
            _bot_reply(f"📝 Quiz — Module: {module}\n\n{quiz}")
            continue

        # course market <topic>
        if msg_lower.startswith("course market "):
            topic = msg[len("course market "):].strip()
            if not topic:
                _bot_reply("Usage: course market <topic>")
                continue
            _bot_reply(f"📣 Generating marketing pack for '{topic}'…")
            marketing = _gen_marketing(topic)
            course = _load_course(topic)
            course["marketing"] = marketing
            _save_course(topic, course)
            _bot_reply(f"🚀 Marketing Pack — {topic}:\n\n{marketing}")
            continue

        # course price <topic>
        if msg_lower.startswith("course price "):
            topic = msg[len("course price "):].strip()
            if not topic:
                _bot_reply("Usage: course price <topic>")
                continue
            pricing = _gen_pricing(topic)
            course = _load_course(topic)
            course["pricing"] = pricing
            _save_course(topic, course)
            _bot_reply(f"💰 Pricing Strategy — {topic}:\n\n{pricing}")
            continue

        # course create <topic>  — full package
        if msg_lower.startswith("course create "):
            topic = msg[len("course create "):].strip()
            if not topic:
                _bot_reply("Usage: course create <topic>")
                continue
            _bot_reply(f"⚙️ Building full course package for: '{topic}' — this may take a moment…")
            try:
                outline = _gen_outline(topic)
                intro = _gen_intro_lesson(topic)
                # quiz from first module
                first_mod = (outline.get("modules") or [{}])[0].get("title", "Module 1")
                quiz = _gen_quiz(first_mod)
                pricing = _gen_pricing(topic)
                marketing = _gen_marketing(topic)
                course = {
                    "topic": topic,
                    "created_at": now_iso(),
                    "outline": outline,
                    "modules": outline.get("modules", []),
                    "intro_lesson": intro,
                    "sample_quiz": quiz,
                    "pricing": pricing,
                    "marketing": marketing,
                    "lessons": [],
                    "quizzes": [],
                }
                path = _save_course(topic, course)
                mod_count = len(outline.get("modules", []))
                lesson_count = sum(len(m.get("lessons", [])) for m in outline.get("modules", []))
                reply = (
                    f"✅ Course Package Ready — {outline.get('course_title', topic)}\n"
                    f"  Tagline   : {outline.get('tagline', '')}\n"
                    f"  Audience  : {outline.get('target_audience', '')}\n"
                    f"  Modules   : {mod_count}\n"
                    f"  Lessons   : {lesson_count}\n"
                    f"  Platform  : {DEFAULT_PLATFORM}\n"
                    f"  💾 Saved  : {path}"
                )
            except Exception as exc:
                reply = f"❌ Course creation error: {exc}"
            _bot_reply(reply)
            continue

    return new_idx


def main():
    print(f"[{now_iso()}] course-creator started")
    last_idx = len(load_chatlog())
    write_state({"bot": "course-creator", "ts": now_iso(), "status": "starting"})
    while True:
        try:
            new_idx = process_chatlog(last_idx)
            last_idx = new_idx
        except Exception as exc:
            print(f"[{now_iso()}] course-creator error: {exc}")
        write_state({"bot": "course-creator", "ts": now_iso(), "status": "running"})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
