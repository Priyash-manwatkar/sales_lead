import io
import json
import runpy
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import engine as E

st.set_page_config(page_title="SalesIQ", page_icon="📈", layout="wide")
db.init()
E.rescore_missing()
st.markdown("""<style>
.card{background:#fff;border:1px solid #e3e8ee;border-left:4px solid #0e7c86;border-radius:8px;padding:10px 14px;min-height:78px}
.card b{font-size:1.25rem;color:#0f2a3d;display:block}.card span{color:#6b7c8a;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em}
</style>""", unsafe_allow_html=True)
ICON = {"Company Added": "🏢", "Visit": "🤝", "Call": "📞", "Report": "📝", "Requirement": "📌",
        "Follow-up": "⏰", "Opportunity Change": "🔄", "Closed": "✅", "Lost": "❌"}
PURPOSES = ["Introduction", "Requirement discussion", "Product demo", "Price negotiation", "Relationship building", "Order follow-up"]
today = str(date.today())


def card(col, label, val):
    col.markdown(f"<div class='card'><span>{label}</span><b>{val}</b></div>", unsafe_allow_html=True)


def load():
    d = db.q("SELECT * FROM companies")
    d["expected"] = d.apply(lambda r: E.estimate(r)[0]["Expected"], axis=1)
    d["band"] = d.score.apply(E.band)
    return d


def pick(d, key):
    return d[d["name"] == st.selectbox("Company", d["name"], key=key)].iloc[0]


def events(cid):
    return db.q("SELECT * FROM events WHERE company_id=? ORDER BY dt, id", (int(cid),))


def is_due(d):
    return (d.next_followup != "") & (d.next_followup <= today)


