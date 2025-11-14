# receiving_hospital_dashboard.py
# Streamlit MVP – Receiving Hospital Dashboard (synthetic data + live workflow + analytics)

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta
import time
import random
import uuid
import json
from statistics import median

# -------------------- Page Setup & Style --------------------
st.set_page_config(page_title="Receiving Hospital – AHECN MVP", layout="wide")

st.markdown("""
<style>
:root{
  --ok:#10b981; --warn:#f59e0b; --bad:#ef4444; --muted:#94a3b8; --card:#0f172a; --ink:#e2e8f0;
}
html, body, [class*="css"] { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial; }
.block-container{ padding-top:1rem; padding-bottom:2.5rem }
.card{ background:var(--card); border:1px solid #1f2937; border-radius:14px; padding:14px 16px; margin-bottom:12px; }
.kpi{ background:#0b1324; border:1px solid #1f2937; border-radius:12px; padding:12px 14px; }
.kpi .label{ color:var(--muted); font-size:.8rem; letter-spacing:.2px }
.kpi .value{ font-weight:700; font-size:1.4rem; color:var(--ink) }
.pill{ display:inline-flex; align-items:center; padding:.28rem .6rem; border-radius:999px; font-weight:700; font-size:.75rem; letter-spacing:.3px; margin-right:.35rem; }
.pill.red{ background:rgba(239,68,68,.15); color:#fecaca; border:1px solid rgba(239,68,68,.35)}
.pill.yellow{ background:rgba(245,158,11,.15); color:#fde68a; border:1px solid rgba(245,158,11,.35)}
.pill.green{ background:rgba(16,185,129,.15); color:#a7f3d0; border:1px solid rgba(16,185,129,.35)}
.badge{ display:inline-block; padding:.25rem .5rem; border-radius:8px; font-size:.72rem; color:#cbd5e1; background:#1f2937; margin-right:.35rem }
.soft{ border:none; height:1px; background:#1f2937; margin:8px 0 12px }
.small{ color:#94a3b8; font-size:.85rem }
.btnline > div > button{ width:100% }
.audit{ background:#1e293b; border-left:3px solid #8b5cf6; padding:6px 10px; border-radius:6px; margin:4px 0 }
</style>
""", unsafe_allow_html=True)

# -------------------- Utilities --------------------
def now_ts() -> float:
    return time.time()

def fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "—"

def triage_pill(color: str) -> str:
    c = (color or "").upper()
    cls = "red" if c=="RED" else "yellow" if c=="YELLOW" else "green"
    return f'<span class="pill {cls}">{c}</span>'

def minutes_between(t1, t2) -> float:
    if not t1 or not t2: return None
    return (t2 - t1) / 60.0

# -------------------- Synthetic Data --------------------
FACILITY_POOL = [
    "NEIGRIHMS", "Civil Hospital Shillong", "Nazareth Hospital",
    "Ganesh Das MCH", "Sohra Civil Hospital", "Shillong Polyclinic & Trauma"
]
COMPLAINTS = ["Maternal", "Trauma", "Stroke", "Cardiac", "Sepsis", "Other"]
AMB_TYPES = ["BLS", "ALS", "ALS + Vent", "Neonatal", "Other"]
PRIORITY = ["Routine", "Urgent", "STAT"]
TRIAGE = ["RED", "YELLOW", "GREEN"]
REJECT_REASONS = ["No ICU bed", "No specialist", "Equipment down", "Over capacity", "Outside scope", "Patient diverted"]

