"""Coherence C3 — the 3 previously-missing SalesPage endpoints (money anchor):
order core-field update, and the WhatsApp/e-mail share-link generator. The /photo
upload is pure Node multipart (no Python logic). See docs/SYSTEM_COHERENCE_PLAN.md (C3)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

# Imported lazily by the fixture (not at module top) — importing orders_store runs
# _init_table() which opens a DB, and that must happen AFTER isolated_ai_home has
# redirected AI_HOME, not at collection time.
store = None
pitch = None


@pytest.fixture(autouse=True)
def _orders_store(isolated_ai_home):
    global store, pitch
    import core.orders_store as _store
    import core.pitch as _pitch
    store, pitch = _store, _pitch
    store._init_table()  # create the orders table in this test's isolated AI_HOME
    yield


def _new_order():
    return store.order_aanmaken(bedrijfsnaam="Bakkerij Jansen", plaats="Delft",
                                branche="bakker", contact="info@jansen.nl", prijs=299)


def test_order_bijwerken_updates_only_provided_fields():
    o = _new_order()
    res = store.order_bijwerken(o["id"], bedrijfsnaam="Bakkerij De Vries", prijs=349)
    assert res["ok"] is True
    assert res["order"]["bedrijfsnaam"] == "Bakkerij De Vries"
    assert res["order"]["prijs"] == 349
    assert res["order"]["plaats"] == "Delft"      # untouched field preserved
    assert res["order"]["branche"] == "bakker"


def test_order_bijwerken_noop_when_nothing_to_change():
    o = _new_order()
    res = store.order_bijwerken(o["id"])
    assert res["ok"] is True and res["order"]["id"] == o["id"]


def test_order_bijwerken_missing_order_is_honest():
    res = store.order_bijwerken("order-doesnotexist", prijs=100)
    assert res["ok"] is False and "error" in res


def test_deel_links_build_demo_and_share_urls():
    o = _new_order()
    store.status_bijwerken(o["id"], "ter_review", demo_pad="bakker_jansen_delft/index.html")
    store.pitch_bijwerken(o["id"], "Hoi Jansen, ik heb een site gemaakt. Bekijk hem hier.")
    res = pitch.genereer_deel_links(o["id"], base_url="https://demo.example.com")
    assert res["ok"] is True
    assert res["demo_url"] == "https://demo.example.com/api/demos/bakker_jansen_delft/"
    assert res["whatsapp_url"].startswith("https://wa.me/?text=")
    assert res["email_url"].startswith("mailto:?")


def test_deel_links_require_a_pitch_first():
    o = _new_order()  # no pitch generated yet
    res = pitch.genereer_deel_links(o["id"])
    assert res["ok"] is False and "pitch" in res["error"].lower()