# ---------------------------------------------------------------- Dashboard
def dashboard(d):
    st.title("Sales Intelligence Dashboard")
    a, b = st.columns(2)
    own = a.multiselect("Salesperson", sorted(d.owner.unique()), sorted(d.owner.unique()))
    ind = b.multiselect("Industry", sorted(d.industry.unique()), sorted(d.industry.unique()))
    d = d[d.owner.isin(own) & d.industry.isin(ind)]
    act = d[~d.stage.isin(["Won", "Lost"])]
    ev = db.q("SELECT * FROM events")
    ev = ev[ev.company_id.isin(d.id)]
    won, lost = (d.stage == "Won").sum(), (d.stage == "Lost").sum()
    kp = [("Companies", len(d)), ("New (30 days)", (d.created >= str(date.today() - timedelta(30))).sum()),
          ("Active opportunities", len(act)), ("Pipeline (expected)", E.money(act.expected.sum())),
          ("High-potential accounts", (d.score >= 70).sum()), ("Visits completed", (ev.kind == "Visit").sum()),
          ("Follow-ups due", is_due(act).sum()), ("Conversion rate", f"{won / max(won + lost, 1) * 100:.0f}%")]
    for row in (kp[:4], kp[4:]):
        for c, (l, v) in zip(st.columns(4), row):
            card(c, l, v)
        st.write("")
    c1, c2 = st.columns(2)
    fn = d.stage.value_counts().reindex(E.STAGES[:5]).fillna(0).reset_index()
    fn.columns = ["stage", "companies"]
    c1.plotly_chart(px.funnel(fn, x="companies", y="stage", title="Opportunity funnel", color_discrete_sequence=["#0e7c86"]), use_container_width=True)
    ib = act.groupby("industry").expected.sum().reset_index()
    c2.plotly_chart(px.bar(ib, x="industry", y="expected", title="Industry-wise pipeline (₹ lakh, expected)", color_discrete_sequence=["#0f2a3d"]), use_container_width=True)
    c3, c4 = st.columns(2)
    lr = d[d.stage == "Lost"].lost_reason.value_counts().reset_index()
    lr.columns = ["reason", "count"]
    c3.plotly_chart(px.bar(lr, x="count", y="reason", orientation="h", title="Lost opportunities: reasons", color_discrete_sequence=["#c2410c"]), use_container_width=True)
    top = act.nlargest(10, "expected")
    c4.plotly_chart(px.bar(top, x="expected", y="name", orientation="h", title="Revenue potential by company (top 10, ₹ lakh)", color_discrete_sequence=["#0e7c86"]), use_container_width=True)
    st.subheader("Salesperson performance")
    g = d.groupby("owner").agg(Companies=("id", "count"), Won=("stage", lambda s: (s == "Won").sum()),
                               Active=("stage", lambda s: (~s.isin(["Won", "Lost"])).sum()),
                               Pipeline_lakh=("expected", "sum"), Avg_score=("score", "mean")).round(1).reset_index()
    st.dataframe(g, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------- Quick view
def quick(d):
    st.title("Quick View")
    r = pick(d, "qv")
    ev = events(r.id)
    last = ev.iloc[-1]
    idle = (date.today() - date.fromisoformat(last["dt"])).days
    c = st.columns(4)
    card(c[0], "Opportunity score", f"{r.score:.0f} · {r.band}")
    card(c[1], "Potential value (expected)", E.money(r.expected))
    card(c[2], "Sales stage", r.stage)
    card(c[3], "Last interaction", f"{last.kind} · {last['dt']}")
    c = st.columns(3)
    card(c[0], "Customer requirement", E.txt(r.requirement) or "-")
    card(c[1], "Main objection", E.txt(r.objection) or "None")
    card(c[2], "Pending follow-up", E.txt(r.next_followup) or "Not set")
    st.write("")
    st.success("**Recommended next action:** " + E.next_action(r, idle))
    st.info(E.summary(r, last))


# ---------------------------------------------------------------- Companies
def companies(d):
    st.title("Company Management")
    t1, t2, t3 = st.tabs(["Edit board", "Add company", "Company profile"])
    with t1:
        s = st.text_input("Search by name, industry or city")
        f1, f2, f3 = st.columns(3)
        stg = f1.multiselect("Stage", E.STAGES)
        own = f2.multiselect("Owner", sorted(d.owner.unique()))
        ind = f3.multiselect("Industry", sorted(d.industry.unique()))
        v = d.copy()
        if s:
            v = v[v[["name", "industry", "city"]].apply(lambda c: c.str.contains(s, case=False)).any(axis=1)]
        if stg: v = v[v.stage.isin(stg)]
        if own: v = v[v.owner.isin(own)]
        if ind: v = v[v.industry.isin(ind)]
        show = ["id", "name", "industry", "city", "owner", "stage", "status", "next_followup", "score"]
        cfg = {"stage": st.column_config.SelectboxColumn(options=E.STAGES),
               "status": st.column_config.SelectboxColumn(options=["Active", "On hold", "Dormant"]),
               "score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d"),
               "next_followup": st.column_config.TextColumn("next_followup (YYYY-MM-DD)")}
        ed = st.data_editor(v[show], disabled=["id", "name", "industry", "city", "score"], column_config=cfg,
                            hide_index=True, use_container_width=True, key="board")
        if st.button("Save board edits"):
            for _, r in ed.iterrows():
                o = d[d.id == r.id].iloc[0]
                new = (r.stage, r.status, r.owner, r.next_followup)
                if new != (o.stage, o.status, o.owner, o.next_followup):
                    try:
                        if r.next_followup: date.fromisoformat(r.next_followup)
                    except ValueError:
                        st.error(f"{o['name']}: follow-up must be YYYY-MM-DD"); continue
                    db.run("UPDATE companies SET stage=?,status=?,owner=?,next_followup=? WHERE id=?", (*new, int(r.id)))
                    E.stage_change(int(r.id), o.stage, r.stage)
                    E.rescore(r.id)
            st.rerun()
        x = io.BytesIO()
        d[db.COLS].to_excel(x, index=False)
        e1, e2 = st.columns(2)
        e1.download_button("⬇ Export CSV", d[db.COLS].to_csv(index=False), "companies.csv")
        e2.download_button("⬇ Export Excel", x.getvalue(), "companies.xlsx")
        up = st.file_uploader("Import companies (CSV/Excel, 'name' column required)", type=["csv", "xlsx"])
        if up and st.button("Import"):
            try:
                df = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up)
                if "name" not in df: raise ValueError("Missing required column 'name'")
                for _, r in df.dropna(subset=["name"]).iterrows():
                    E.rescore(db.save_company(dict(r)))
                st.success(f"Imported {len(df)} rows"); st.rerun()
            except Exception as ex:
                st.error(f"Import failed: {ex}")
    with t2:
        add_tab(d)
    with t3:
        profile(d)


