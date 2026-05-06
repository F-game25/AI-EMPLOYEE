"""Language-Action Model routing — skill invocation."""
import logging

logger = logging.getLogger(__name__)


def route_lam(request: dict) -> dict:
    """Route to LAM (invoke skills/tools from runtime/skills/catalog)."""
    try:
        from runtime.skills.catalog import get_skill

        skill_name = request.get("skill", "")
        args = request.get("args", {})

        if not skill_name:
            return {"status": "error", "error": "Missing skill name"}

        skill = get_skill(skill_name)
        if not skill:
            return {"status": "error", "error": f"Skill not found: {skill_name}"}

        result = skill.run(**args)

        return {
            "status": "success",
            "output": result,
            "provider": "skill_catalog",
            "model": skill_name,
        }

    except Exception as e:
        logger.error(f"route_lam failed: {e}")
        return {"status": "error", "error": str(e)}
