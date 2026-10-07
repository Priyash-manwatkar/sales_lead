import random
import sqlite3
from datetime import date, timedelta

import pandas as pd

DB = "crm.db"
TEXT = ["name", "industry", "city", "geography", "business_model", "products", "requirement", "competitors",
        "supplier", "stage", "status", "owner", "timeline", "next_followup", "lost_reason", "objection"]
NUM = ["employees", "revenue_cr", "order_value_l", "freq_per_yr", "fit", "intent", "dm_access", "relationship", "engagement"]
COLS = TEXT + NUM
DEF = dict(industry="Manufacturing", city="Delhi", geography="", business_model="", products="", requirement="",
           competitors="", supplier="None", stage="Lead", status="Active", owner="Unassigned", timeline="Unknown",
           next_followup="", lost_reason="", objection="", employees=100, revenue_cr=50.0, order_value_l=10.0,
           freq_per_yr=4, fit=3, intent=3, dm_access=3, relationship=2, engagement=2)


def _c():
    return sqlite3.connect(DB)


def q(sql, p=()):
    with _c() as c:
        return pd.read_sql_query(sql, c, params=p)


def run(sql, p=()):
    with _c() as c:
        return c.execute(sql, p).lastrowid


def clean(v):
    v = v.item() if hasattr(v, "item") else v
    return None if isinstance(v, float) and v != v else v


def log(cid, kind, title, detail="", dt=None):
    run("INSERT INTO events(company_id,dt,kind,title,detail) VALUES(?,?,?,?,?)",
        (int(cid), dt or str(date.today()), kind, title, detail))


def save_company(d, cid=None):
    d = {k: clean(v) for k, v in d.items() if k in COLS}
    if cid is None:
        ex = q("SELECT id FROM companies WHERE lower(name)=lower(?)", (d.get("name", ""),))
        cid = int(ex.id[0]) if len(ex) else None
        if cid is None:
            d = {**DEF, **{k: v for k, v in d.items() if v is not None}}
    if cid:
        run(f"UPDATE companies SET {','.join(k + '=?' for k in d)} WHERE id=?", (*d.values(), int(cid)))
        return int(cid)
    d["created"] = str(date.today())
    cid = run(f"INSERT INTO companies({','.join(d)}) VALUES({','.join('?' * len(d))})", tuple(d.values()))
    log(cid, "Company Added", d["name"], "Added to CRM")
    return cid


def init():
    cols = ",".join(f"{c} {'TEXT' if c in TEXT else 'REAL'}" for c in COLS)
    with _c() as c:
        c.executescript(f"""CREATE TABLE IF NOT EXISTS companies(id INTEGER PRIMARY KEY, {cols}, score REAL, prev_score REAL,
            enriched TEXT DEFAULT '[]', created TEXT);
            CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, company_id INT, name TEXT, role TEXT, phone TEXT, is_dm INT);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, company_id INT, dt TEXT, kind TEXT, title TEXT, detail TEXT);""")
    if len(q("SELECT id FROM companies")) == 0:
        seed()


def seed():
    R = random.Random(7)
    pre = ["Apex", "Nova", "Bharat", "Sunrise", "Vertex", "Orion", "Delta", "Zenith", "Prime", "Metro", "Astra", "Kiran"]
    suf = ["Industries", "Infra", "Steel", "Realty", "Power", "Logistics", "Retail", "Engineering"]
    inds = ["Manufacturing", "Construction", "Real Estate", "Energy", "Logistics", "Retail"]
    cities = ["Delhi", "Gurugram", "Noida", "Rohtak", "Jaipur", "Ludhiana", "Mumbai", "Pune", "Chennai"]
    reqs = ["Power cables for new plant", "Bulk wires for housing project", "Monthly panel wiring supply",
            "Switchgear and cable retrofit", "Annual rate contract for electricals"]
    objs = ["Price higher than current vendor", "Delivery lead time too long", "Wants credit terms", "Needs sample approval", ""]
    lost = ["Price", "Went with incumbent", "Timeline slipped", "No budget", "Quality concerns"]
    people = ["Aarav Sharma", "Neha Verma", "Rohan Gupta", "Priya Singh", "Vikram Mehta", "Anjali Reddy", "Karan Joshi", "Meera Nair"]
    roles = ["Procurement Head", "Plant Manager", "CEO", "Purchase Manager", "Project Head"]
    names = set()
    while len(names) < 26:
        names.add(f"{R.choice(pre)} {R.choice(suf)}")
    for nm in sorted(names):
        emp = int(R.lognormvariate(5.5, 1.0))
        stage = R.choices(["Lead", "Qualified", "Proposal", "Negotiation", "Won", "Lost"], [5, 5, 4, 3, 3, 3])[0]
        cid = save_company(dict(
            name=nm, industry=R.choice(inds), city=R.choice(cities), employees=max(20, min(emp, 4000)),
            revenue_cr=round(emp * R.uniform(0.1, 0.5), 1), requirement=R.choice(reqs), objection=R.choice(objs),
            supplier=R.choice(["None", "Local vendor", "Regional brand", "Major brand"]), stage=stage,
            owner=R.choice(["Rahul", "Priya", "Amit"]), order_value_l=round(R.uniform(3, 60), 1),
            freq_per_yr=R.choice([2, 4, 6, 12]), fit=R.randint(2, 5), intent=R.randint(1, 5),
            timeline=R.choice(["Immediate", "1-3 months", "3-6 months", "6+ months", "Unknown"]),
            dm_access=R.randint(1, 5), relationship=R.randint(1, 5), engagement=R.randint(1, 5),
            lost_reason=R.choice(lost) if stage == "Lost" else "",
            next_followup="" if stage in ("Won", "Lost") else str(date.today() + timedelta(days=R.randint(-6, 10)))))
        for _ in range(R.randint(1, 3)):
            role = R.choice(roles)
            run("INSERT INTO contacts(company_id,name,role,phone,is_dm) VALUES(?,?,?,?,?)",
                (cid, R.choice(people), role, f"98{R.randint(10000000, 99999999)}", int(role in ("CEO", "Procurement Head"))))
        for _ in range(R.randint(1, 5)):
            k = R.choice(["Visit", "Call", "Report", "Requirement"])
            log(cid, k, f"{k} logged", "", str(date.today() - timedelta(days=R.randint(1, 90))))
        if stage in ("Won", "Lost"):
            log(cid, "Closed" if stage == "Won" else "Lost", f"Deal {stage.lower()}", "", str(date.today() - timedelta(days=R.randint(1, 20))))
