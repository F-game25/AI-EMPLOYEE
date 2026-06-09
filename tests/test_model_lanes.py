"""Tests for named model lanes (runtime/core/model_lanes.py)."""
import os
import sys
from pathlib import Path

import pytest

_RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from core import model_lanes as ml  # noqa: E402


def test_all_lanes_resolve_to_nonempty_model():
    models = ml.lane_models()
    assert set(models.keys()) == set(ml.ALL_LANES)
    for lane, model in models.items():
        assert isinstance(model, str) and model, f"{lane} resolved empty"


def test_task_to_lane_mapping():
    assert ml.lane_for_task("coding") == ml.LANE_CODE
    assert ml.lane_for_task("code") == ml.LANE_CODE
    assert ml.lane_for_task("research") == ml.LANE_DEEP
    assert ml.lane_for_task("reasoning") == ml.LANE_REASONING
    assert ml.lane_for_task("routing") == ml.LANE_FAST
    # unknown / empty -> DEFAULT
    assert ml.lane_for_task("something-weird") == ml.LANE_DEFAULT
    assert ml.lane_for_task(None) == ml.LANE_DEFAULT


def test_env_override_wins():
    os.environ["MODEL_LANE_CODE"] = "my-custom-coder:1b"
    try:
        assert ml.resolve_lane(ml.LANE_CODE) == "my-custom-coder:1b"
    finally:
        del os.environ["MODEL_LANE_CODE"]


def test_resolve_for_task():
    assert ml.resolve_for_task("coding") == ml.resolve_lane(ml.LANE_CODE)


def test_hot_lane_models_deduped_and_nonempty():
    hot = ml.hot_lane_models()
    assert hot, "no hot models"
    assert len(hot) == len(set(hot)), "hot models not deduped"


def test_unknown_lane_falls_back_to_default():
    assert ml.resolve_lane("NONSENSE") == ml.resolve_lane(ml.LANE_DEFAULT)
