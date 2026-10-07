import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="LeadIQ | Lead Prioritization", page_icon="🎯", layout="wide")

# ---------------- Scoring configuration (edit weights here) ----------------
MAX = {"Industry fit": 15, "Company size": 15, "Engagement": 20,
       "Past interactions": 15, "Purchase intent": 25, "Lead source": 10}
INDUSTRY = {"Manufacturing": 15, "Construction": 14, "Energy": 13, "Real Estate": 12,
            "Logistics": 11, "Retail": 9, "Healthcare": 8, "Hospitality": 6, "Education": 5}
SOURCE = {"Referral": 10, "Partner": 8, "Webinar": 7, "Website": 6,
          "Trade Show": 5, "LinkedIn": 4, "Cold List": 2}
TIMELINE = {"Immediate": 6, "1-3 months": 4, "3-6 months": 2, "Not sure": 0}
REQUIRED = ["lead_id", "company", "industry", "employees", "lead_source", "website_visits",
            "email_opens", "email_clicks", "pricing_page_visits", "past_meetings",
            "days_since_last_contact", "demo_requested", "budget_confirmed", "purchase_timeline"]
COLORS = {"High": "#16a34a", "Medium": "#f59e0b", "Low": "#94a3b8"}
YES = {"yes", "y", "1", "true"}


def components(r):
    size = 15 if r.employees >= 1000 else 12 if r.employees >= 200 else 8 if r.employees >= 50 else 4
    eng = (min(r.website_visits, 20) / 20 * 8 + min(r.email_opens, 10) / 10 * 4
           + min(r.email_clicks, 8) / 8 * 8)
    d = r.days_since_last_contact
    inter = min(r.past_meetings, 3) / 3 * 9 + (6 if d <= 7 else 4 if d <= 30 else 2 if d <= 90 else 0)
    intent = (8 * r.demo_requested + 7 * r.budget_confirmed
              + TIMELINE.get(r.purchase_timeline, 0) + min(r.pricing_page_visits, 4) / 4 * 4)
    return pd.Series({"Industry fit": INDUSTRY.get(r.industry, 6), "Company size": size,
                      "Engagement": round(eng, 1), "Past interactions": round(inter, 1),
                      "Purchase intent": round(intent, 1), "Lead source": SOURCE.get(r.lead_source, 3)})


def priority(s):
    return "High" if s >= 70 else "Medium" if s >= 40 else "Low"


def explain(r):
    strong = [f"{k} ({r[k]:.0f}/{v})" for k, v in MAX.items() if r[k] / v >= 0.7]
    weak = [f"{k} ({r[k]:.0f}/{v})" for k, v in MAX.items() if r[k] / v <= 0.3]
    facts = []
    if r.demo_requested: facts.append("requested a demo")
    if r.budget_confirmed: facts.append("budget confirmed")
    if r.purchase_timeline == "Immediate": facts.append("wants to buy immediately")
    if r.days_since_last_contact > 30: facts.append(f"no contact for {r.days_since_last_contact} days")
    txt = f"Score {r.score:.0f}. "
    if strong: txt += "Strengths: " + ", ".join(strong) + ". "
    if weak: txt += "Weak: " + ", ".join(weak) + ". "
    if facts: txt += "Signals: " + ", ".join(facts) + "."
    return txt


def action(r):
    if r.priority == "High":
        if r.days_since_last_contact > 14: return "Re-engage today: call + tailored proposal (lead is going cold)"
        if r.demo_requested: return "Schedule product demo within 24 hours"
        if r.budget_confirmed: return "Send proposal & pricing; involve decision-maker"
        return "Call within 24 hours to confirm budget and timeline"
    if r.priority == "Medium":
        if r["Purchase intent"] >= 12: return "Book a discovery call this week"
        if r["Engagement"] >= 10: return "Nurture: send case study and invite to webinar"
        return "Add to automated email sequence; review in 2 weeks"
    return "Deprioritize: remove from active list" if r.lead_source == "Cold List" else "Automated nurture only, no manual effort"


@st.cache_data
def score_leads(df):
    df = df.copy()
    for c in ["demo_requested", "budget_confirmed"]:
        df[c] = df[c].astype(str).str.strip().str.lower().isin(YES).astype(int)
    comp = df.apply(components, axis=1)
    df = pd.concat([df, comp], axis=1)
    df["score"] = comp.sum(axis=1).round(0)
    df["priority"] = df["score"].apply(priority)
    df["why"] = df.apply(explain, axis=1)
    df["next_action"] = df.apply(action, axis=1)
    return df


# ---------------- Sidebar ----------------
st.sidebar.title("🎯 LeadIQ")
up = st.sidebar.file_uploader("Upload leads CSV", type="csv")
raw = pd.read_csv(up) if up else pd.read_csv("sample_leads.csv")
st.sidebar.caption("Using uploaded file" if up else "Using built-in sample data")
missing = [c for c in REQUIRED if c not in raw.columns]
if missing:
    st.error(f"Missing columns: {', '.join(missing)}")
    st.stop()
df = score_leads(raw)
if "created_date" in df: df["created_date"] = pd.to_datetime(df["created_date"])

