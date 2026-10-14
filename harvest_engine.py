"""
HarvestWindow Advisor - net-realisable-price engine (Round 1 feasibility proof).

SIMULATED DATA / ILLUSTRATIVE PARAMETERS. Nothing here is a guaranteed price.
Every assumption is in PARAMS and is labelled ASSUMPTION; calibrate with FPO data.
The LLM layer (not in this file) only parses messy quotes and writes the explanation;
all numbers come from this deterministic, auditable engine.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

PARAMS = {
    # CASE EVIDENCE: transport+loading removes Rs 4-6/kg on a 90 km market
    "transport_rs_per_kg_at_90km": (4.0, 6.0),
    "ref_distance_km": 90.0,                      # ASSUMPTION: cost scales linearly with distance
    "shrink_same_day_pct": (2.0, 4.0),            # ASSUMPTION: handling/sorting shrink
    "shrink_per_30km_pct": (0.5, 1.0),            # ASSUMPTION: transit shrink
    "delay_shrink_per_day_pct": (2.0, 4.0),       # ASSUMPTION: extra spoilage if held a day
    "rain_damage_pct": (5.0, 15.0),               # ASSUMPTION: quality loss if rain hits unsold produce
    # quote uncertainty band (+/-), by freshness and source verification
    "band_fresh_verified": 0.08,                  # ASSUMPTION
    "band_fresh_unverified": 0.15,                # ASSUMPTION
    "band_stale_extra": 0.10,                     # ASSUMPTION: added if quote older than 12 h
    "stale_hours": 12,
    "risk_weight_lower_bound": 0.5,               # score = (1-w)*mid + w*low  (risk-averse; human-tunable)
}

@dataclass
class Quote:
    market: str
    price_rs_kg: Optional[float]
    distance_km: float
    age_hours: float = 0.0
    verified: bool = False       # confirmed by FPO agent / official source
    source: str = "unknown"

@dataclass
class Option:
    market: str
    when: str
    net_low: float
    net_high: float
    score: float
    notes: List[str] = field(default_factory=list)
    @property
    def mid(self): return (self.net_low + self.net_high) / 2

def _band(q: Quote) -> float:
    b = PARAMS["band_fresh_verified"] if q.verified else PARAMS["band_fresh_unverified"]
    if q.age_hours > PARAMS["stale_hours"]:
        b += PARAMS["band_stale_extra"]
    return b

def evaluate(q: Quote, delay_days: int = 0, p_rain: float = 0.0) -> Option:
    notes = []
    b = _band(q)
    plo, phi = q.price_rs_kg * (1 - b), q.price_rs_kg * (1 + b)
    k = q.distance_km / PARAMS["ref_distance_km"]
    clo, chi = (PARAMS["transport_rs_per_kg_at_90km"][0] * k, PARAMS["transport_rs_per_kg_at_90km"][1] * k)
    s_lo = PARAMS["shrink_same_day_pct"][0] + PARAMS["shrink_per_30km_pct"][0] * q.distance_km / 30
    s_hi = PARAMS["shrink_same_day_pct"][1] + PARAMS["shrink_per_30km_pct"][1] * q.distance_km / 30
    if delay_days:
        s_lo += delay_days * PARAMS["delay_shrink_per_day_pct"][0] + p_rain * PARAMS["rain_damage_pct"][0]
        s_hi += delay_days * PARAMS["delay_shrink_per_day_pct"][1] + p_rain * PARAMS["rain_damage_pct"][1]
        notes.append(f"held {delay_days} day(s), rain probability {p_rain:.0%}")
    if not q.verified: notes.append("quote unverified")
    if q.age_hours > PARAMS["stale_hours"]: notes.append(f"quote {q.age_hours:.0f} h old")
    net_low = plo * (1 - s_hi / 100) - chi
    net_high = phi * (1 - s_lo / 100) - clo
    w = PARAMS["risk_weight_lower_bound"]
    mid = (net_low + net_high) / 2
    return Option(q.market, "today" if not delay_days else f"+{delay_days}d",
                  round(net_low, 1), round(net_high, 1), round((1 - w) * mid + w * net_low, 2), notes)

def advise(quotes: List[Quote], p_rain: float = 0.0, consider_delay: bool = True):
    options, excluded = [], []
    for q in quotes:
        if q.price_rs_kg is None or q.price_rs_kg <= 0:
            excluded.append((q.market, "no usable price - excluded, not guessed")); continue
        options.append(evaluate(q, 0, p_rain))
        if consider_delay:
            options.append(evaluate(q, 1, p_rain))
    if not options:
        return {"status": "NO_ADVICE", "reason": "no usable quotes", "options": [], "excluded": excluded,
                "human_review": True}
    options.sort(key=lambda o: o.score, reverse=True)
    best, second = options[0], options[1] if len(options) > 1 else None
    if second is None or best.net_low > second.net_high:
        conf = "HIGH"
    elif best.mid - second.mid >= 1.5:
        conf = "MEDIUM"
    else:
        conf = "LOW"
    # LOW confidence or all-unverified -> mandatory human review; never auto-issued
    human = conf == "LOW" or all("quote unverified" in o.notes for o in options)
    return {"status": "OK", "confidence": conf, "human_review": human, "best": best,
            "options": options, "excluded": excluded}

def headline_pick(quotes: List[Quote]):
    """Baseline: what a farmer does today - chase the highest quoted price."""
    valid = [q for q in quotes if q.price_rs_kg]
    return max(valid, key=lambda q: q.price_rs_kg) if valid else None

def message_hi(res) -> str:
    """Template Hindi/English SMS body (LLM only polishes wording; numbers are fixed here)."""
    if res["status"] != "OK" or res["human_review"]:
        return "Salah abhi pakka nahin. Aapke FPO sahayak aapko call karenge. (Advice pending human check)"
    b = res["best"]
    return (f"Sujhav: {b.market} mandi mein {b.when} bechein. Kharch aur nuksan ke baad andaza "
            f"Rs {b.net_low:.0f}-{b.net_high:.0f}/kg. Yeh guarantee nahin hai. Baarish se bhaav/quality badal sakti hai.")

if __name__ == "__main__":
    # SIMULATED quotes: case gives only the Rs14-24 range; the middle values are illustrative
    quotes = [
        Quote("Local trader (0 km)", 14, 0, 2, True, "FPO agent"),
        Quote("Mandi B (25 km)", 18, 25, 3, True, "FPO agent"),
        Quote("Mandi C (45 km)", 21, 45, 4, True, "FPO agent"),
        Quote("Mandi D (90 km)", 24, 90, 5, True, "FPO agent"),
    ]
    hp = headline_pick(quotes)
    print(f"Baseline (chase highest headline): {hp.market} @ Rs{hp.price_rs_kg}/kg")
    for rain in (0.0, 0.7):
        res = advise(quotes, p_rain=rain)
        print(f"\n--- rain probability {rain:.0%} -> confidence {res['confidence']}, human_review={res['human_review']}")
        for o in res["options"][:5]:
            print(f"{o.market:22s} {o.when:5s} net Rs {o.net_low:5.1f} - {o.net_high:5.1f}  score {o.score:5.2f}  {o.notes}")
        print(message_hi(res))
