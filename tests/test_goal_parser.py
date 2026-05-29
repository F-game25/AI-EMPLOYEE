import sys
from pathlib import Path


RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from core.goal_parser import _keyword_fallback, parse_goal  # noqa: E402


def test_time_question_is_conversation_not_executable_goal():
    plan = parse_goal("what time is it")

    assert plan["is_goal"] is False
    assert plan["goal_type"] == "conversation"
    assert plan["response_type"] == "time"
    assert plan["task_plan"] == []


def test_plain_what_is_question_does_not_create_research_file():
    plan = parse_goal("what is LangGraph?")

    assert plan["is_goal"] is False
    assert plan["goal_type"] == "conversation"
    assert plan["task_plan"] == []


def test_research_command_still_builds_research_plan():
    plan = _keyword_fallback("research LangGraph and save a report")

    assert plan["is_goal"] is True
    assert plan["goal_type"] == "research"
    assert [step["action"] for step in plan["task_plan"]] == [
        "web_search",
        "llm_extract",
        "save_file",
    ]


def test_content_command_still_builds_content_plan():
    plan = _keyword_fallback("write a blog post about time management")

    assert plan["is_goal"] is True
    assert plan["goal_type"] == "content_creation"
    assert plan["task_plan"][-1]["action"] == "save_file"
