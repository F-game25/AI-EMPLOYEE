import logging
from typing import Optional
from collections import defaultdict
import datetime

logger = logging.getLogger(__name__)


class ExecutionHeatmapAggregator:
    def __init__(self):
        self.heatmaps: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    def record_execution(self, agent_id: str, action_type: str = "task") -> None:
        now = datetime.datetime.now()
        hour = now.hour
        day_of_week = now.weekday()

        key = f"{hour}_{day_of_week}"
        self.heatmaps[agent_id][key] += 1

    def get_heatmap(self, agent_id: str) -> dict:
        matrix = {}
        for hour in range(24):
            matrix[hour] = {}
            for day in range(7):
                key = f"{hour}_{day}"
                matrix[hour][day] = self.heatmaps[agent_id].get(key, 0)
        return matrix

    def get_all_heatmaps(self) -> dict:
        return {agent_id: self.get_heatmap(agent_id) for agent_id in self.heatmaps}

    def get_peak_hours(self, agent_id: str) -> list[int]:
        heatmap = self.get_heatmap(agent_id)
        peak_hours = []
        for hour in range(24):
            hour_total = sum(heatmap[hour].values())
            if hour_total > 0:
                peak_hours.append((hour, hour_total))

        peak_hours.sort(key=lambda x: -x[1])
        return [h[0] for h in peak_hours[:3]]

    def reset_heatmap(self, agent_id: str) -> None:
        if agent_id in self.heatmaps:
            self.heatmaps[agent_id].clear()


_instance: Optional[ExecutionHeatmapAggregator] = None


def get_heatmap_aggregator() -> ExecutionHeatmapAggregator:
    global _instance
    if _instance is None:
        _instance = ExecutionHeatmapAggregator()
    return _instance