def add_tab(d):
    ss = st.session_state
    a, b, c = st.columns(3)
    name = a.text_input("Company name *", key="a_name")
    ind = b.selectbox("Industry", E.INDUSTRIES, key="a_ind")
    city = c.text_input("City", "Delhi", key="a_city")
    for k, v in dict(employees=100, revenue_cr=50.0, order_value_l=10.0, freq_per_yr=4, business_model="", products="",
                     requirement="", competitors="", geography="").items():
        ss.setdefault("a_" + k, v)
    if st.button("🔍 AI Company Intelligence"):
        if not name.strip():
            st.warning("Enter a company name first")
        else:
            en = E.enrich(name, ind, city)
            ss["a_est"] = list(en)
            for k, v in en.items(): ss["a_" + k] = v
    est = ss.get("a_est", [])
    if est:
        st.warning("🟠 Fields filled by AI are **estimates**, not verified facts. Confidence: " + E.CONFIDENCE)
    a, b, c = st.columns(3)
    emp = a.number_input("Employees", 0, key="a_employees", step=10)
    rev = b.number_input("Revenue (₹ Cr)", 0.0, key="a_revenue_cr")
    ov = c.number_input("Expected order value (₹ lakh)", 0.0, key="a_order_value_l")
    fq = a.number_input("Orders per year", 0, 100, key="a_freq_per_yr")
    sup = b.selectbox("Current supplier", list(E.SUP), key="a_sup")
    tl = c.selectbox("Buying timeline", list(E.TL), key="a_tl")
    mod, prod = st.text_input("Business model", key="a_business_model"), st.text_input("Products/services", key="a_products")
    req, comp = st.text_input("Potential requirement", key="a_requirement"), st.text_input("Competitors", key="a_competitors")
    geo = st.text_input("Geographic presence", key="a_geography")
    o1, o2, o3 = st.columns(3)
    owner = o1.selectbox("Owner", ["Rahul", "Priya", "Amit"], key="a_owner")
    fit = o2.slider("Product fit (1-5)", 1, 5, 3, key="a_fit")
    intent = o3.slider("Purchase intent (1-5)", 1, 5, 3, key="a_intent")
    if st.button("💾 Save company", type="primary"):
        if not name.strip(): st.error("Company name is required")
        elif (d["name"].str.lower() == name.strip().lower()).any(): st.error("A company with this name already exists")
        else:
            cid = db.save_company(dict(name=name.strip(), industry=ind, city=city, employees=emp, revenue_cr=rev,
                                       order_value_l=ov, freq_per_yr=fq, supplier=sup, timeline=tl, business_model=mod,
                                       products=prod, requirement=req, competitors=comp, geography=geo, owner=owner,
                                       fit=fit, intent=intent))
            db.run("UPDATE companies SET enriched=? WHERE id=?", (json.dumps(est), cid))
            E.rescore(cid)
            st.success("Company saved. Open the Company profile tab.")


