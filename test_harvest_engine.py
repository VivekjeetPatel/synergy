from harvest_engine import *

Q = lambda **k: Quote(**{**dict(market="M", price_rs_kg=20, distance_km=45, age_hours=2, verified=True), **k})

def test_never_single_number():
    r = advise([Q(market="A"), Q(market="B", price_rs_kg=24, distance_km=90)])
    assert all(o.net_low < o.net_high for o in r["options"])

def test_net_price_beats_headline_blindness():
    # 90 km market quoting Rs24 must NOT look better than 45 km Rs21 by a wide margin once costs are counted
    d = evaluate(Q(market="D", price_rs_kg=24, distance_km=90))
    c = evaluate(Q(market="C", price_rs_kg=21, distance_km=45))
    assert d.mid - c.mid < 1.0 and d.net_low < c.net_low

def test_stale_or_unverified_widens_interval():
    fresh = evaluate(Q()); stale = evaluate(Q(age_hours=30, verified=False))
    assert (stale.net_high - stale.net_low) > (fresh.net_high - fresh.net_low)

def test_rain_prefers_selling_today():
    r = advise([Q(market="A")], p_rain=0.8)
    assert r["best"].when == "today"

def test_missing_price_excluded_not_guessed():
    r = advise([Q(market="X", price_rs_kg=None), Q(market="Y")])
    assert r["excluded"] and all(o.market == "Y" for o in r["options"])

def test_no_quotes_no_advice_human_review():
    r = advise([Q(price_rs_kg=None)])
    assert r["status"] == "NO_ADVICE" and r["human_review"]

def test_unverified_only_forces_human_review():
    r = advise([Q(verified=False)])
    assert r["human_review"]

def test_message_has_disclaimer():
    r = advise([Q(market="A", distance_km=10), Q(market="B", price_rs_kg=15, distance_km=80)], p_rain=0.1)
    if not r["human_review"]:
        assert "guarantee nahin" in message_hi(r)