st.sidebar.subheader("Filters")
pri = st.sidebar.multiselect("Priority", ["High", "Medium", "Low"], ["High", "Medium", "Low"])
ind = st.sidebar.multiselect("Industry", sorted(df.industry.unique()), sorted(df.industry.unique()))
src = st.sidebar.multiselect("Lead source", sorted(df.lead_source.unique()), sorted(df.lead_source.unique()))
mins = st.sidebar.slider("Minutes per manual follow-up", 10, 90, 30)
f = df[df.priority.isin(pri) & df.industry.isin(ind) & df.lead_source.isin(src)]

# ---------------- Header & KPIs ----------------
st.title("Lead Prioritization & Sales Action Dashboard")
st.caption("Focus your team on the leads most likely to buy.")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total leads", len(f))
k2.metric("Average score", f"{f.score.mean():.0f}/100" if len(f) else "-")
k3.metric("High priority", f"{(f.priority == 'High').mean() * 100:.0f}%" if len(f) else "-")
k4.metric("Qualified (High+Medium)", f"{(f.priority != 'Low').mean() * 100:.0f}%" if len(f) else "-")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "📋 Action list", "🔍 Lead explainer", "📈 Impact"])

with tab1:
    c1, c2 = st.columns(2)
    dist = f.priority.value_counts().reindex(["High", "Medium", "Low"]).fillna(0).reset_index()
    dist.columns = ["priority", "count"]
    c1.plotly_chart(px.pie(dist, names="priority", values="count", hole=0.55, color="priority",
                           color_discrete_map=COLORS, title="Priority distribution"), use_container_width=True)
    c2.plotly_chart(px.histogram(f, x="score", nbins=20, color="priority", color_discrete_map=COLORS,
                                 title="Score distribution"), use_container_width=True)
    c3, c4 = st.columns(2)
    bs = f.groupby("lead_source").score.mean().sort_values().reset_index()
    c3.plotly_chart(px.bar(bs, x="score", y="lead_source", orientation="h",
                           title="Average score by lead source"), use_container_width=True)
    if "converted" in f and "created_date" in f:
        t = f.set_index("created_date").resample("MS").converted.mean().mul(100).reset_index()
        c4.plotly_chart(px.line(t, x="created_date", y="converted", markers=True,
                                title="Conversion trend (% by month created)"), use_container_width=True)
    else:
        bi = f.groupby("industry").score.mean().sort_values().reset_index()
        c4.plotly_chart(px.bar(bi, x="score", y="industry", orientation="h",
                               title="Average score by industry"), use_container_width=True)

with tab2:
    st.subheader("Who to contact next")
    cols = ["lead_id", "company", "industry", "score", "priority", "next_action", "why"]
    st.dataframe(f.sort_values("score", ascending=False)[cols], use_container_width=True, height=480,
                 column_config={"score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d")})
    st.download_button("⬇ Download scored leads", f.to_csv(index=False), "scored_leads.csv", "text/csv")

with tab3:
    if len(f):
        pick = st.selectbox("Choose a lead", f.sort_values("score", ascending=False).apply(
            lambda r: f"{r.lead_id} - {r.company}", axis=1))
        r = f[f.lead_id == pick.split(" - ")[0]].iloc[0]
        a, b = st.columns([1, 2])
        a.metric("Score", f"{r.score:.0f}/100", r.priority)
        a.info(f"**Next action:** {r.next_action}")
        b.plotly_chart(px.bar(pd.DataFrame({"Factor": list(MAX), "Points": [r[k] for k in MAX],
                                            "Max": list(MAX.values())}), x="Points", y="Factor", orientation="h",
                              range_x=[0, 25], title="Score breakdown"), use_container_width=True)
        st.write(r.why)

with tab4:
    st.subheader("Measured impact (vs. treating all leads equally)")
    n, hi, me = len(df), (df.priority == "High").sum(), (df.priority == "Medium").sum()
    base_h = n * mins / 60
    new_h = (hi + 0.5 * me) * mins / 60  # High = full effort, Medium = half (automation), Low = none
    i1, i2, i3 = st.columns(3)
    i1.metric("Baseline follow-up hours", f"{base_h:.0f}")
    i2.metric("With prioritization", f"{new_h:.0f}")
    i3.metric("Time saved", f"{base_h - new_h:.0f} hrs", f"{(base_h - new_h) / base_h * 100:.0f}%")
    if "converted" in df:
        worked = df[df.priority != "Low"]
        win_share = worked.converted.sum() / max(df.converted.sum(), 1) * 100
        j1, j2, j3 = st.columns(3)
        j1.metric("Baseline conversion", f"{df.converted.mean() * 100:.1f}%")
        j2.metric("Conversion of High+Medium", f"{worked.converted.mean() * 100:.1f}%")
        j3.metric("Wins captured by worked leads", f"{win_share:.0f}%",
                  f"from {len(worked) / n * 100:.0f}% of leads")
        by = df.groupby("priority").converted.mean().mul(100).reindex(["High", "Medium", "Low"]).reset_index()
        st.plotly_chart(px.bar(by, x="priority", y="converted", color="priority", color_discrete_map=COLORS,
                               title="Historical conversion rate (%) by priority: model validation"), use_container_width=True)
        eff0 = df.converted.sum() / base_h
        eff1 = worked.converted.sum() / new_h
        st.success(f"Follow-up efficiency: {eff0:.2f} → {eff1:.2f} conversions per effort-hour ({eff1 / eff0:.1f}x)")
    else:
        st.info("Add a 0/1 'converted' column to your CSV to see conversion validation and efficiency KPIs.")