def profile(d):
    r = pick(d, "pf")
    cid = int(r.id)
    est = json.loads(E.txt(r.enriched) or "[]")
    fields = ["industry", "city", "employees", "revenue_cr", "geography", "business_model", "products", "requirement", "competitors", "supplier"]
    tbl = pd.DataFrame([(k.replace("_", " ").title(), E.txt(r[k]), "🟠 AI estimate" if k in est else "🟢 Entered/verified") for k in fields],
                       columns=["Field", "Value", "Basis"])
    a, b = st.columns([3, 2])
    a.dataframe(tbl, hide_index=True, use_container_width=True)
    a.caption(E.strategic(r) + " · " + E.CONFIDENCE)
    n = len(events(cid))
    parts = E.score_parts(r, n)
    bd = pd.DataFrame({"factor": list(parts), "points": list(parts.values()), "max": [E.W[k] for k in parts]})
    b.metric("Opportunity score", f"{r.score:.0f}/100", f"{r.score - r.prev_score:+.0f} vs previous")
    b.plotly_chart(px.bar(bd, x="points", y="factor", orientation="h", title="Why this score (points vs max shown on hover)",
                          hover_data=["max"], color_discrete_sequence=["#0e7c86"], height=420), use_container_width=True)
    st.subheader("Opportunity potential")
    est_v, asm = E.estimate(r)
    for c, (k, v) in zip(st.columns(4), est_v.items()): card(c, k, E.money(v))
    st.caption("Assumptions: " + " · ".join(asm))
    st.subheader("Contacts / decision-makers")
    cs = db.q("SELECT name,role,phone,is_dm FROM contacts WHERE company_id=?", (cid,))
    st.dataframe(cs, hide_index=True, use_container_width=True)
    with st.form("ct", clear_on_submit=True):
        x = st.columns(4)
        cn, cr, cp, dm = x[0].text_input("Name"), x[1].text_input("Role"), x[2].text_input("Phone"), x[3].checkbox("Decision-maker")
        if st.form_submit_button("Add contact") and cn.strip():
            db.run("INSERT INTO contacts(company_id,name,role,phone,is_dm) VALUES(?,?,?,?,?)", (cid, cn, cr, cp, int(dm)))
            st.rerun()
    with st.expander("✏️ Edit company"):
        with st.form("edit"):
            a1, a2, a3 = st.columns(3)
            stage = a1.selectbox("Stage", E.STAGES, E.STAGES.index(r.stage))
            status = a2.selectbox("Status", ["Active", "On hold", "Dormant"])
            owner = a3.text_input("Owner", r.owner)
            emp, rev = a1.number_input("Employees", 0, value=int(E.num(r.employees))), a2.number_input("Revenue (₹ Cr)", 0.0, value=float(E.num(r.revenue_cr)))
            ov, fq = a3.number_input("Order value (₹ lakh)", 0.0, value=float(E.num(r.order_value_l))), a1.number_input("Orders/year", 0, 100, int(E.num(r.freq_per_yr)))
            sup, tl = a2.selectbox("Supplier", list(E.SUP), list(E.SUP).index(r.supplier) if r.supplier in E.SUP else 0), a3.selectbox("Timeline", list(E.TL), list(E.TL).index(r.timeline) if r.timeline in E.TL else 4)
            sl = st.columns(5)
            sc = [sl[i].slider(k, 1, 5, int(E.num(r[c], 3))) for i, (k, c) in enumerate([("Fit", "fit"), ("Intent", "intent"), ("DM access", "dm_access"), ("Relationship", "relationship"), ("Engagement", "engagement")])]
            req, obj = st.text_input("Requirement", E.txt(r.requirement)), st.text_input("Objection", E.txt(r.objection))
            nf, lr = st.text_input("Next follow-up (YYYY-MM-DD)", E.txt(r.next_followup)), st.text_input("Lost reason", E.txt(r.lost_reason))
            ver = st.multiselect("Mark as verified", est)
            if st.form_submit_button("Save changes"):
                try:
                    if nf: date.fromisoformat(nf)
                except ValueError:
                    st.error("Follow-up date must be YYYY-MM-DD"); st.stop()
                db.save_company(dict(stage=stage, status=status, owner=owner, employees=emp, revenue_cr=rev, order_value_l=ov,
                                     freq_per_yr=fq, supplier=sup, timeline=tl, fit=sc[0], intent=sc[1], dm_access=sc[2],
                                     relationship=sc[3], engagement=sc[4], requirement=req, objection=obj, next_followup=nf,
                                     lost_reason=lr), cid)
                db.run("UPDATE companies SET enriched=? WHERE id=?", (json.dumps([e for e in est if e not in ver]), cid))
                E.stage_change(cid, r.stage, stage); E.rescore(cid); st.rerun()
    st.subheader("Timeline")
    with st.form("act", clear_on_submit=True):
        x = st.columns([1, 3])
        k, note = x[0].selectbox("Log", ["Call", "Requirement", "Follow-up"]), x[1].text_input("Note")
        if st.form_submit_button("Add to timeline") and note.strip():
            db.log(cid, k, note); E.rescore(cid); st.rerun()
    for x in events(cid).itertuples():
        st.markdown(f"{ICON.get(x.kind, '•')} **{x.dt}** · {x.kind}: {x.title}")
        if x.detail and x.kind == "Report":
            with st.expander("View report"): st.markdown(x.detail)


