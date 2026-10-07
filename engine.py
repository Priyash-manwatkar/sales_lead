import os
import random
from datetime import date, timedelta

import db

W = {"Company size": 7, "Revenue potential": 8, "Product fit": 12, "Purchase intent": 12, "Buying timeline": 9,
     "Decision-maker access": 7, "Current supplier": 5, "Requirement frequency": 7, "Engagement": 7,
     "Relationship": 7, "Past interactions": 5, "Geographic fit": 5, "Historical conversion": 9}
TL = {"Immediate": 1, "1-3 months": .75, "3-6 months": .4, "6+ months": .15, "Unknown": .1}
SUP = {"None": 1, "Local vendor": .7, "Regional brand": .5, "Major brand": .3}
SHARE = {"None": .5, "Local vendor": .35, "Regional brand": .25, "Major brand": .15}
HOME = ["Delhi", "Gurugram", "Noida", "Faridabad", "Rohtak", "Jaipur", "Ludhiana"]
STAGES = ["Lead", "Qualified", "Proposal", "Negotiation", "Won", "Lost"]
REPORTS = ["Company Intelligence Report", "Visit Report", "Opportunity Assessment", "Account Summary",
           "Follow-up Brief", "Management Report"]
BENCH = {  # employees, revenue Cr, model, products, likely requirement, competitors
    "Manufacturing": (450, 220, "B2B manufacturer selling to OEMs and distributors", "Industrial components, finished goods", "Regular supply of wires, cables and electricals", "Polycab, KEI, local traders"),
    "Construction": (300, 150, "EPC contractor / builder", "Residential and commercial projects", "Project-wise bulk electricals", "Havells, Finolex, local dealers"),
    "Real Estate": (200, 120, "Property developer", "Housing and commercial towers", "Wiring and electrical fit-out per project", "Finolex, RR Kabel, local dealers"),
    "Energy": (600, 400, "Power generation / distribution", "Power and renewable projects", "HT/LT cables, switchgear", "Polycab, KEI, Universal Cable"),
    "Logistics": (350, 180, "Warehousing and freight services", "Transport and warehousing", "Warehouse electrification and lighting", "Havells, Anchor, local vendors"),
    "Retail": (250, 130, "Multi-outlet retail chain", "Consumer goods retail", "Store fit-out electricals", "Havells, Legrand, local vendors")}
INDUSTRIES = list(BENCH)
CONFIDENCE = "Low-Medium: industry-benchmark estimate, not web-verified. Confirm during first visit."


def num(x, d=0):
    return d if x is None or x != x else x


def txt(x):
    return "" if x is None or x != x else str(x)


def money(l):
    return f"₹{l / 100:.1f} Cr" if l >= 100 else f"₹{l:.0f} L"


def band(s):
    return "High" if s >= 70 else "Medium" if s >= 45 else "Low"


