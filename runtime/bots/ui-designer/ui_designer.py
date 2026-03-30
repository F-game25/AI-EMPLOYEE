"""UI Designer Bot — UI/UX design guidance, design systems, and interface critique.

Provides comprehensive UI/UX design capabilities:
  - Design system creation (tokens, components, patterns)
  - Interface design critique and improvement suggestions
  - Component specifications (sizes, states, variants, accessibility)
  - Color palette and typography selection
  - Responsive layout guidance
  - Design handoff specifications for developers
  - Accessibility audit (WCAG 2.1 AA)
  - Dark mode and theming strategy
  - User flow and information architecture
  - Micro-interaction and animation guidance

Commands (via chatlog / WhatsApp / Dashboard):
  design system <product>          — create a design system foundation
  design component <component>     — spec a UI component with all states/variants
  design audit <description>       — critique a UI for usability and consistency
  design colors <brand>            — generate accessible color palette
  design typography <context>      — typography system recommendation
  design layout <page/screen>      — layout and information architecture
  design accessibility <feature>   — WCAG accessibility audit and fixes
  design darkmode <product>        — dark mode strategy and token mapping
  design flows <user-goal>         — user flow design
  design handoff <component>       — developer handoff specifications
  design status                    — current design projects

State files:
  ~/.ai-employee/state/ui-designer.state.json
  ~/.ai-employee/state/design-projects.json
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
STATE_FILE = AI_HOME / "state" / "ui-designer.state.json"
PROJECTS_FILE = AI_HOME / "state" / "design-projects.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("UI_DESIGNER_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("ui-designer")

_ai_router_path = AI_HOME / "bots" / "ai-router"
if str(_ai_router_path) not in sys.path:
    sys.path.insert(0, str(_ai_router_path))

try:
    from ai_router import query_ai_for_agent as _query_ai_for_agent  # type: ignore
    _AI_AVAILABLE = True
except ImportError:
    _AI_AVAILABLE = False


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_projects() -> list:
    if not PROJECTS_FILE.exists():
        return []
    try:
        return json.loads(PROJECTS_FILE.read_text())
    except Exception:
        return []


def save_projects(projects: list) -> None:
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2))


def load_chatlog() -> list:
    if not CHATLOG.exists():
        return []
    entries = []
    try:
        for line in CHATLOG.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    except Exception:
        pass
    return entries


def append_chatlog(entry: dict) -> None:
    CHATLOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CHATLOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def ai_query(prompt: str, system_prompt: str = "") -> str:
    if not _AI_AVAILABLE:
        return "AI router not available."
    try:
        result = _query_ai_for_agent("ui-designer", prompt, system_prompt=system_prompt)
        return result.get("answer", "No response generated.")
    except Exception as exc:
        return f"AI query failed: {exc}"


def write_orchestrator_result(subtask_id: str, result_text: str, status: str = "done") -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULTS_DIR / f"{subtask_id}.json"
    result_file.write_text(json.dumps({
        "subtask_id": subtask_id,
        "status": status,
        "result": result_text,
        "completed_at": now_iso(),
    }))


SYSTEM_DESIGNER = (
    "You are an expert UI/UX designer who creates beautiful, consistent, and accessible interfaces. "
    "You specialize in design systems, component libraries, and pixel-perfect interface creation. "
    "You always follow WCAG 2.1 AA accessibility standards, consider mobile-first responsive design, "
    "and build for consistency across the entire product. "
    "You provide specific CSS variables (design tokens), component specifications with all states, "
    "and developer-ready handoff documentation. "
    "You think in design systems first — reusable patterns over one-off solutions."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_system(product: str) -> str:
    return ai_query(
        f"Create a design system foundation for: {product}\n\n"
        "## Design Tokens (CSS Variables)\n"
        "Provide complete CSS custom properties for:\n"
        "- Color palette (primary, secondary, neutral, semantic: success/warning/error/info)\n"
        "- Typography (font families, sizes xs through 4xl, weights, line heights)\n"
        "- Spacing scale (4px base grid)\n"
        "- Border radius scale\n"
        "- Shadow scale\n"
        "- Transition/animation timings\n\n"
        "## Component Inventory\n"
        "List the 20 core components this product needs with priority order\n\n"
        "## Design Principles\n"
        "3-5 product-specific design principles that guide decisions\n\n"
        "## Figma/Sketch Structure\n"
        "How to organize the design file (pages, frames, component naming)",
        SYSTEM_DESIGNER,
    )


def cmd_component(component: str) -> str:
    return ai_query(
        f"Create full specification for UI component: {component}\n\n"
        "## Component Anatomy\n"
        "All parts/slots this component has with descriptions\n\n"
        "## Variants\n"
        "All visual variants (e.g., primary/secondary/destructive for a button)\n\n"
        "## Sizes\n"
        "All size options with exact pixel dimensions\n\n"
        "## States\n"
        "Default, hover, active, focus, disabled, loading, error — with visual description\n\n"
        "## Accessibility\n"
        "- ARIA role and required attributes\n"
        "- Keyboard interaction pattern\n"
        "- Screen reader announcement\n"
        "- Color contrast requirements\n\n"
        "## CSS Implementation\n"
        "Complete CSS using design tokens for the default variant\n\n"
        "## Usage Guidelines\n"
        "When to use, when not to use, and common mistakes",
        SYSTEM_DESIGNER,
    )


def cmd_audit(description: str) -> str:
    return ai_query(
        f"UI/UX critique and improvement for: {description}\n\n"
        "## Usability Issues\n"
        "Ranked by severity (Critical/High/Medium/Low):\n"
        "For each: describe the problem, user impact, and specific fix\n\n"
        "## Visual Consistency Issues\n"
        "Inconsistencies in spacing, color, typography, or components\n\n"
        "## Accessibility Issues\n"
        "WCAG 2.1 failures with remediation\n\n"
        "## Mobile/Responsive Issues\n"
        "Problems on smaller screens and fixes\n\n"
        "## Top 5 Priority Improvements\n"
        "Ranked by impact on user experience",
        SYSTEM_DESIGNER,
    )


def cmd_colors(brand: str) -> str:
    return ai_query(
        f"Generate an accessible color system for brand: {brand}\n\n"
        "## Primary Palette\n"
        "10-step scale (50 through 900) with hex values for the primary brand color\n\n"
        "## Neutral/Gray Palette\n"
        "10-step neutral scale for backgrounds, borders, text\n\n"
        "## Semantic Colors\n"
        "Success, warning, error, info colors with light variants for backgrounds\n\n"
        "## Accessibility Check\n"
        "Contrast ratios for all text-on-background combinations (WCAG AA: 4.5:1, AAA: 7:1)\n\n"
        "## Dark Mode Mapping\n"
        "How each light mode color maps to dark mode equivalent\n\n"
        "## CSS Variables\n"
        "Complete :root{} and [data-theme='dark']{} blocks",
        SYSTEM_DESIGNER,
    )


def cmd_typography(context: str) -> str:
    return ai_query(
        f"Typography system recommendation for: {context}\n\n"
        "## Font Selection\n"
        "- Primary font (body/UI) with rationale\n"
        "- Display/heading font (if different) with rationale\n"
        "- Monospace font for code (if needed)\n"
        "- Google Fonts or system font stack alternative\n\n"
        "## Type Scale\n"
        "| Token | Size | Line Height | Weight | Use Case |\n"
        "For: display, h1-h4, body-lg, body, body-sm, caption, label, code\n\n"
        "## Responsive Typography\n"
        "How sizes adjust from mobile to desktop (clamp() or breakpoints)\n\n"
        "## CSS Variables\n"
        "Complete font token definitions\n\n"
        "## Accessibility\n"
        "Minimum sizes, line length guidelines, contrast requirements",
        SYSTEM_DESIGNER,
    )


def cmd_layout(page: str) -> str:
    return ai_query(
        f"Layout and information architecture for: {page}\n\n"
        "## Content Hierarchy\n"
        "What's most important → least important on this screen\n\n"
        "## Layout Structure\n"
        "Grid system, column count, key zones (header, nav, content, sidebar, footer)\n\n"
        "## Responsive Behavior\n"
        "How layout adapts from mobile (320px) → tablet (768px) → desktop (1280px)\n\n"
        "## Navigation Pattern\n"
        "Recommended navigation approach and rationale\n\n"
        "## CSS Grid/Flexbox\n"
        "Implementation code for the layout\n\n"
        "## Spacing\n"
        "Recommended margins and padding using the 4px spacing scale",
        SYSTEM_DESIGNER,
    )


def cmd_accessibility(feature: str) -> str:
    return ai_query(
        f"Accessibility audit and fixes for: {feature}\n\n"
        "## WCAG 2.1 Compliance Check\n"
        "Test against criteria: 1.1.1, 1.3.1, 1.4.1-1.4.13, 2.1.1, 2.4.3, 2.4.7, 4.1.1, 4.1.2\n\n"
        "## Issues Found\n"
        "For each issue: WCAG criterion violated, current behavior, required fix with code\n\n"
        "## Color Contrast\n"
        "Check all text/background combinations against 4.5:1 AA standard\n\n"
        "## Keyboard Navigation\n"
        "Tab order, focus indicators, keyboard shortcuts needed\n\n"
        "## Screen Reader Support\n"
        "ARIA labels, live regions, announcements needed\n\n"
        "## Implementation Checklist\n"
        "Ordered list of fixes with HTML/CSS/JS code examples",
        SYSTEM_DESIGNER,
    )


def cmd_darkmode(product: str) -> str:
    return ai_query(
        f"Dark mode strategy and token mapping for: {product}\n\n"
        "## Implementation Strategy\n"
        "CSS custom properties approach vs. class-based vs. prefers-color-scheme\n\n"
        "## Token Mapping\n"
        "| Light Mode Token | Value | Dark Mode Value | Rationale |\n"
        "Map all semantic color tokens to their dark equivalents\n\n"
        "## Surface Elevation\n"
        "How to handle elevation/depth in dark mode (avoiding pure black)\n\n"
        "## Image and Icon Handling\n"
        "Strategy for images and icons that need dark variants\n\n"
        "## CSS Implementation\n"
        "Complete :root{} and [data-theme='dark']{} or @media (prefers-color-scheme: dark){}\n\n"
        "## User Preference Persistence\n"
        "JavaScript to save and apply user preference",
        SYSTEM_DESIGNER,
    )


def cmd_flows(user_goal: str) -> str:
    return ai_query(
        f"User flow design for goal: {user_goal}\n\n"
        "## User Journey Map\n"
        "Step-by-step flow from entry point to goal completion\n\n"
        "## Screen Inventory\n"
        "List all screens/states needed with purpose of each\n\n"
        "## Happy Path\n"
        "Optimal path with screen transitions\n\n"
        "## Error States\n"
        "How each step handles errors (validation, network, auth)\n\n"
        "## Empty States\n"
        "What users see when there's no data yet\n\n"
        "## Loading States\n"
        "Skeleton screens, spinners, and progress indicators needed\n\n"
        "## Edge Cases\n"
        "5 edge cases to design for",
        SYSTEM_DESIGNER,
    )


def cmd_handoff(component: str) -> str:
    return ai_query(
        f"Developer handoff specification for: {component}\n\n"
        "## Dimensions and Spacing\n"
        "Exact pixel measurements for all spacing, sizes, and positioning\n\n"
        "## Colors\n"
        "Exact hex/token values for all colors in all states\n\n"
        "## Typography\n"
        "Font, size, weight, line-height, letter-spacing for all text elements\n\n"
        "## Interactions\n"
        "Hover, focus, active, transition durations and easing\n\n"
        "## Assets\n"
        "Icons needed (with names), images (with sizes/formats), and export settings\n\n"
        "## HTML Structure\n"
        "Semantic HTML markup with ARIA attributes\n\n"
        "## CSS Implementation\n"
        "Complete CSS using design tokens\n\n"
        "## QA Checklist\n"
        "10-item checklist to verify implementation matches design",
        SYSTEM_DESIGNER,
    )


def cmd_status() -> str:
    projects = load_projects()
    if not projects:
        return "No design projects recorded yet."
    lines = ["## Design Projects\n"]
    for p in projects[:10]:
        lines.append(f"- [{p.get('type', 'design')}] {p.get('description', '')[:80]} — {p.get('created_at', '')[:10]}")
    return "\n".join(lines)


# ── Message Routing ────────────────────────────────────────────────────────────

COMMANDS = {
    "design system": (cmd_system, 1),
    "design component": (cmd_component, 1),
    "design audit": (cmd_audit, 1),
    "design colors": (cmd_colors, 1),
    "design typography": (cmd_typography, 1),
    "design layout": (cmd_layout, 1),
    "design accessibility": (cmd_accessibility, 1),
    "design darkmode": (cmd_darkmode, 1),
    "design flows": (cmd_flows, 1),
    "design handoff": (cmd_handoff, 1),
    "design status": (lambda: cmd_status(), 0),
}


def process_message(text: str) -> str | None:
    text_lower = text.strip().lower()
    for prefix, (handler, needs_arg) in COMMANDS.items():
        if text_lower.startswith(prefix):
            arg = text[len(prefix):].strip() if needs_arg else ""
            projects = load_projects()
            projects.insert(0, {
                "id": str(uuid.uuid4())[:8],
                "type": prefix.replace("design ", ""),
                "description": arg[:200],
                "created_at": now_iso(),
            })
            save_projects(projects[:50])
            if needs_arg:
                return handler(arg)
            return handler()
    return None


def process_queue() -> None:
    queue_file = AGENT_TASKS_DIR / "ui-designer.queue.jsonl"
    if not queue_file.exists():
        return
    lines = queue_file.read_text().splitlines()
    remaining = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            task = json.loads(line)
        except Exception:
            continue
        if task.get("status") == "pending":
            result = process_message(task.get("input", ""))
            if result:
                write_orchestrator_result(task["subtask_id"], result)
                task["status"] = "done"
            else:
                task["status"] = "unhandled"
                write_orchestrator_result(
                    task["subtask_id"],
                    f"UI Designer could not process: {task.get('input', '')}",
                    status="unhandled",
                )
        remaining.append(json.dumps(task))
    queue_file.write_text("\n".join(remaining) + "\n" if remaining else "")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    state = {
        "agent": "ui-designer",
        "started_at": now_iso(),
        "status": "running",
        "last_poll": now_iso(),
    }
    write_state(state)
    logger.info("UI Designer started.")
    processed: set = set()

    while True:
        try:
            process_queue()
            entries = load_chatlog()
            for entry in entries:
                eid = entry.get("id") or entry.get("ts") or str(entry)
                if eid in processed:
                    continue
                role = entry.get("role", "")
                text = entry.get("text", "") or entry.get("content", "")
                if role == "user" and text.strip().lower().startswith("design "):
                    result = process_message(text)
                    if result:
                        append_chatlog({
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "agent": "ui-designer",
                            "text": result,
                            "ts": now_iso(),
                        })
                processed.add(eid)

            state["last_poll"] = now_iso()
            write_state(state)
        except Exception as exc:
            logger.error("UI Designer error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