# ---------------------------------------------------------------- Visit report
def visit(d):
    st.title("AI Visit Report")
    ss = st.session_state
    r = pick(d, "vc")
    with st.form("visit"):
        a, b = st.columns(2)
        dt, people = a.date_input("Visit date", date.today()), b.text_input("People met")
        purpose = st.selectbox("Purpose", PURPOSES)
        disc, req = st.text_area("Discussion points"), st.text_area("Customer requirements")
        obj, com, nxt = st.text_area("Objections / challenges"), st.text_area("Commitments"), st.text_area("Next steps")
        go = st.form_submit_button("✨ Generate AI Report")
    if go:
        if not (disc.strip() or req.strip()):
            st.warning("Add at least discussion points or requirements")
        else:
            ss["n"] = ss.get("n", 0) + 1
            ss["rep"] = (int(r.id), E.visit_report(dict(company=r["name"], dt=str(dt), people=people or "-", purpose=purpose,
                                                       disc=disc, req=req, obj=obj, com=com, nxt=nxt), r.score))
    if "rep" in ss and ss["rep"][0] == int(r.id):
        rep = ss["rep"][1]
        st.subheader("Generated report (edit before saving)")
        ed = {k: st.text_area(k, v if isinstance(v, str) else "\n".join(f"- {x}" for x in v), key=f"r{ss['n']}_{k}") for k, v in rep.items()}
        if st.button("💾 Save to company history", type="primary"):
            cid, fu = int(r.id), ed["Follow-up date"].strip()[:10]
            try: date.fromisoformat(fu)
            except ValueError: fu = E.txt(r.next_followup)
            db.log(cid, "Visit", f"{purpose} visit ({people or 'n/a'})", "", str(dt))
            db.log(cid, "Report", "Visit report saved", "\n\n".join(f"**{k}**\n{v}" for k, v in ed.items()), str(dt))
            if req.strip(): db.log(cid, "Requirement", req[:90], "", str(dt))
            db.run("UPDATE companies SET requirement=?, objection=?, next_followup=?, engagement=MIN(5,engagement+1) WHERE id=?",
                   (req.strip() or E.txt(r.requirement), obj.splitlines()[0] if obj.strip() else E.txt(r.objection), fu, cid))
            E.rescore(cid); del ss["rep"]
            st.success("Saved to timeline. Score and follow-up updated.")


# ---------------------------------------------------------------- AI reports
def reports(d):
    st.title("AI Reports")
    a, b = st.columns(2)
    r = d[d["name"] == a.selectbox("Company", d["name"], key="rc")].iloc[0]
    kind = b.selectbox("Report type", E.REPORTS)
    if st.button("Generate", type="primary"):
        ev = events(r.id)
        text = E.report(kind, r, db.q("SELECT * FROM contacts WHERE company_id=?", (int(r.id),)), ev, E.score_parts(r, len(ev)))
        st.session_state["out"] = E.ai("Polish this sales report for clarity; keep every fact, do not invent numbers:\n" + text, text)
    if "out" in st.session_state:
        st.markdown(st.session_state["out"])
        st.download_button("⬇ Download (.md)", st.session_state["out"], "report.md")


# ---------------------------------------------------------------- Follow-ups
def followups(d):
    st.title("Smart Follow-ups")
    act = d[~d.stage.isin(["Won", "Lost"])].copy()
    last = db.q("SELECT company_id, MAX(dt) dt FROM events GROUP BY company_id").set_index("company_id").dt
    act["idle_days"] = act.id.map(lambda i: (date.today() - date.fromisoformat(last.get(i, today))).days)
    x = st.slider("Flag accounts with no interaction for at least (days)", 7, 90, 30)
    act["recommended_action"] = act.apply(lambda r: E.next_action(r, r.idle_days), axis=1)
    act["score_change"] = act.score - act.prev_score
    sets = {"⏰ Due today": act[act.next_followup == today], "🔴 Overdue": act[(act.next_followup != "") & (act.next_followup < today)],
            f"💤 No interaction for {x}+ days": act[act.idle_days >= x],
            "⭐ High-score accounts needing attention": act[(act.score >= 70) & (act.idle_days >= 14)],
            "📈📉 Score movers (±5 or more)": act[act.score_change.abs() >= 5]}
    for t, v in sets.items():
        st.subheader(f"{t} ({len(v)})")
        if len(v):
            st.dataframe(v[["name", "owner", "stage", "score", "score_change", "next_followup", "idle_days", "recommended_action"]],
                         hide_index=True, use_container_width=True)


PAGES = {"📊 Dashboard": dashboard, "⚡ Quick View": quick, "🏢 Companies": companies, "📝 Visit Report": visit,
         "🤖 AI Reports": reports, "⏰ Follow-ups": followups}
page = st.sidebar.radio("SalesIQ", [*PAGES, "📥 CSV Lead Scorer (v1)"])
if page.startswith("📥"):
    st.set_page_config = lambda *a, **k: None  # v1 app calls it again
    runpy.run_path("lead_scorer_v1.py")
else:
    PAGES[page](load())
