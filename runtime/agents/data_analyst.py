from __future__ import annotations

from agents.base import BaseAgent


class DataAnalystAgent(BaseAgent):
    agent_id = "data_analyst"
    required_fields = ("task",)

    def execute(self, payload: dict) -> dict:
        data_input = payload.get("data", payload.get("task", ""))
        prompt = (
            "Analyze the provided CSV/JSON-like data and return JSON: "
            "{summary, key_metrics, anomalies, chart_data}."
            f" Data: {data_input}"
        )
        data, tokens = self._ask_json(prompt=prompt, system="You are a data analyst.")
        data.setdefault("summary", "")
        data.setdefault("key_metrics", {})
        data.setdefault("anomalies", [])
        data.setdefault("chart_data", {})
        data["tokens_used"] = tokens
        return data
