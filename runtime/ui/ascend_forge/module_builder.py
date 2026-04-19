"""Module Builder — wizard for creating new agents and tools via Ascend Forge.

Lets the user define a new module:
- Choose type (agent / tool / memory extension / UI component)
- Enter name and description
- Auto-generate a starter scaffold via the engine LLM (if available)
  or use the built-in template
- Submit the generated code through ForgeController

All generated code is validated in the sandbox before being offered for
deployment.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_RUNTIME = Path(__file__).resolve().parents[2]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False

# ── Templates ──────────────────────────────────────────────────────────────────

_MODULE_TYPES: dict[str, str] = {
    "Agent": "agents",
    "Tool / Skill": "skills",
    "Memory Extension": "memory",
    "Core Module": "core",
    "UI Component": "ui",
}

_TEMPLATES: dict[str, str] = {
    "Agent": '''\
"""{{NAME}} — AI Employee agent.

Responsibilities:
  - TODO

Usage::

    from agents.{{SLUG}} import {{CLASS}}
    agent = {{CLASS}}()
    result = agent.run(task="...")
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agents.{{SLUG}}")


class {{CLASS}}:
    """{{DESCRIPTION}}"""

    def run(self, *, task: str, context: dict | None = None) -> dict[str, Any]:
        """Execute the agent task."""
        context = context or {}
        logger.info("{{NAME}} running task: %s", task[:80])
        # TODO: implement logic
        return {"status": "ok", "task": task, "result": None}


def get_{{SLUG}}() -> {{CLASS}}:
    """Return a fresh {{CLASS}} instance."""
    return {{CLASS}}()
''',
    "Tool / Skill": '''\
"""{{NAME}} — AI Employee skill/tool.

Usage::

    from skills.{{SLUG}} import {{FUNC}}
    result = {{FUNC}}(input="...")
"""
from __future__ import annotations

from typing import Any


def {{FUNC}}(*, input: str, options: dict | None = None) -> dict[str, Any]:
    """{{DESCRIPTION}}"""
    options = options or {}
    # TODO: implement
    return {"input": input, "result": None}
''',
    "Memory Extension": '''\
"""{{NAME}} — custom memory extension for AI Employee.

Extends the memory layer with domain-specific storage or retrieval.
"""
from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.RLock()


class {{CLASS}}:
    """{{DESCRIPTION}}"""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def store(self, key: str, value: Any) -> None:
        with _LOCK:
            self._data[key] = value

    def retrieve(self, key: str) -> Any:
        with _LOCK:
            return self._data.get(key)
''',
    "Core Module": '''\
"""{{NAME}} — AI Employee core module.

{{DESCRIPTION}}
"""
from __future__ import annotations


class {{CLASS}}:
    """{{DESCRIPTION}}"""

    pass
''',
    "UI Component": '''\
"""{{NAME}} — Streamlit UI component for AI Employee.

Usage::

    from ui.{{SLUG}} import render_{{SLUG}}
    render_{{SLUG}}()
"""
from __future__ import annotations

import sys
from pathlib import Path

_RUNTIME = Path(__file__).resolve().parents[1]
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


def render_{{SLUG}}() -> None:
    """Render the {{NAME}} panel."""
    if not _HAS_ST:
        return
    st.subheader("{{NAME}}")
    st.caption("{{DESCRIPTION}}")
    # TODO: implement
    st.info("Coming soon.")
''',
}


def _fill_template(template: str, *, name: str, description: str) -> str:
    slug = name.lower().replace(" ", "_").replace("-", "_")
    cls = "".join(w.capitalize() for w in name.replace("-", " ").split())
    func = slug
    return (
        template
        .replace("{{NAME}}", name)
        .replace("{{SLUG}}", slug)
        .replace("{{CLASS}}", cls)
        .replace("{{FUNC}}", func)
        .replace("{{DESCRIPTION}}", description or f"{name} module.")
    )


def _target_module(module_type: str, name: str) -> str:
    """Derive the repo-relative module path from type and name."""
    slug = name.lower().replace(" ", "_").replace("-", "_")
    folder = _MODULE_TYPES.get(module_type, "core")
    return f"{folder}/{slug}.py"


def render_module_builder() -> None:
    """Render the module-builder wizard inside a Streamlit context."""
    if not _HAS_ST:
        print("Streamlit not installed — skipping module_builder render.")
        return

    st.subheader("🧩 Module Builder")
    st.caption(
        "Create new agents, tools, or modules. "
        "Generated code is validated in the sandbox before deployment."
    )

    col_type, col_name = st.columns(2)
    with col_type:
        module_type = st.selectbox(
            "Module type",
            list(_MODULE_TYPES.keys()),
            key="mb_type",
        )
    with col_name:
        name = st.text_input(
            "Module name",
            placeholder="My Custom Agent",
            key="mb_name",
        )

    description = st.text_area(
        "Description",
        placeholder="What does this module do?",
        height=80,
        key="mb_desc",
    )

    if name:
        template = _TEMPLATES.get(module_type, _TEMPLATES["Core Module"])
        generated = _fill_template(template, name=name, description=description)
        target = _target_module(module_type, name)
        st.caption(f"Target module: `{target}`")

        code = st.text_area(
            "Generated scaffold (edit before deploying)",
            value=generated,
            height=350,
            key="mb_code",
        )

        tag = st.text_input("Version tag", placeholder="v1.0", key="mb_tag")
        auto_deploy = st.checkbox("Auto-deploy if safe", value=False, key="mb_auto")

        if st.button("🚀 Create & Submit", key="mb_submit"):
            if not code.strip():
                st.error("Code cannot be empty.")
            else:
                _create_and_submit(target, code, description, tag, auto_deploy)
    else:
        st.info("Enter a module name above to generate a scaffold.")


def _create_and_submit(
    module: str,
    code: str,
    description: str,
    tag: str,
    auto_deploy: bool,
) -> None:
    try:
        from core.forge_controller import get_forge_controller
        result = get_forge_controller().submit_change(
            module=module,
            code=code,
            description=description,
            tag=tag,
            author="dashboard:module_builder",
            auto_deploy=auto_deploy,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"ForgeController error: {exc}")
        return

    status = result.get("status", "unknown")
    if status == "rejected":
        st.error(f"❌ Rejected: {result.get('reason', '')}")
        for err in result.get("validation", {}).get("errors", []):
            st.code(err, language="text")
    elif status == "awaiting_approval":
        st.warning(
            f"⏳ Awaiting approval — snapshot: `{result.get('snapshot_id')}`\n\n"
            f"{result.get('reason', '')}"
        )
    elif status == "deployed":
        st.success(f"✅ Module `{module}` deployed — snapshot: `{result.get('snapshot_id')}`")
    else:
        st.json(result)


if __name__ == "__main__" and _HAS_ST:
    st.set_page_config(page_title="Ascend Forge — Module Builder", page_icon="🧩")
    render_module_builder()
