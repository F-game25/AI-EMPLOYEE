"""
ASCEND AI — Mock Layer
Returns safe data when ~/.ai-employee/ is missing or all bots are down.
All responses include "mock": True so the frontend knows the data is synthetic.
"""

MOCK_AGENTS = [
    "task-orchestrator",
    "company-builder",
    "hr-manager",
    "finance-wizard",
    "brand-strategist",
    "growth-hacker",
    "project-manager",
    "lead-hunter",
    "content-master",
    "social-guru",
    "intel-agent",
    "email-ninja",
    "support-bot",
    "data-analyst",
    "creative-studio",
    "web-sales",
    "skills-manager",
    "polymarket-trader",
    "mirofish-researcher",
    "discovery",
]


def get_mock_agents():
    return [
        {"name": n, "status": "offline", "pid": None, "uptime": None, "mock": True}
        for n in MOCK_AGENTS
    ]


def get_mock_system_stats():
    return {
        "cpu_percent": 23,
        "ram_used_gb": 4.2,
        "ram_total_gb": 16,
        "gpu_percent": 0,
        "temp_celsius": 42,
        "mock": True,
    }


def get_mock_chat_response():
    return (
        "ASCEND AI is initializing. Some agents are currently offline. "
        "Use the Doctor page to run diagnostics."
    )


def get_mock_health():
    return {"status": "ok", "version": "1.0.0", "mock": True}
