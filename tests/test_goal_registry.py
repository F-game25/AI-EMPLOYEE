"""GoalRegistry — one canonical goal identity across the three goal layers
(goal_store / goal_engine / roadmap_engine), without collapsing them.
"""
import importlib

import pytest


@pytest.fixture()
def reg(tmp_path, monkeypatch):
    # Isolate the registry DB in a temp STATE_DIR (resolved lazily per call).
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    gr = importlib.import_module("core.goal_registry")
    return gr


def test_register_is_idempotent_per_native_id(reg):
    a = reg.register_goal("ship feature", reg.SOURCE_RUN_GOAL, "g1")
    b = reg.register_goal("ship feature", reg.SOURCE_RUN_GOAL, "g1", status="active")
    assert a == b                                  # same (source, native) -> same canonical id


def test_distinct_sources_get_distinct_canonical_ids(reg):
    c1 = reg.register_goal("run goal", reg.SOURCE_RUN_GOAL, "r1")
    c2 = reg.register_goal("okr objective", reg.SOURCE_OBJECTIVE, "o1")
    assert c1 != c2
    ids = {g["canonical_id"] for g in reg.get_goal_registry().list_goals()}
    assert {c1, c2} <= ids                         # both discoverable in one place


def test_link_unifies_layers_under_one_identity(reg):
    cid = reg.register_goal("launch", reg.SOURCE_OBJECTIVE, "obj-9")
    reg.get_goal_registry().link_goal(cid, reg.SOURCE_ROADMAP, "rm-9")
    g = reg.get_goal_registry().get_goal(cid)
    sources = {l["source"] for l in g["links"]}
    assert sources == {reg.SOURCE_OBJECTIVE, reg.SOURCE_ROADMAP}   # one goal, two layers


def test_resolve_and_update_status(reg):
    cid = reg.register_goal("x", reg.SOURCE_ROADMAP, "rm-1")
    assert reg.get_goal_registry().resolve(reg.SOURCE_ROADMAP, "rm-1") == cid
    assert reg.get_goal_registry().update_status(reg.SOURCE_ROADMAP, "rm-1", "completed") is True
    g = reg.get_goal_registry().get_goal(cid)
    assert g["links"][0]["status"] == "completed"


def test_register_helper_never_raises_and_returns_id(reg):
    assert reg.register_goal("ok", reg.SOURCE_RUN_GOAL, "ok-1") is not None
    # Bad source/id types are coerced, not fatal.
    assert reg.register_goal("", reg.SOURCE_RUN_GOAL, 12345) is not None