def seed_referrals_for_today(n=120, seed=2025):
    rng = random.Random(seed)
    today = datetime.now().date()
    start = datetime.combine(today, datetime.min.time()).timestamp()
    referrals = []

    for i in range(n):
        compl = rng.choices(COMPLAINTS, weights=[0.2,0.22,0.18,0.18,0.15,0.07])[0]
        tri = rng.choices(TRIAGE, weights=[0.34,0.44,0.22])[0]
        priority = rng.choices(PRIORITY, weights=[0.25,0.5,0.25])[0]
        amb = rng.choices(AMB_TYPES, weights=[0.45,0.32,0.15,0.03,0.05])[0]

        # timestamps spread across the day
        first_contact = start + rng.randint(0, 23*3600)
        decision_ts = first_contact + rng.randint(60, 25*60)
        dispatch_ts = decision_ts + rng.randint(2*60, 12*60)
        travel_min = rng.randint(8, 85)
        arrive_dest_ts = dispatch_ts + travel_min*60
        handover_ts = arrive_dest_ts + rng.randint(5*60, 35*60)

        status = rng.choices(
            ["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"],
            weights=[0.25,0.15,0.2,0.2,0.15,0.05]
        )[0]
        # enforce timestamp presence based on status
        times = {"first_contact_ts": first_contact, "decision_ts": decision_ts}
        if status in ["ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER"]:
            times["dispatch_ts"] = dispatch_ts
        if status in ["ENROUTE","ARRIVE_DEST","HANDOVER"]:
            times["enroute_ts"] = dispatch_ts + rng.randint(0, 3*60)
        if status in ["ARRIVE_DEST","HANDOVER"]:
            times["arrive_dest_ts"] = arrive_dest_ts
        if status in ["HANDOVER"]:
            times["handover_ts"] = handover_ts

        # pick receiving facility randomly (we’ll filter to the chosen one in UI)
        dest = rng.choice(FACILITY_POOL)

        # patient & referrer
        age = rng.randint(1, 85)
        sex = rng.choice(["Male","Female"])
        pid = f"PID-{rng.randint(100000,999999)}"
        ref_name = rng.choice(["Dr. Rai", "Dr. Khonglah", "ANM Pynsuk", "Dr. Sharma", "Dr. Singh"])
        ref_fac = rng.choice(["PHC Mawlai","CHC Smit","CHC Pynursla","District Hospital Shillong","PHC Nongpoh","CHC Jowai"])

        # ETA & transport
        eta_min = travel_min if status in ["ENROUTE","ARRIVE_DEST"] else rng.randint(10, 90)
        transport = {"priority": priority, "ambulance": amb, "eta_min": eta_min}

        # provisional diagnosis (simple seed)
        dx_label = {
            "Maternal":"Postpartum haemorrhage",
            "Trauma":"Head injury, possible SDH",
            "Stroke":"Acute ischemic stroke",
            "Cardiac":"Suspected STEMI",
            "Sepsis":"Sepsis, hypotension",
            "Other":"Acute respiratory failure"
        }[compl]
        pdx = {"code":"-", "label":dx_label, "case_type":compl}

        rec = dict(
            id=str(uuid.uuid4())[:8].upper(),
            patient={"name": f"Pt-{i:04d}", "age": age, "sex": sex, "id": pid},
            referrer={"name": ref_name, "facility": ref_fac, "role": rng.choice(["Doctor/Physician","ANM/ASHA/EMT"])},
            provisionalDx=pdx,
            triage={"complaint": compl, "decision":{"color":tri}, "hr": rng.randint(60,150),
                    "sbp": rng.randint(80,180), "rr": rng.randint(12,35),
                    "temp": round(rng.uniform(36.0,39.8),1), "spo2": rng.randint(86,99), "avpu": "A"},
            dest=dest,
            transport=transport,
            resuscitation=[],
            interventions=[],
            times=times,
            status=status,
            audit_log=[]
        )
        referrals.append(rec)

    return referrals

# -------------------- Session State --------------------
if "referrals_today" not in st.session_state:
    st.session_state.referrals_today = seed_referrals_for_today(n=140)

if "facilities" not in st.session_state:
    # For dashboard scope, we center on facilities in pool
    st.session_state.facilities = FACILITY_POOL.copy()

if "facility_meta" not in st.session_state:
    # minimal capacity meta per facility
    st.session_state.facility_meta = {
        f: {"ICU_open": random.randint(0,8), "acceptanceRate": round(random.uniform(0.65,0.92),2)}
        for f in st.session_state.facilities
    }

