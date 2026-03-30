"""Engineering Assistant Bot — Frontend, backend, AI engineering, and code review.

Provides comprehensive software engineering help:
  - Frontend development (React, Vue, TypeScript, CSS, performance)
  - Backend architecture (APIs, databases, microservices, cloud)
  - AI/ML engineering (models, pipelines, LLM integration, MLOps)
  - Code review (security, performance, maintainability)
  - DevOps (CI/CD, Docker, Kubernetes, infrastructure)
  - Database design (schema, indexing, query optimization)
  - API design (REST, GraphQL, gRPC, WebSockets)
  - Security review (OWASP, threat modeling, secure coding)

Commands (via chatlog / WhatsApp / Dashboard):
  eng frontend <task>              — frontend dev help (React, Vue, CSS, performance)
  eng backend <task>               — backend architecture and API design
  eng aiml <task>                  — AI/ML engineering and LLM integration
  eng review <code/task>           — code review for security and quality
  eng devops <task>                — CI/CD, Docker, K8s, infrastructure
  eng database <task>              — schema design and query optimization
  eng security <task>              — security review and threat modeling
  eng architecture <system>        — system architecture design
  eng refactor <description>       — refactoring guidance
  eng debug <problem>              — debugging and troubleshooting help
  eng status                       — current engineering tasks

State files:
  ~/.ai-employee/state/engineering-assistant.state.json
  ~/.ai-employee/state/eng-tasks.json
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
STATE_FILE = AI_HOME / "state" / "engineering-assistant.state.json"
TASKS_FILE = AI_HOME / "state" / "eng-tasks.json"
CHATLOG = AI_HOME / "state" / "chatlog.jsonl"
AGENT_TASKS_DIR = AI_HOME / "state" / "agent_tasks"
RESULTS_DIR = AI_HOME / "state" / "orchestrator_results"

POLL_INTERVAL = int(os.environ.get("ENG_POLL_INTERVAL", "5"))

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING),
    format="%(message)s",
)
logger = logging.getLogger("engineering-assistant")

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


def load_tasks() -> list:
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text())
    except Exception:
        return []


def save_tasks(tasks: list) -> None:
    TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


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
        result = _query_ai_for_agent("engineering-assistant", prompt, system_prompt=system_prompt)
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


SYSTEM_FRONTEND = (
    "You are an expert frontend developer specializing in modern web technologies. "
    "You build responsive, accessible, and performant web applications with pixel-perfect precision. "
    "Your stack: React, Vue 3, TypeScript, Tailwind CSS, Next.js. "
    "You always consider Core Web Vitals (LCP, FID, CLS), accessibility (WCAG 2.1 AA), "
    "and bundle optimization. Provide specific, runnable code examples with best practices. "
    "Point out performance pitfalls and accessibility issues proactively."
)

SYSTEM_BACKEND = (
    "You are a senior backend architect who builds robust, scalable server-side systems. "
    "You specialize in API design (REST, GraphQL, gRPC), database architecture, "
    "microservices, and cloud infrastructure (AWS, GCP, Azure). "
    "You always design for security (OWASP Top 10), scalability (horizontal scaling), "
    "and observability (logging, tracing, metrics). "
    "Provide architecture diagrams, SQL schemas, and working code examples. "
    "Be specific about trade-offs and when to use each pattern."
)

SYSTEM_AIML = (
    "You are an expert AI/ML engineer specializing in production machine learning systems. "
    "You build data pipelines, train and deploy models, and integrate LLMs into applications. "
    "Your stack: Python, PyTorch, Hugging Face, LangChain, LlamaIndex, OpenAI, Anthropic, Ollama, "
    "MLflow, FastAPI, vector databases (Chroma, Pinecone, Qdrant). "
    "You always consider model bias, interpretability, data privacy, and production monitoring. "
    "Provide working code examples with MLOps best practices."
)

SYSTEM_REVIEW = (
    "You are a senior software engineer conducting thorough code reviews. "
    "You focus on: security vulnerabilities (OWASP Top 10, injection, auth flaws), "
    "performance bottlenecks (N+1 queries, inefficient algorithms, memory leaks), "
    "maintainability (complexity, naming, documentation, testability), "
    "and correctness (edge cases, error handling, race conditions). "
    "Provide specific, actionable feedback with code examples for each issue. "
    "Rate severity: Critical (security/data loss), High (bugs/performance), Medium (maintainability), Low (style)."
)

SYSTEM_DEVOPS = (
    "You are a DevOps and platform engineering expert. "
    "You design CI/CD pipelines, container orchestration (Docker, Kubernetes), "
    "infrastructure as code (Terraform, Pulumi), and cloud architecture (AWS, GCP, Azure). "
    "You optimize for reliability (SRE principles, SLOs), security (least privilege, secrets management), "
    "and developer productivity (fast pipelines, easy deployments). "
    "Provide working configs (Dockerfile, K8s manifests, GitHub Actions, Terraform) with explanations."
)

SYSTEM_DATABASE = (
    "You are a database architect and optimization specialist. "
    "You design schemas for PostgreSQL, MySQL, MongoDB, Redis, and ClickHouse. "
    "You optimize queries, design indexes, plan migrations, and architect for scale. "
    "You understand ACID properties, CAP theorem, and when to choose SQL vs NoSQL. "
    "Always provide: CREATE TABLE with indexes, example queries, EXPLAIN ANALYZE output interpretation, "
    "and migration strategies. Point out common schema anti-patterns proactively."
)

SYSTEM_SECURITY = (
    "You are an application security engineer with adversarial thinking. "
    "You conduct threat modeling, secure code reviews, and vulnerability assessments. "
    "You follow OWASP Top 10 (2021), CWE Top 25, and NIST guidelines. "
    "For every finding: provide CVSS severity, proof of exploitability, and concrete remediation code. "
    "You never recommend disabling security controls. All user input is hostile. "
    "Default deny. Validate and sanitize at every trust boundary."
)

SYSTEM_ARCHITECTURE = (
    "You are a principal software architect who designs complex distributed systems. "
    "You think in trade-offs: consistency vs availability (CAP), monolith vs microservices, "
    "synchronous vs event-driven, build vs buy. "
    "You produce architecture decision records (ADRs), system diagrams, and service contracts. "
    "Always explain WHY a pattern is chosen over alternatives, and what the trade-offs are. "
    "Consider: scalability, reliability, maintainability, team capabilities, and time-to-market."
)


# ── Command Handlers ──────────────────────────────────────────────────────────

def cmd_frontend(task: str) -> str:
    return ai_query(
        f"Frontend engineering task: {task}\n\n"
        "## Solution\n"
        "Provide complete, working implementation with:\n"
        "- Component/module code with TypeScript types\n"
        "- CSS/styling (Tailwind preferred, or plain CSS)\n"
        "- State management approach\n"
        "- Performance considerations (memoization, lazy loading, bundle impact)\n"
        "- Accessibility requirements (ARIA, keyboard navigation)\n"
        "- Testing approach (unit test example)\n"
        "- Browser compatibility notes\n\n"
        "## Key Decisions\n"
        "Explain trade-offs in the implementation approach",
        SYSTEM_FRONTEND,
    )


def cmd_backend(task: str) -> str:
    return ai_query(
        f"Backend architecture/development task: {task}\n\n"
        "## Architecture\n"
        "- Service design and API contracts\n"
        "- Data model and database schema\n"
        "- Authentication/authorization approach\n\n"
        "## Implementation\n"
        "- Working code with error handling\n"
        "- Database queries with proper indexing\n"
        "- Input validation and sanitization\n\n"
        "## Operations\n"
        "- Logging and monitoring approach\n"
        "- Scaling considerations\n"
        "- Deployment requirements",
        SYSTEM_BACKEND,
    )


def cmd_aiml(task: str) -> str:
    return ai_query(
        f"AI/ML engineering task: {task}\n\n"
        "## Approach\n"
        "- Problem framing: what type of ML problem is this?\n"
        "- Data requirements and quality considerations\n"
        "- Model/architecture choice with rationale\n\n"
        "## Implementation\n"
        "- Complete working code (Python)\n"
        "- Data pipeline\n"
        "- Model training/fine-tuning approach\n"
        "- Evaluation metrics\n\n"
        "## Production\n"
        "- Serving architecture (API endpoint, batch, streaming)\n"
        "- Monitoring: performance drift detection\n"
        "- Bias and fairness considerations",
        SYSTEM_AIML,
    )


def cmd_review(code_or_task: str) -> str:
    return ai_query(
        f"Code review request: {code_or_task}\n\n"
        "## Security Review\n"
        "List all security vulnerabilities with CVSS severity and remediation code\n\n"
        "## Performance Review\n"
        "Identify N+1 queries, inefficient algorithms, memory leaks, and bottlenecks\n\n"
        "## Maintainability Review\n"
        "Code complexity, naming, missing tests, documentation gaps\n\n"
        "## Correctness Review\n"
        "Edge cases, error handling, race conditions, data validation\n\n"
        "## Priority Fixes\n"
        "Ranked list of changes with before/after code examples",
        SYSTEM_REVIEW,
    )


def cmd_devops(task: str) -> str:
    return ai_query(
        f"DevOps/infrastructure task: {task}\n\n"
        "## Solution\n"
        "Provide complete working configuration files:\n"
        "- Dockerfile (multi-stage if appropriate)\n"
        "- Docker Compose or Kubernetes manifests\n"
        "- CI/CD pipeline (GitHub Actions / GitLab CI)\n"
        "- Infrastructure as Code (Terraform/Pulumi if applicable)\n\n"
        "## Security\n"
        "- Secrets management approach\n"
        "- Least privilege IAM/RBAC configuration\n\n"
        "## Monitoring\n"
        "- Health checks and alerting setup\n"
        "- Key metrics to track",
        SYSTEM_DEVOPS,
    )


def cmd_database(task: str) -> str:
    return ai_query(
        f"Database design/optimization task: {task}\n\n"
        "## Schema Design\n"
        "- CREATE TABLE statements with proper types and constraints\n"
        "- Index strategy with rationale for each index\n"
        "- Relationships and referential integrity\n\n"
        "## Queries\n"
        "- Key query patterns with optimization\n"
        "- EXPLAIN ANALYZE interpretation\n"
        "- Pagination strategy\n\n"
        "## Operations\n"
        "- Migration strategy\n"
        "- Backup and recovery approach\n"
        "- Scaling plan (replication, sharding, caching)",
        SYSTEM_DATABASE,
    )


def cmd_security(task: str) -> str:
    return ai_query(
        f"Security review/task: {task}\n\n"
        "## Threat Model\n"
        "- Attack surface and trust boundaries\n"
        "- Threat actors and their capabilities\n"
        "- High-value targets\n\n"
        "## Vulnerability Assessment\n"
        "For each finding:\n"
        "- CVSS severity (Critical/High/Medium/Low)\n"
        "- Proof of exploitability\n"
        "- Remediation code example\n\n"
        "## Security Controls\n"
        "- Authentication/authorization improvements\n"
        "- Input validation and output encoding\n"
        "- Secrets management recommendations\n\n"
        "## Prioritized Fixes\n"
        "Ordered by risk × exploitability",
        SYSTEM_SECURITY,
    )


def cmd_architecture(system: str) -> str:
    return ai_query(
        f"Architecture design for: {system}\n\n"
        "## Architecture Decision Record (ADR)\n"
        "- Context: what forces and constraints drive this decision?\n"
        "- Options considered (at least 3 alternatives)\n"
        "- Decision and rationale\n"
        "- Trade-offs accepted\n\n"
        "## System Design\n"
        "- Component diagram (ASCII or description)\n"
        "- Service responsibilities and interfaces\n"
        "- Data flows and state management\n"
        "- API contracts\n\n"
        "## Operational Concerns\n"
        "- Deployment model\n"
        "- Scaling approach\n"
        "- Failure modes and recovery\n"
        "- Monitoring and observability",
        SYSTEM_ARCHITECTURE,
    )


def cmd_refactor(description: str) -> str:
    return ai_query(
        f"Refactoring guidance for: {description}\n\n"
        "## Code Smells Identified\n"
        "List specific issues with examples\n\n"
        "## Refactoring Plan\n"
        "Step-by-step safe refactoring sequence (test coverage before each change)\n\n"
        "## Before / After Examples\n"
        "Show concrete code transformations for the most impactful changes\n\n"
        "## Testing Strategy\n"
        "How to verify the refactoring didn't break behavior\n\n"
        "## Estimated Effort\n"
        "Hours, risk level, and recommended order",
        SYSTEM_REVIEW,
    )


def cmd_debug(problem: str) -> str:
    return ai_query(
        f"Debugging help for: {problem}\n\n"
        "## Root Cause Analysis\n"
        "Most likely causes ranked by probability\n\n"
        "## Diagnostic Steps\n"
        "Step-by-step investigation with specific commands/code to run\n\n"
        "## Fix Options\n"
        "Solutions ranked by: correctness, simplicity, risk\n\n"
        "## Prevention\n"
        "How to prevent this class of bug in the future\n\n"
        "## Verification\n"
        "How to confirm the fix worked (test case)",
        SYSTEM_BACKEND,
    )


def cmd_status() -> str:
    tasks = load_tasks()
    if not tasks:
        return "No engineering tasks recorded yet."
    lines = ["## Engineering Tasks\n"]
    for t in tasks[:10]:
        lines.append(f"- [{t.get('type', 'task')}] {t.get('description', '')[:80]} — {t.get('created_at', '')[:10]}")
    return "\n".join(lines)


# ── Message Routing ────────────────────────────────────────────────────────────

COMMANDS = {
    "eng frontend": (cmd_frontend, 1),
    "eng backend": (cmd_backend, 1),
    "eng aiml": (cmd_aiml, 1),
    "eng review": (cmd_review, 1),
    "eng devops": (cmd_devops, 1),
    "eng database": (cmd_database, 1),
    "eng security": (cmd_security, 1),
    "eng architecture": (cmd_architecture, 1),
    "eng refactor": (cmd_refactor, 1),
    "eng debug": (cmd_debug, 1),
    "eng status": (lambda: cmd_status(), 0),
}


def process_message(text: str) -> str | None:
    text_lower = text.strip().lower()
    for prefix, (handler, needs_arg) in COMMANDS.items():
        if text_lower.startswith(prefix):
            arg = text[len(prefix):].strip() if needs_arg else ""
            tasks = load_tasks()
            tasks.insert(0, {
                "id": str(uuid.uuid4())[:8],
                "type": prefix.replace("eng ", ""),
                "description": arg[:200],
                "created_at": now_iso(),
            })
            save_tasks(tasks[:50])
            if needs_arg:
                return handler(arg)
            return handler()
    return None


def process_queue() -> None:
    queue_file = AGENT_TASKS_DIR / "engineering-assistant.queue.jsonl"
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
                    f"Engineering assistant could not process: {task.get('input', '')}",
                    status="unhandled",
                )
        remaining.append(json.dumps(task))
    queue_file.write_text("\n".join(remaining) + "\n" if remaining else "")


# ── Main Loop ──────────────────────────────────────────────────────────────────

def main() -> None:
    state = {
        "agent": "engineering-assistant",
        "started_at": now_iso(),
        "status": "running",
        "last_poll": now_iso(),
    }
    write_state(state)
    logger.info("Engineering Assistant started.")
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
                if role == "user" and text.strip().lower().startswith("eng "):
                    result = process_message(text)
                    if result:
                        append_chatlog({
                            "id": str(uuid.uuid4()),
                            "role": "assistant",
                            "agent": "engineering-assistant",
                            "text": result,
                            "ts": now_iso(),
                        })
                processed.add(eid)

            state["last_poll"] = now_iso()
            write_state(state)
        except Exception as exc:
            logger.error("Engineering assistant error: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