def ai(prompt, fallback):
    """Optional LLM polish: used only if ANTHROPIC_API_KEY is set, otherwise the offline text is returned."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return fallback
    try:
        import anthropic
        m = anthropic.Anthropic().messages.create(model="claude-sonnet-5-5", max_tokens=1200,
                                                  messages=[{"role": "user", "content": prompt}])
        return m.content[0].text
    except Exception:
        return fallback


def win_rate(ind):
    d = db.q("SELECT stage FROM companies WHERE industry=? AND stage IN ('Won','Lost')", (ind,))
    return (d.stage == "Won").mean() if len(d) else .3


def score_parts(r, n):
    f = {"Company size": min(num(r.employees) / 1000, 1) ** .5, "Revenue potential": min(num(r.revenue_cr) / 500, 1) ** .5,
         "Product fit": num(r.fit) / 5, "Purchase intent": num(r.intent) / 5, "Buying timeline": TL.get(r.timeline, .1),
         "Decision-maker access": num(r.dm_access) / 5, "Current supplier": SUP.get(r.supplier, .5),
         "Requirement frequency": min(num(r.freq_per_yr) / 12, 1), "Engagement": num(r.engagement) / 5,
         "Relationship": num(r.relationship) / 5, "Past interactions": min(n / 8, 1),
         "Geographic fit": 1 if r.city in HOME else .5, "Historical conversion": min(win_rate(r.industry) / .5, 1)}
    return {k: round(v * W[k], 1) for k, v in f.items()}


def rescore(cid):
    r = db.q("SELECT * FROM companies WHERE id=?", (int(cid),)).iloc[0]
    n = int(db.q("SELECT COUNT(*) c FROM events WHERE company_id=?", (int(cid),)).c[0])
    s = round(sum(score_parts(r, n).values()))
    old = r.score
    prev = s + random.randint(-6, 6) if old is None or old != old else (old if s != old else r.prev_score)
    db.run("UPDATE companies SET score=?, prev_score=? WHERE id=?", (s, prev, int(cid)))


def rescore_missing():
    for i in db.q("SELECT id FROM companies WHERE score IS NULL").id:
        rescore(i)


def estimate(r):
    annual = num(r.order_value_l) * num(r.freq_per_yr)
    share = SHARE.get(r.supplier, .25)
    exp = annual * num(r.fit) / 5 * share
    est = {"Estimated annual demand": annual, "Conservative": exp * .5, "Expected": exp, "High-potential": exp * 1.6}
    asm = [f"Annual demand = order value {money(num(r.order_value_l))} x {num(r.freq_per_yr):.0f} orders/year",
           f"Product fit {num(r.fit):.0f}/5 scales the addressable share",
           f"Current supplier '{r.supplier}' implies we can win ~{share * 100:.0f}% of wallet",
           "Conservative = 50% of expected; High-potential = 160% of expected",
           "Estimates only, not confirmed revenue"]
    return est, asm


def enrich(name, ind, city):
    e, rv, model, prod, req, comp = BENCH.get(ind, BENCH["Manufacturing"])
    k = random.Random(name.lower()).uniform(.7, 1.4)
    return dict(employees=int(e * k), revenue_cr=round(rv * k, 1), business_model=model, products=prod,
                requirement=req, competitors=comp, geography=f"{city} plus nearby regional markets")


def strategic(r):
    lvl = "High" if num(r.fit) >= 4 else "Moderate" if num(r.fit) >= 3 else "Low"
    return f"{lvl} strategic relevance: {r.industry} account in {r.city} with {num(r.freq_per_yr):.0f} expected orders/year (AI estimate)."


def next_action(r, idle):
    o = txt(r.objection).lower()
    if r.stage == "Won": return "Schedule account review and pitch adjacent products"
    if r.stage == "Lost": return "Re-visit in 90 days with a fresh offer"
    if any(w in o for w in ("price", "cost", "rate")): return "Send a revised commercial offer addressing the price concern"
    if r.score >= 70 and idle > 14: return "Priority call today: high-score account going cold"
    if r.stage == "Proposal": return "Follow up on the proposal and ask for a decision date"
    if r.stage == "Negotiation": return "Close open terms; involve your manager if needed"
    if idle > 30: return "Re-engage by phone with a relevant case study"
    if num(r.dm_access) <= 2: return "Get introduced to the decision-maker"
    return "Schedule the next visit and confirm requirement quantities"


def summary(r, last):
    return (f"{r['name']} is a {r.industry} account in {r.city} at the {r.stage} stage, scoring {r.score:.0f}/100 ({band(r.score)}). "
            f"Requirement: {txt(r.requirement) or 'not yet captured'}. Main objection: {txt(r.objection) or 'none raised'}. "
            f"Last touch was a {last.kind.lower()} on {last['dt']}. Expected annual potential is about {money(estimate(r)[0]['Expected'])} (estimate).")


def stage_change(cid, old, new):
    if old != new:
        db.log(cid, {"Won": "Closed", "Lost": "Lost"}.get(new, "Opportunity Change"), f"Stage: {old} → {new}")


def lines(t):
    return [x.strip("-• ").strip() for x in txt(t).replace(";", "\n").split("\n") if x.strip()]


def visit_report(v, score):
    o, pain = lines(v["obj"]), [l for l in lines(v["req"] + "\n" + v["disc"])
                                if any(w in l.lower() for w in ("delay", "urgent", "shortage", "quality", "cost", "issue", "problem"))]
    days = 2 if score >= 70 else 5 if score >= 45 else 10
    act = ("Send revised pricing/commercial offer addressing the price objection" if any("price" in x.lower() for x in o)
           else "Confirm commitments in writing and share requested details" if v["com"].strip()
           else "Call within a week to validate requirement quantities")
    return {"Executive summary": f"Visited {v['company']} on {v['dt']} for {v['purpose'].lower()}. Met {v['people']}. Requirement: {v['req'] or 'not stated'}. Key concern: {o[0] if o else 'none raised'}.",
            "Customer requirement": v["req"] or "Not stated", "Key discussion points": lines(v["disc"]) or ["-"],
            "Pain points": pain or ["None explicitly stated"], "Objections": o or ["None raised"],
            "Opportunities": [f"Supply opportunity: {l}" for l in lines(v["req"])] + lines(v["com"]),
            "Action items": lines(v["nxt"]) + lines(v["com"]), "Follow-up date": str(date.today() + timedelta(days=days)),
            "Recommended next action": act}


def report(kind, r, cs, ev, s):
    est, asm = estimate(r)
    top = sorted(s.items(), key=lambda kv: -kv[1] / W[kv[0]])
    hist = "\n".join(f"- {x.dt}: **{x.kind}**: {x.title}" for x in ev.tail(6).itertuples())
    idle = (date.today() - date.fromisoformat(ev.dt.max())).days
    people = ", ".join(f"{c.name} ({c.role}{', DM' if c.is_dm else ''})" for c in cs.itertuples()) or "None recorded"
    rep = ev[ev.kind == "Report"]
    profile = (f"- **Industry:** {r.industry} | **City:** {r.city} | **Employees:** {num(r.employees):.0f} | **Revenue:** ₹{num(r.revenue_cr):.0f} Cr\n"
               f"- **Model:** {txt(r.business_model) or '-'}\n- **Products:** {txt(r.products) or '-'}\n- **Competitors:** {txt(r.competitors) or '-'}\n- **Contacts:** {people}")
    pot = "\n".join(f"- {k}: **{money(v)}**" for k, v in est.items())
    why = ", ".join(f"{k} ({s[k]:.0f}/{W[k]})" for k, _ in top[:3])
    weak = ", ".join(f"{k} ({s[k]:.0f}/{W[k]})" for k, _ in top[-2:])
    body = {
        "Company Intelligence Report": f"## Profile\n{profile}\n\n## Strategic relevance\n{strategic(r)}\n\n## Data confidence\n{CONFIDENCE}",
        "Visit Report": rep.detail.iloc[-1] if len(rep) else "No visit report saved yet. Use the Visit Report page.",
        "Opportunity Assessment": f"## Score {r.score:.0f}/100 ({band(r.score)})\nStrongest: {why}. Weakest: {weak}.\n\n## Opportunity potential\n{pot}\n\n**Assumptions**\n" + "\n".join(f"- {a}" for a in asm),
        "Account Summary": summary(r, ev.iloc[-1]) + f"\n\n## Recent history\n{hist}",
        "Follow-up Brief": f"- **Next follow-up:** {txt(r.next_followup) or 'not set'}\n- **Idle for:** {idle} days\n- **Open objection:** {txt(r.objection) or 'none'}\n- **Recommended action:** {next_action(r, idle)}\n\n## Recent history\n{hist}",
        "Management Report": f"**Stage:** {r.stage} | **Owner:** {r.owner} | **Score:** {r.score:.0f} ({band(r.score)})\n\n## Potential\n{pot}\n\n## Risks\n- Objection: {txt(r.objection) or 'none'}\n- Weak factors: {weak}\n\n## Ask / next step\n{next_action(r, idle)}"}
    return f"# {kind}: {r['name']}\n*Generated {date.today()}*\n\n{body[kind]}"