# -------------------- Sidebar Controls --------------------
st.sidebar.header("Receiving Hospital")
facility = st.sidebar.selectbox("Select facility (you are receiving for):", st.session_state.facilities, index=1)
meta = st.session_state.facility_meta.get(facility, {"ICU_open":0, "acceptanceRate":0.75})

icu_new = st.sidebar.number_input("ICU beds available (editable)", min_value=0, max_value=50, value=int(meta["ICU_open"]))
st.session_state.facility_meta[facility]["ICU_open"] = int(icu_new)

st.sidebar.caption("Tip: use the buttons below to refresh or regenerate the day’s synthetic load.")
c1, c2 = st.sidebar.columns(2)
if c1.button("Refresh data"):
    st.rerun()
if c2.button("New day load"):
    st.session_state.referrals_today = seed_referrals_for_today(n=140, seed=int(time.time()) % 10_000_000)
    st.rerun()

# -------------------- Data Views (Today + Facility) --------------------
today = datetime.now().date()
def is_today(ts):
    try:
        dt = datetime.fromtimestamp(ts).date()
        return dt == today
    except Exception:
        return False

# same-day referrals for selected facility (primary or included as destination)
ref_all = [r for r in st.session_state.referrals_today if r["dest"] == facility and is_today(r["times"].get("first_contact_ts", now_ts()))]

# -------------------- KPIs --------------------
total = len(ref_all)
awaiting = len([r for r in ref_all if r["status"] in ["PREALERT","ACCEPTED","ENROUTE"]])
enroute = len([r for r in ref_all if r["status"] == "ENROUTE"])
arrived = len([r for r in ref_all if r["status"] == "ARRIVE_DEST"])
handover = len([r for r in ref_all if r["status"] == "HANDOVER"])
rejected = len([r for r in ref_all if r["status"] == "REJECTED"])
accept_base = len([r for r in ref_all if r["status"] in ["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"]])
accept_rate = (100.0 * (accept_base - rejected) / accept_base) if accept_base else 0.0
eta_vals = [r["transport"].get("eta_min") for r in ref_all if r["status"] in ["ENROUTE","ARRIVE_DEST"] and r["transport"].get("eta_min") is not None]
avg_eta = round(sum(eta_vals)/len(eta_vals),1) if eta_vals else 0.0

st.title(f"Receiving Hospital Dashboard – {facility}")
k1,k2,k3,k4,k5,k6 = st.columns(6)
with k1: st.markdown(f'<div class="kpi"><div class="label">Referrals today</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
with k2: st.markdown(f'<div class="kpi"><div class="label">Awaiting/Active</div><div class="value">{awaiting}</div></div>', unsafe_allow_html=True)
with k3: st.markdown(f'<div class="kpi"><div class="label">En Route</div><div class="value">{enroute}</div></div>', unsafe_allow_html=True)
with k4: st.markdown(f'<div class="kpi"><div class="label">Arrived</div><div class="value">{arrived}</div></div>', unsafe_allow_html=True)
with k5: st.markdown(f'<div class="kpi"><div class="label">Acceptance Rate</div><div class="value">{accept_rate:.0f}%</div></div>', unsafe_allow_html=True)
with k6: st.markdown(f'<div class="kpi"><div class="label">ICU Beds Open</div><div class="value">{int(icu_new)}</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="soft" />', unsafe_allow_html=True)

# -------------------- Work Queue --------------------
st.subheader("Incoming Queue & Ongoing Receiving")
st.caption("Actions: Accept / Reject • Mark En Route / Arrived / Handover • Log vitals & interventions • Generate ISBAR")

# Define a consistent status flow
# PREALERT -> ACCEPTED -> ENROUTE -> ARRIVE_DEST -> HANDOVER
priority_rank = {"STAT":0, "Urgent":1, "Routine":2}
status_rank = {"PREALERT":0, "ACCEPTED":1, "ENROUTE":2, "ARRIVE_DEST":3, "HANDOVER":4, "REJECTED":5}

queue = sorted(
    [r for r in ref_all if r["status"] in ["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST"]],
    key=lambda x: (status_rank.get(x["status"],9), priority_rank.get(x["transport"].get("priority","Urgent"),1), -x["times"].get("decision_ts", 0))
)

if not queue:
    st.info("No active or awaiting referrals at this time.")
else:
    for r in queue:
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            header_l, header_r = st.columns([3, 2])
            with header_l:
                tri_html = triage_pill(r["triage"]["decision"]["color"])
                st.markdown(f"**{r['patient']['name']}**, {r['patient']['age']} {r['patient']['sex']} {tri_html}", unsafe_allow_html=True)
                st.caption(f"From **{r['referrer']['facility']}** (by {r['referrer']['name']} – {r['referrer']['role']})")
                st.caption(f"Dx: {r['provisionalDx'].get('label','—')}")
            with header_r:
                st.write(f"**Status:** {r['status']}")
                eta_txt = r['transport'].get('eta_min', '—')
                st.write(f"**ETA:** {eta_txt} min  •  **Amb:** {r['transport'].get('ambulance','—')}  •  **Priority:** {r['transport'].get('priority','Urgent')}")

            a1,a2,a3,a4,a5 = st.columns(5)
            # Accept
            if a1.button("Accept", key=f"acc_{r['id']}", use_container_width=True, disabled=r["status"] not in ["PREALERT","ACCEPTED"]):
                if r["status"] == "PREALERT":
                    r["status"] = "ACCEPTED"
                r["audit_log"].append({"ts": datetime.now().isoformat(), "action":"ACCEPTED"})
                st.rerun()

            # Mark En Route
            if a2.button("En Route", key=f"enr_{r['id']}", use_container_width=True, disabled=r["status"] not in ["PREALERT","ACCEPTED","ENROUTE"]):
                r["status"] = "ENROUTE"
                r["times"]["dispatch_ts"] = r["times"].get("dispatch_ts", now_ts())
                r["times"]["enroute_ts"] = now_ts()
                r["audit_log"].append({"ts": datetime.now().isoformat(), "action":"ENROUTE"})
                st.rerun()

            # Arrived
            if a3.button("Arrived", key=f"arr_{r['id']}", use_container_width=True, disabled=r["status"] not in ["ENROUTE","ARRIVE_DEST"]):
                r["status"] = "ARRIVE_DEST"
                r["times"]["arrive_dest_ts"] = now_ts()
                r["audit_log"].append({"ts": datetime.now().isoformat(), "action":"ARRIVE_DEST"})
                st.rerun()

            # Handover
            if a4.button("Handover", key=f"hov_{r['id']}", use_container_width=True, disabled=r["status"] not in ["ARRIVE_DEST"]):
                r["status"] = "HANDOVER"
                r["times"]["handover_ts"] = now_ts()
                r["audit_log"].append({"ts": datetime.now().isoformat(), "action":"HANDOVER"})
                st.rerun()

            # Reject
            rej_reason = a5.selectbox("Reject reason", ["—"] + REJECT_REASONS, key=f"rejrs_{r['id']}")
            if a5.button("Reject", key=f"rej_{r['id']}", use_container_width=True, disabled=rej_reason=="—"):
                r["status"] = "REJECTED"
                r["audit_log"].append({"ts": datetime.now().isoformat(), "action":"REJECTED", "reason": rej_reason})
                st.warning(f"Case rejected: {rej_reason}")
                st.rerun()

            st.markdown('<hr class="soft" />', unsafe_allow_html=True)

            # Details row
            d1, d2 = st.columns([2, 3])

            with d1:
                st.markdown("**Timeline**")
                tl = r["times"]
                st.write(f"- First contact: {fmt_ts(tl.get('first_contact_ts'))}")
                st.write(f"- Decision: {fmt_ts(tl.get('decision_ts'))}")
                st.write(f"- Dispatch: {fmt_ts(tl.get('dispatch_ts'))}")
                st.write(f"- En route: {fmt_ts(tl.get('enroute_ts'))}")
                st.write(f"- Arrive dest: {fmt_ts(tl.get('arrive_dest_ts'))}")
                st.write(f"- Handover: {fmt_ts(tl.get('handover_ts'))}")

                st.markdown("**Audit**")
                if r.get("audit_log"):
                    for a in r["audit_log"]:
                        txt = f"{a['ts']} • {a['action']}" + (f" • {a.get('reason','')}" if a.get("reason") else "")
                        st.markdown(f'<div class="audit">{txt}</div>', unsafe_allow_html=True)
                else:
                    st.caption("No audit entries yet.")

            with d2:
                # Live vitals entry + recent trend table
                st.markdown("**Vitals (latest & add)**")
                colv1, colv2, colv3 = st.columns(3)
                v_hr = colv1.number_input("HR", 0, 250, r['triage']['hr'], key=f"vhr_{r['id']}")
                v_sbp = colv2.number_input("SBP", 0, 300, r['triage']['sbp'], key=f"vsbp_{r['id']}")
                v_rr = colv3.number_input("RR", 0, 80, r['triage']['rr'], key=f"vrr_{r['id']}")
                colv4, colv5, colv6 = st.columns(3)
                v_spo2 = colv4.number_input("SpO₂", 50, 100, r['triage']['spo2'], key=f"vspo2_{r['id']}")
                v_temp = colv5.number_input("Temp °C", 30.0, 43.0, r['triage']['temp'], step=0.1, key=f"vtemp_{r['id']}")
                v_avpu = colv6.selectbox("AVPU", ["A", "V", "P", "U"], index=0, key=f"vavpu_{r['id']}")

                if st.button("➕ Add vitals", key=f"addv_{r['id']}"):
                    if "vitals_history" not in r: r["vitals_history"] = []
                    r["vitals_history"].append({
                        "timestamp": now_ts(), "hr": v_hr, "sbp": v_sbp, "rr": v_rr,
                        "spo2": v_spo2, "temp": v_temp, "avpu": v_avpu
                    })
                    st.success("Vitals recorded")
                    st.rerun()

                if r.get("vitals_history"):
                    vdf = pd.DataFrame(r["vitals_history"])
                    vdf["time"] = pd.to_datetime(vdf["timestamp"], unit="s").dt.strftime("%H:%M")
                    st.dataframe(vdf[["time","hr","sbp","rr","spo2","temp","avpu"]].tail(6), use_container_width=True, height=180)
                else:
                    st.caption("No vitals history yet.")

                st.markdown("**Interventions (quick)**")
                qcols = st.columns(6)
                quick_list = ["Oxygen","IV Access","IV Fluids","Uterotonics","TXA","Aspirin"]
                quick_sel = []
                for i, q in enumerate(quick_list):
                    if qcols[i].checkbox(q, key=f"iv_{r['id']}_{i}"): quick_sel.append(q)
                if st.button("💾 Save interventions", key=f"saveiv_{r['id']}"):
                    for name in quick_sel:
                        r["interventions"].append({"name": name, "type":"emt", "timestamp": now_ts(), "status":"completed"})
                    st.success(f"Saved {len(quick_sel)} interventions")
                    st.rerun()

                st.markdown("**ISBAR (auto)**")
                isbar = f"""I: {r['patient']['name']}, {r['patient']['age']}{r['patient']['sex']} • {r['id']}
S: {r['triage']['complaint']} • Triage {r['triage']['decision']['color']} • Priority {r['transport'].get('priority','Urgent')}
B: Referred from {r['referrer']['facility']} by {r['referrer']['name']} ({r['referrer']['role']}) • Dx: {r['provisionalDx'].get('label','—')}
A: Latest Vitals – HR {v_hr}, SBP {v_sbp}, RR {v_rr}, SpO2 {v_spo2}, Temp {v_temp}°C, AVPU {v_avpu}
R: {"Arrived" if r["status"] in ["ARRIVE_DEST","HANDOVER"] else "En route"} • Ambulance {r['transport'].get('ambulance','—')} • ETA {r['transport'].get('eta_min','—')} min
"""
                st.code(isbar, language="text")

            st.markdown('</div>', unsafe_allow_html=True)

# -------------------- Analytics (Today) --------------------
st.subheader("Today’s Analytics")
if not ref_all:
    st.info("No same-day data for this facility.")
else:
    # Build a dataframe for analysis
    def to_row(r):
        t = r["times"]
        return {
            "id": r["id"],
            "status": r["status"],
            "triage": r["triage"]["decision"]["color"],
            "case_type": r["triage"]["complaint"],
            "priority": r["transport"].get("priority","Urgent"),
            "ambulance": r["transport"].get("ambulance","—"),
            "eta_min": r["transport"].get("eta_min"),
            "first_contact": datetime.fromtimestamp(t.get("first_contact_ts", now_ts())),
            "decision_ts": t.get("decision_ts"),
            "dispatch_ts": t.get("dispatch_ts"),
            "arrive_dest_ts": t.get("arrive_dest_ts"),
            "handover_ts": t.get("handover_ts"),
            "decision_to_dispatch_min": minutes_between(t.get("decision_ts"), t.get("dispatch_ts")),
            "dispatch_to_arrival_min": minutes_between(t.get("dispatch_ts"), t.get("arrive_dest_ts")),
            "arrival_to_handover_min": minutes_between(t.get("arrive_dest_ts"), t.get("handover_ts")),
        }
    adf = pd.DataFrame([to_row(r) for r in ref_all])

    # KPIs row 2
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        x = adf["decision_to_dispatch_min"].dropna()
        st.markdown(f'<div class="kpi"><div class="label">Decision→Dispatch (median)</div><div class="value">{(median(x) if len(x)>0 else 0):.1f} min</div></div>', unsafe_allow_html=True)
    with c2:
        x = adf["dispatch_to_arrival_min"].dropna()
        st.markdown(f'<div class="kpi"><div class="label">Dispatch→Arrival (median)</div><div class="value">{(median(x) if len(x)>0 else 0):.1f} min</div></div>', unsafe_allow_html=True)
    with c3:
        x = adf["arrival_to_handover_min"].dropna()
        st.markdown(f'<div class="kpi"><div class="label">Arrival→Handover (median)</div><div class="value">{(median(x) if len(x)>0 else 0):.1f} min</div></div>', unsafe_allow_html=True)
    with c4:
        tri_counts = adf["triage"].value_counts(dropna=False).to_dict()
        red_share = (100.0 * tri_counts.get("RED",0) / len(adf)) if len(adf) else 0
        st.markdown(f'<div class="kpi"><div class="label">Critical Load (RED)</div><div class="value">{red_share:.0f}%</div></div>', unsafe_allow_html=True)

    st.markdown('<hr class="soft" />', unsafe_allow_html=True)
    arow1 = st.columns(2)
    with arow1[0]:
        st.markdown("**Triage Mix**")
        tri = adf.groupby("triage").size().reset_index(name="count")
        tri_chart = alt.Chart(tri).mark_arc(innerRadius=50).encode(
            theta="count:Q", color=alt.Color("triage:N", scale=alt.Scale(domain=["RED","YELLOW","GREEN"], range=["#ef4444","#f59e0b","#10b981"])),
            tooltip=["triage","count"]
        ).properties(height=320)
        st.altair_chart(tri_chart, use_container_width=True)

    with arow1[1]:
        st.markdown("**Case Types**")
        ctypes = adf.groupby("case_type").size().reset_index(name="count").sort_values("count", ascending=False)
        case_chart = alt.Chart(ctypes).mark_bar().encode(
            x=alt.X("count:Q", title="Cases"), y=alt.Y("case_type:N", sort="-x", title=""),
            tooltip=["case_type","count"]
        ).properties(height=320)
        st.altair_chart(case_chart, use_container_width=True)

    arow2 = st.columns(2)
    with arow2[0]:
        st.markdown("**Hourly Flow (first contact)**")
        hourly = adf.copy()
        hourly["hour"] = pd.to_datetime(hourly["first_contact"]).dt.hour
        h = hourly.groupby("hour").size().reset_index(name="count")
        hchart = alt.Chart(h).mark_bar().encode(
            x=alt.X("hour:O", title="Hour of Day"), y=alt.Y("count:Q", title="Referrals"),
            tooltip=["hour","count"]
        ).properties(height=300)
        st.altair_chart(hchart, use_container_width=True)

    with arow2[1]:
        st.markdown("**Transport Times by Ambulance Type**")
        tdf = adf[~adf["dispatch_to_arrival_min"].isna()]
        if not tdf.empty:
            box = alt.Chart(tdf).mark_boxplot().encode(
                x=alt.X("ambulance:N", title="Ambulance"), y=alt.Y("dispatch_to_arrival_min:Q", title="Minutes"),
                color="ambulance:N", tooltip=["ambulance","dispatch_to_arrival_min"]
            ).properties(height=300)
            st.altair_chart(box, use_container_width=True)
        else:
            st.caption("No complete dispatch→arrival intervals yet.")

    arow3 = st.columns(2)
    with arow3[0]:
        st.markdown("**Status Snapshot**")
        s = adf.groupby("status").size().reset_index(name="count")
        s_chart = alt.Chart(s).mark_bar().encode(
            x=alt.X("status:N", sort=["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"]),
            y="count:Q", tooltip=["status","count"]
        ).properties(height=300)
        st.altair_chart(s_chart, use_container_width=True)

    with arow3[1]:
        st.markdown("**Acceptance vs Rejection**")
        accept_rej = pd.DataFrame({
            "Outcome":["Accepted/Progressed","Rejected"],
            "Count":[int(accept_base - rejected), int(rejected)]
        })
        ar_chart = alt.Chart(accept_rej).mark_arc(innerRadius=50).encode(
            theta="Count:Q", color=alt.Color("Outcome:N", scale=alt.Scale(range=["#10b981","#ef4444"])),
            tooltip=["Outcome","Count"]
        ).properties(height=300)
        st.altair_chart(ar_chart, use_container_width=True)

    # Raw table (today)
    st.markdown("**Today’s Cases (table)**")
    show_cols = ["id","status","triage","case_type","priority","ambulance","eta_min","first_contact"]
    st.dataframe(adf[show_cols].sort_values("first_contact", ascending=False), use_container_width=True, height=280)

# -------------------- Exports --------------------
st.subheader("Exports")
colx1, colx2 = st.columns(2)
with colx1:
    if ref_all:
        csv_bytes = pd.DataFrame([{
            "id": r["id"], "status": r["status"],
            "triage": r["triage"]["decision"]["color"], "case_type": r["triage"]["complaint"],
            "priority": r["transport"].get("priority",""), "ambulance": r["transport"].get("ambulance",""),
            "eta_min": r["transport"].get("eta_min",""),
            "first_contact": fmt_ts(r["times"].get("first_contact_ts")), "decision": fmt_ts(r["times"].get("decision_ts")),
            "dispatch": fmt_ts(r["times"].get("dispatch_ts")), "arrival": fmt_ts(r["times"].get("arrive_dest_ts")),
            "handover": fmt_ts(r["times"].get("handover_ts")),
        } for r in ref_all]).to_csv(index=False).encode("utf-8")
    else:
        csv_bytes = "".encode("utf-8")
    st.download_button("⬇️ Download CSV (today @ facility)", data=csv_bytes, file_name="receiving_today.csv", mime="text/csv", disabled=(len(ref_all)==0))
with colx2:
    json_bytes = json.dumps(ref_all, indent=2).encode("utf-8") if ref_all else "".encode("utf-8")
    st.download_button("⬇️ Download JSON (today @ facility)", data=json_bytes, file_name="receiving_today.json", mime="application/json", disabled=(len(ref_all)==0))
