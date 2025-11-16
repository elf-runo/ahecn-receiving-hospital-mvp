# receiving_hospital_dashboard_plus.py
# Streamlit MVP – Receiving Hospital Dashboard
# Features: multi-day synthetic data, date-range & calendar analytics, notifications center, live workflow.

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import datetime, timedelta, date
import time
import random
import uuid
import json
from statistics import median
# ADDED: event bus
try:
    from storage import poll_events_since, publish_event  # publish_event optional here (we use poll)
except ImportError:
    # Fallback if storage module is not available
    def poll_events_since(*args, **kwargs): return []
    def publish_event(*args, **kwargs): return None

# -------------------- Constants (MOVE THIS SECTION UP) --------------------
FACILITY_POOL = [
    "NEIGRIHMS", "Civil Hospital Shillong", "Nazareth Hospital",
    "Ganesh Das MCH", "Sohra Civil Hospital", "Shillong Polyclinic & Trauma"
]
COMPLAINTS = ["Maternal", "Trauma", "Stroke", "Cardiac", "Sepsis", "Other"]
AMB_TYPES = ["BLS", "ALS", "ALS + Vent", "Neonatal", "Other"]
PRIORITY = ["Routine", "Urgent", "STAT"]
TRIAGE = ["RED", "YELLOW", "GREEN"]
REJECT_REASONS = ["No ICU bed", "No specialist", "Equipment down", "Over capacity", "Outside scope", "Patient diverted"]
# -------------------- Intervention Types --------------------
REFERRING_INTERVENTIONS = [
    "Oxygen therapy", "IV access established", "Fluid bolus", 
    "Medication administered", "Blood transfusion", "CPR initiated",
    "Defibrillation", "Intubation", "Chest tube insertion",
    "Splinting", "Wound care", "Medication: Analgesia",
    "Medication: Antibiotics", "Medication: Antihypertensive",
    "Medication: Anticonvulsant", "ECG performed", "Lab tests drawn"
]

EMT_INTERVENTIONS = [
    "O2 started", "IV access", "IV fluids", "Cardiac monitoring",
    "12-lead ECG", "Medication: Nitroglycerin", "Medication: Aspirin",
    "Medication: Albuterol", "Medication: Epinephrine",
    "CPR in progress", "Defibrillation", "Intubation",
    "CPAP/BiPAP", "C-spine immobilization", "Extrication",
    "Wound dressing", "Splinting", "Ventilator management",
    "Pulse ox monitoring", "Blood glucose check"
]

INTERVENTION_STATUS = ["Planned", "In Progress", "Completed", "Cancelled"]

# -------------------- Configuration Management (NOW THIS CAN USE FACILITY_POOL) --------------------
CONFIG = {
    "facilities": FACILITY_POOL,
    "sla_thresholds": {
        "decision_to_dispatch": 15,
        "dispatch_to_arrival": 60, 
        "arrival_to_handover": 30
    },
    "notifications": {
        "red_triage": True,
        "eta_alert": 15,
        "vitals_alert": True
    },
    "auto_refresh_interval": 5
}

# Load from YAML if available (future enhancement)
def load_config_from_yaml():
    """Load configuration from YAML file - placeholder for future"""
    try:
        import yaml
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)
    except ImportError:
        return CONFIG
    except FileNotFoundError:
        return CONFIG

# Uncomment to use YAML config:
# CONFIG = load_config_from_yaml()

# -------------------- Authentication --------------------
def check_authentication():
    """Simple authentication check - extend for production"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        show_login_screen()
        st.stop()

def show_login_screen():
    """Display login form"""
    st.title("🏥 AHECN Receiving Hospital Dashboard")
    st.markdown("---")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        username = col1.text_input("Username", placeholder="Enter your username")
        password = col2.text_input("Password", type="password", placeholder="Enter your password")
        role = st.selectbox("Role", ["Receiving Doctor", "Nurse", "Administrator", "EMT Coordinator"])
        
        if st.form_submit_button("🔐 Login"):
            # Simple demo authentication - replace with real auth
            if username and password:
                st.session_state.authenticated = True
                st.session_state.user_role = role
                st.session_state.username = username
                st.rerun()
            else:
                st.error("Please enter both username and password")

# Check authentication at app start
check_authentication()

# -------------------- Auto-save Function --------------------
def auto_save():
    """Simple auto-save to session state"""
    if "saved_data" not in st.session_state:
        st.session_state.saved_data = {}
    
    st.session_state.saved_data = {
        "referrals": st.session_state.referrals_all,
        "interventions": st.session_state.get("interventions", {}),
        "resources": st.session_state.get("resources", {}),
        "notifications": st.session_state.get("notifications", [])
    }
    
# -------------------- Page Setup & Style --------------------
st.set_page_config(page_title="Receiving Hospital – AHECN (Enhanced)", layout="wide")

st.markdown("""
<style>
:root{
  --ok:#10b981; --warn:#f59e0b; --bad:#ef4444; --muted:#94a3b8; --card:#0f172a; --ink:#e2e8f0;
}

/* Fix main container alignment */
.main .block-container {
  padding-top: 1rem;
  padding-bottom: 2.5rem;
  max-width: 100%;
}

/* Fix header alignment */
.headerbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin-bottom: 1.5rem;
}

.headerbar .left, .headerbar .right {
  display: flex;
  align-items: center;
}

/* Fix card content alignment */
.card {
  background: var(--card);
  border: 1px solid #1f2937;
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 16px;
}

/* Fix KPI alignment */
.kpi {
  background: #0b1324;
  border: 1px solid #1f2937;
  border-radius: 12px;
  padding: 14px 16px;
  text-align: center;
  height: 100%;
}

.kpi .label {
  color: var(--muted);
  font-size: 0.8rem;
  letter-spacing: 0.2px;
  margin-bottom: 0.5rem;
  display: block;
}

.kpi .value {
  font-weight: 700;
  font-size: 1.6rem;
  color: var(--ink);
  display: block;
  line-height: 1.2;
}

/* Fix button alignment in workflow */
.btnline > div {
  display: flex;
  gap: 8px;
}

.btnline > div > button {
  flex: 1;
  min-height: 36px;
}

/* Fix column alignment in workflow cards */
[data-testid="column"] {
  align-items: stretch;
}

/* Ensure proper spacing in workflow actions */
.stButton > button {
  width: 100%;
  margin: 2px 0;
}

/* Fix notification alignment */
.ntf {
  background: #111827;
  border: 1px solid #1f2937;
  border-radius: 10px;
  padding: 12px 14px;
  margin: 8px 0;
}

.ntf .title {
  font-weight: 700;
  margin-bottom: 4px;
}

.ntf .meta {
  color: #94a3b8;
  font-size: 0.78rem;
  margin-bottom: 6px;
}

/* Fix form controls alignment */
.stSelectbox, .stNumberInput, .stTextInput {
  margin-bottom: 8px;
}

/* Ensure charts are properly contained */
.js-plotly-plot, .plotly, .vega-embed {
  width: 100% !important;
}

/* Fix data table alignment */
.dataframe {
  width: 100%;
}

/* Fix the main title alignment */
h1, h2, h3 {
  margin-top: 0 !important;
  margin-bottom: 1rem !important;
}

/* Fix the workflow card header */
.streamlit-container {
  width: 100%;
}

/* Mobile responsiveness */
@media (max-width: 768px) {
  .headerbar {
    flex-direction: column;
    align-items: stretch;
    gap: 1rem;
  }
  
  .kpi {
    margin-bottom: 1rem;
  }
  
  .card {
    padding: 12px;
  }
  
  /* Stack columns on mobile */
  [data-testid="column"] {
    width: 100% !important;
  }
}
</style>
""", unsafe_allow_html=True)
# -------------------- Demo User Setup --------------------
if "user" not in st.session_state:
    st.session_state.user = {
        "name": "Dr. Demo User", 
        "role": "Emergency Physician",
        "facility": "NEIGRIHMS"
    }

# -------------------- Utilities --------------------
def now_ts() -> float: return time.time()
def fmt_ts(ts: float, short=False) -> str:
    if not ts: return "—"
    try: return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M" if not short else "%H:%M")
    except: return "—"
def triage_pill(color: str) -> str:
    c=(color or "").upper(); cls = "red" if c=="RED" else "yellow" if c=="YELLOW" else "green"
    return f'<span class="pill {cls}">{c}</span>'
def minutes_between(t1, t2): return None if not t1 or not t2 else (t2 - t1)/60.0
def within_date_range(ts: float, d0: date, d1: date) -> bool:
    try: d = datetime.fromtimestamp(ts).date(); return d0 <= d <= d1
    except: return False
# Error handling & validation
def validate_referral_data(referral):
    """Validate referral data structure"""
    required_fields = ["id", "patient", "status", "times"]
    for field in required_fields:
        if field not in referral:
            return False, f"Missing required field: {field}"
    
    # Validate timestamp formats
    try:
        for time_key, time_value in referral["times"].items():
            if time_value and time_value < 0:
                return False, f"Invalid timestamp: {time_key}"
    except (TypeError, KeyError):
        return False, "Invalid time structure"
    
    return True, "Valid"

def safe_date_conversion(ts):
    """Safely convert timestamp to date"""
    try:
        return datetime.fromtimestamp(ts).date()
    except (TypeError, ValueError, OSError):
        return None

def safe_get(obj, keys, default=None):
    """Safely get nested dictionary values"""
    try:
        for key in keys.split('.'):
            obj = obj[key]
        return obj
    except (KeyError, TypeError):
        return default
def add_intervention(case_id, intervention, details, interv_type):
    """Quick intervention tracking"""
    if "interventions" not in st.session_state:
        st.session_state.interventions = {}
    
    if case_id not in st.session_state.interventions:
        st.session_state.interventions[case_id] = []
    
    st.session_state.interventions[case_id].append({
        "intervention": intervention,
        "details": details, 
        "type": interv_type,
        "timestamp": time.time()
    })
    
    # Show success message
    st.success(f"Added: {intervention}")    
def auto_save():
    """Simple auto-save to session state"""
    # This ensures data persists during the session
    if "saved_data" not in st.session_state:
        st.session_state.saved_data = {}
    
    st.session_state.saved_data = {
        "referrals": st.session_state.referrals_all,
        "interventions": st.session_state.get("interventions", {}),
        "resources": st.session_state.get("resources", {}),
        "notifications": st.session_state.get("notifications", [])
    }

# Also add this initialization at the start of your session state
if "saved_data" in st.session_state:
    # Restore from saved data
    st.session_state.referrals_all = st.session_state.saved_data.get("referrals", [])
    st.session_state.interventions = st.session_state.saved_data.get("interventions", {})
    st.session_state.resources = st.session_state.saved_data.get("resources", {})
    st.session_state.notifications = st.session_state.saved_data.get("notifications", [])
else:
    # Initialize fresh
    st.session_state.interventions = {}
    st.session_state.resources = {
        "NEIGRIHMS": {"icu_beds": 12, "icu_available": 4},
        "Civil Hospital Shillong": {"icu_beds": 8, "icu_available": 2},
        "Nazareth Hospital": {"icu_beds": 6, "icu_available": 1},
        "Ganesh Das MCH": {"icu_beds": 10, "icu_available": 3},
        "Sohra Civil Hospital": {"icu_beds": 4, "icu_available": 2},
        "Shillong Polyclinic & Trauma": {"icu_beds": 8, "icu_available": 0}
    }    
def display_patient_details(patient):
    """Display comprehensive patient details in a structured format"""
    
    with st.container():
        st.markdown("---")
        
        # Header with critical info
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"### 🏥 {patient['patient']['name']}, {patient['patient']['age']} {patient['patient']['sex']}")
            st.markdown(f"**ID:** {patient['id']} | **Triage:** {patient['triage']['decision']['color']} | **Status:** {patient['status']}")
        
        with col2:
            st.markdown(f"**Priority:** {patient['transport']['priority']}")
            st.markdown(f"**Ambulance:** {patient['transport']['ambulance']}")
            st.markdown(f"**ETA:** {patient['transport'].get('eta_min', '—')} min")
        
        with col3:
            st.markdown(f"**Complaint:** {patient['triage']['complaint']}")
            st.markdown(f"**Referring:** {patient['referrer']['facility']}")
            st.markdown(f"**By:** {patient['referrer']['name']}")

        # Tabbed interface for different detail sections
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Clinical Overview", "💊 Interventions", "📈 Vitals Trend", "🕒 Timeline", "📋 ISBAR Report"])

        with tab1:
            display_clinical_overview(patient)
        
        with tab2:
            display_interventions(patient)
        
        with tab3:
            display_vitals_trend(patient)
        
        with tab4:
            display_timeline(patient)
        
        with tab5:
            display_isbar_report(patient)
# -------------------- Patient Detail Functions --------------------
def display_patient_details(patient):
    """Display comprehensive patient details in a structured format"""
    
    with st.container():
        st.markdown("---")
        
        # Header with critical info
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"### 🏥 {patient['patient']['name']}, {patient['patient']['age']} {patient['patient']['sex']}")
            st.markdown(f"**ID:** {patient['id']} | **Triage:** {patient['triage']['decision']['color']} | **Status:** {patient['status']}")
        
        with col2:
            st.markdown(f"**Priority:** {patient['transport']['priority']}")
            st.markdown(f"**Ambulance:** {patient['transport']['ambulance']}")
            st.markdown(f"**ETA:** {patient['transport'].get('eta_min', '—')} min")
        
        with col3:
            st.markdown(f"**Complaint:** {patient['triage']['complaint']}")
            st.markdown(f"**Referring:** {patient['referrer']['facility']}")
            st.markdown(f"**By:** {patient['referrer']['name']}")

        # Tabbed interface for different detail sections
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Clinical Overview", "💊 Interventions", "📈 Vitals Trend", "🕒 Timeline", "📋 ISBAR Report"])

        with tab1:
            display_clinical_overview(patient)
        
        with tab2:
            display_interventions(patient)
        
        with tab3:
            display_vitals_trend(patient)
        
        with tab4:
            display_timeline(patient)
        
        with tab5:
            display_isbar_report(patient)

def display_clinical_overview(patient):
    """Display clinical overview with current status and actions"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Current Vitals")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("HR", f"{patient['triage']['hr']} bpm")
        v2.metric("BP", f"{patient['triage']['sbp']} mmHg")
        v3.metric("SpO2", f"{patient['triage']['spo2']}%")
        v4.metric("Temp", f"{patient['triage']['temp']}°C")
        
        st.markdown("#### Clinical Actions")
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        
        if action_col1.button("✅ Accept", key=f"accept_{patient['id']}", use_container_width=True):
            patient["status"] = "ACCEPTED"
            auto_save()
            st.rerun()
            
        if action_col2.button("🚗 En Route", key=f"enroute_{patient['id']}", use_container_width=True):
            patient["status"] = "ENROUTE"
            auto_save()
            st.rerun()
            
        if action_col3.button("🏥 Arrived", key=f"arrived_{patient['id']}", use_container_width=True):
            patient["status"] = "ARRIVE_DEST"
            auto_save()
            st.rerun()
            
        if action_col4.button("👥 Handover", key=f"handover_{patient['id']}", use_container_width=True):
            patient["status"] = "HANDOVER"
            auto_save()
            st.rerun()

    with col2:
        st.markdown("#### Provisional Diagnosis")
        st.info(patient['provisionalDx'].get('label', 'No diagnosis provided'))
        
        st.markdown("#### Critical Alerts")
        # Check for critical values
        alerts = []
        if patient['triage']['hr'] > 130 or patient['triage']['hr'] < 50:
            alerts.append("🚨 Critical Heart Rate")
        if patient['triage']['sbp'] < 90:
            alerts.append("🚨 Hypotension")
        if patient['triage']['spo2'] < 92:
            alerts.append("🚨 Hypoxia")
        if patient['triage']['avpu'] != 'A':
            alerts.append("🚨 Altered Consciousness")
            
        if alerts:
            for alert in alerts:
                st.error(alert)
        else:
            st.success("✅ No critical alerts")
# -------------------- Patient Detail Functions --------------------
def display_patient_details(patient):
    """Display comprehensive patient details in a structured format"""
    
    with st.container():
        st.markdown("---")
        
        # Header with critical info
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"### 🏥 {patient['patient']['name']}, {patient['patient']['age']} {patient['patient']['sex']}")
            st.markdown(f"**ID:** {patient['id']} | **Triage:** {patient['triage']['decision']['color']} | **Status:** {patient['status']}")
        
        with col2:
            st.markdown(f"**Priority:** {patient['transport']['priority']}")
            st.markdown(f"**Ambulance:** {patient['transport']['ambulance']}")
            st.markdown(f"**ETA:** {patient['transport'].get('eta_min', '—')} min")
        
        with col3:
            st.markdown(f"**Complaint:** {patient['triage']['complaint']}")
            st.markdown(f"**Referring:** {patient['referrer']['facility']}")
            st.markdown(f"**By:** {patient['referrer']['name']}")

        # Tabbed interface for different detail sections
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Clinical Overview", "💊 Interventions", "📈 Vitals Trend", "🕒 Timeline", "📋 ISBAR Report"])

        with tab1:
            display_clinical_overview(patient)
        
        with tab2:
            display_interventions(patient)
        
        with tab3:
            display_vitals_trend(patient)
        
        with tab4:
            display_timeline(patient)
        
        with tab5:
            display_isbar_report(patient)

def display_clinical_overview(patient):
    """Display clinical overview with current status and actions"""
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### Current Vitals")
        v1, v2, v3, v4 = st.columns(4)
        v1.metric("HR", f"{patient['triage']['hr']} bpm")
        v2.metric("BP", f"{patient['triage']['sbp']} mmHg")
        v3.metric("SpO2", f"{patient['triage']['spo2']}%")
        v4.metric("Temp", f"{patient['triage']['temp']}°C")
        
        st.markdown("#### Clinical Actions")
        action_col1, action_col2, action_col3, action_col4 = st.columns(4)
        
        if action_col1.button("✅ Accept", key=f"accept_{patient['id']}", use_container_width=True):
            patient["status"] = "ACCEPTED"
            auto_save()
            st.rerun()
            
        if action_col2.button("🚗 En Route", key=f"enroute_{patient['id']}", use_container_width=True):
            patient["status"] = "ENROUTE"
            auto_save()
            st.rerun()
            
        if action_col3.button("🏥 Arrived", key=f"arrived_{patient['id']}", use_container_width=True):
            patient["status"] = "ARRIVE_DEST"
            auto_save()
            st.rerun()
            
        if action_col4.button("👥 Handover", key=f"handover_{patient['id']}", use_container_width=True):
            patient["status"] = "HANDOVER"
            auto_save()
            st.rerun()

    with col2:
        st.markdown("#### Provisional Diagnosis")
        st.info(patient['provisionalDx'].get('label', 'No diagnosis provided'))
        
        st.markdown("#### Critical Alerts")
        # Check for critical values
        alerts = []
        if patient['triage']['hr'] > 130 or patient['triage']['hr'] < 50:
            alerts.append("🚨 Critical Heart Rate")
        if patient['triage']['sbp'] < 90:
            alerts.append("🚨 Hypotension")
        if patient['triage']['spo2'] < 92:
            alerts.append("🚨 Hypoxia")
        if patient['triage']['avpu'] != 'A':
            alerts.append("🚨 Altered Consciousness")
            
        if alerts:
            for alert in alerts:
                st.error(alert)
        else:
            st.success("✅ No critical alerts")
def get_time_ago(timestamp):
    """Calculate how long ago an event occurred"""
    if not timestamp:
        return "—"
    
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return "Just now"
    elif diff < 3600:
        return f"{int(diff/60)} min ago"
    elif diff < 86400:
        return f"{int(diff/3600)} hours ago"
    else:
        return f"{int(diff/86400)} days ago"

def display_vitals_trend(patient):
    """Display vitals trend chart"""
    if patient.get("vitals_history"):
        vitals_df = pd.DataFrame(patient["vitals_history"])
        vitals_df["time"] = pd.to_datetime(vitals_df["timestamp"], unit='s').dt.strftime("%H:%M")
        
        st.line_chart(vitals_df.set_index("time")[["hr", "sbp", "spo2"]])
    else:
        st.info("No vitals history available")

def display_timeline(patient):
    """Display detailed timeline"""
    times = patient["times"]
    
    timeline_data = []
    for event, timestamp in times.items():
        if timestamp:
            timeline_data.append({
                "Event": event.replace("_ts", "").replace("_", " ").title(),
                "Timestamp": fmt_ts(timestamp),
                "Time Ago": get_time_ago(timestamp)
            })
    
    if timeline_data:
        st.table(pd.DataFrame(timeline_data))
    else:
        st.info("No timeline data available")

def display_isbar_report(patient):
    """Generate comprehensive ISBAR report"""
    isbar_report = f"""
**IDENTIFICATION**
- Patient: {patient['patient']['name']}, {patient['patient']['age']} {patient['patient']['sex']}
- ID: {patient['patient']['id']}
- Case ID: {patient['id']}

**SITUATION**
- Chief Complaint: {patient['triage']['complaint']}
- Triage Level: {patient['triage']['decision']['color']}
- Priority: {patient['transport']['priority']}
- Current Status: {patient['status']}

**BACKGROUND**
- Referring Facility: {patient['referrer']['facility']}
- Referring Clinician: {patient['referrer']['name']} ({patient['referrer']['role']})
- Provisional Diagnosis: {patient['provisionalDx'].get('label', 'Not specified')}

**ASSESSMENT**
- Latest Vitals: HR {patient['triage']['hr']}, BP {patient['triage']['sbp']}, 
  RR {patient['triage']['rr']}, SpO2 {patient['triage']['spo2']}%, Temp {patient['triage']['temp']}°C
- AVPU: {patient['triage']['avpu']}
- Ambulance: {patient['transport']['ambulance']}
- ETA: {patient['transport'].get('eta_min', '—')} minutes

**RECOMMENDATION**
- Handoff Priority: {'HIGH' if patient['triage']['decision']['color'] == 'RED' else 'MEDIUM'}
"""
    st.markdown(isbar_report)

# Add these placeholder functions for ISBAR report
def get_required_resources(patient):
    """Determine required resources based on patient condition"""
    if patient['triage']['decision']['color'] == 'RED':
        return "ICU bed, Cardiac monitor, Emergency team"
    elif patient['triage']['decision']['color'] == 'YELLOW':
        return "ED bed, Monitoring equipment"
    else:
        return "General ward bed"

def get_special_considerations(patient):
    """Get special considerations for handoff"""
    considerations = []
    if patient['triage']['complaint'] == 'Cardiac':
        considerations.append("Cardiac monitor required")
    if patient['triage']['complaint'] == 'Trauma':
        considerations.append("Trauma team alert")
    if patient['triage']['spo2'] < 92:
        considerations.append("Oxygen therapy needed")
    return ", ".join(considerations) if considerations else "Standard care"            
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

def _seed_one(rng: random.Random, day_epoch: float, dest: str):
    compl = rng.choices(COMPLAINTS, weights=[0.2,0.22,0.18,0.18,0.15,0.07])[0]
    tri = rng.choices(TRIAGE, weights=[0.34,0.44,0.22])[0]
    priority = rng.choices(PRIORITY, weights=[0.25,0.5,0.25])[0]
    amb = rng.choices(AMB_TYPES, weights=[0.45,0.32,0.15,0.03,0.05])[0]

    first_contact = day_epoch + rng.randint(0, 23*3600)
    decision_ts = first_contact + rng.randint(60, 25*60)
    dispatch_ts = decision_ts + rng.randint(2*60, 12*60)
    travel_min = rng.randint(8, 85)
    arrive_dest_ts = dispatch_ts + travel_min*60
    handover_ts = arrive_dest_ts + rng.randint(5*60, 35*60)

    status = rng.choices(
        ["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"],
        weights=[0.24,0.15,0.22,0.2,0.14,0.05]
    )[0]

    times = {"first_contact_ts": first_contact, "decision_ts": decision_ts}
    if status in ["ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER"]:
        times["dispatch_ts"] = dispatch_ts
    if status in ["ENROUTE","ARRIVE_DEST","HANDOVER"]:
        times["enroute_ts"] = dispatch_ts + rng.randint(0, 3*60)
    if status in ["ARRIVE_DEST","HANDOVER"]:
        times["arrive_dest_ts"] = arrive_dest_ts
    if status in ["HANDOVER"]:
        times["handover_ts"] = handover_ts

    age = rng.randint(1, 85)
    sex = rng.choice(["Male","Female"])
    pid = f"PID-{rng.randint(100000,999999)}"
    ref_name = rng.choice(["Dr. Rai", "Dr. Khonglah", "ANM Pynsuk", "Dr. Sharma", "Dr. Singh"])
    ref_fac = rng.choice(["PHC Mawlai","CHC Smit","CHC Pynursla","District Hospital Shillong","PHC Nongpoh","CHC Jowai"])
    eta_min = travel_min if status in ["ENROUTE","ARRIVE_DEST"] else rng.randint(10, 90)
    transport = {"priority": priority, "ambulance": amb, "eta_min": eta_min}
    dx_label = {
        "Maternal":"Postpartum haemorrhage",
        "Trauma":"Head injury, possible SDH",
        "Stroke":"Acute ischemic stroke",
        "Cardiac":"Suspected STEMI",
        "Sepsis":"Sepsis, hypotension",
        "Other":"Acute respiratory failure"
    }[compl]
    pdx = {"code":"-", "label":dx_label, "case_type":compl}

    return dict(
        id=str(uuid.uuid4())[:8].upper(),
        patient={"name": f"Pt-{rng.randint(0,9999):04d}", "age": age, "sex": sex, "id": pid},
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

def seed_referrals_range(days=60, seed=2025):
    rng = random.Random(seed)
    all_refs = []
    today = datetime.now().date()
    for i in range(days):
        d = today - timedelta(days=i)
        day_epoch = datetime.combine(d, datetime.min.time()).timestamp()
        # daily volume (random, slightly higher weekdays)
        weekday = d.weekday()
        base = rng.randint(90, 160) if weekday < 5 else rng.randint(60, 120)
        # distribute across facilities
        for dest in FACILITY_POOL:
            k = max(0, int(base * rng.uniform(0.12, 0.22)))  # ~12-22% share per facility
            for _ in range(k):
                all_refs.append(_seed_one(rng, day_epoch, dest))
    return all_refs

# -------------------- Session State --------------------
if "referrals_all" not in st.session_state:
    st.session_state.referrals_all = seed_referrals_range(days=60, seed=2025)

if "facilities" not in st.session_state:
    st.session_state.facilities = FACILITY_POOL

if "facility_meta" not in st.session_state:
    # Initialize ICU bed counts for each facility
    st.session_state.facility_meta = {}
    for facility in FACILITY_POOL:
        st.session_state.facility_meta[facility] = {"ICU_open": random.randint(5, 20)}

if "notifications" not in st.session_state: 
    st.session_state.notifications = []
if "show_notifs" not in st.session_state: 
    st.session_state.show_notifs = False
if "notify_rules" not in st.session_state:
    st.session_state.notify_rules = {"RED_only": True, "eta_soon": True, "rejections": True}
if "resources" not in st.session_state:
    st.session_state.resources = {
        "NEIGRIHMS": {"icu_beds": 12, "icu_available": 4},
        "Civil Hospital Shillong": {"icu_beds": 8, "icu_available": 2},
        "Nazareth Hospital": {"icu_beds": 6, "icu_available": 1},
        "Ganesh Das MCH": {"icu_beds": 10, "icu_available": 3},
        "Sohra Civil Hospital": {"icu_beds": 4, "icu_available": 2},
        "Shillong Polyclinic & Trauma": {"icu_beds": 8, "icu_available": 0}
    }
# ADDED: keep per-case event watermark + live buffer + which case is open
if "last_event_id" not in st.session_state: 
    st.session_state.last_event_id = {}          # {case_id: last_id}
if "live_feed" not in st.session_state: 
    st.session_state.live_feed = {}                  # {case_id: [events]}
if "open_case_id" not in st.session_state: 
    st.session_state.open_case_id = None         # case subscribing
if "vitals_buffer" not in st.session_state: 
    st.session_state.vitals_buffer = {}         # {case_id: [dict]}
if "interventions_buffer" not in st.session_state: 
    st.session_state.interventions_buffer = {}  # {case_id: [dict]}
if "referring_interventions" not in st.session_state:
    st.session_state.referring_interventions = {}  # {case_id: [interventions]}
    
if "emt_interventions" not in st.session_state:
    st.session_state.emt_interventions = {}  # {case_id: [interventions]}
    
def push_notification(title: str, body: str, case_id: str = None, urgency: str = "medium"):
    """Enhanced notifications with urgency levels"""
    icon = "🔴" if urgency == "high" else "🟡" if urgency == "medium" else "🔵"
    
    if "notifications" not in st.session_state:
        st.session_state.notifications = []
    
    st.session_state.notifications.insert(0, {
        "id": str(uuid.uuid4())[:8],
        "ts": now_ts(),
        "title": f"{icon} {title}",
        "body": body,
        "case_id": case_id,
        "read": False,
        "urgency": urgency
    })
    
    # Show toast for high urgency
    if urgency == "high":
        st.toast(f"{icon} {title}: {body}", icon="🚨")

def unread_count():
    return sum(1 for n in st.session_state.notifications if not n["read"])

# Data persistence functions
def load_persistent_data():
    """Load data from JSON file for persistence"""
    try:
        with open("referrals_data.json", "r") as f:
            st.session_state.referrals_all = json.load(f)
        st.success("✅ Loaded existing data")
    except FileNotFoundError:
        st.session_state.referrals_all = seed_referrals_range(days=60, seed=2025)
        st.info("📊 Created new synthetic data")
    
    st.session_state.data_loaded = True

def save_data():
    """Save data to JSON file"""
    try:
        with open("referrals_data.json", "w") as f:
            json.dump(st.session_state.referrals_all, f, indent=2)
        return True
    except Exception as e:
        st.error(f"❌ Failed to save data: {e}")
        return False

# Initialize data if not loaded
if "data_loaded" not in st.session_state or not st.session_state.data_loaded:
    load_persistent_data()
    
# -------------------- Sidebar Controls --------------------
st.sidebar.header("Receiving Hospital")

# Display user info
st.sidebar.markdown(f"**👤 {st.session_state.user['name']}**")
st.sidebar.markdown(f"*{st.session_state.user['role']}*")
st.sidebar.markdown(f"🏥 {st.session_state.user['facility']}")
st.sidebar.markdown("---")

facility = st.sidebar.selectbox("You are receiving for:", st.session_state.get("facilities", ["NEIGRIHMS"]), index=0)

# Date range controls
default_end = datetime.now().date()
default_start = default_end - timedelta(days=6)
date_range = st.sidebar.date_input("Pick range", (default_start, default_end))
if isinstance(date_range, tuple) and len(date_range) == 2:
    d0, d1 = date_range
else:
    d0, d1 = default_start, default_end

# Notification rules
st.sidebar.subheader("Notification Rules")
st.session_state.notify_rules["RED_only"] = st.sidebar.checkbox("RED triage alerts", value=True)
st.session_state.notify_rules["eta_soon"] = st.sidebar.checkbox("ETA <15min alerts", value=True)
st.session_state.notify_rules["rejections"] = st.sidebar.checkbox("Rejection alerts", value=True)

# Auto-refresh
st.session_state.auto_refresh = st.sidebar.checkbox("Auto-refresh live feed (every 3s)", value=True)

# === DEMO DATA GENERATOR ===
st.sidebar.markdown("---")
st.sidebar.markdown("**🎬 Demo Tools**")

# FIXED: Added unique key
if st.sidebar.button("Load Demo Scenario", key="load_demo_scenario_unique"):
    # Clear existing data
    st.session_state.referrals_all = []
    
    # Create realistic demo cases
    demo_cases = []
    
    # Critical case
    demo_cases.append({
        "id": "DEMO-1001",
        "patient": {"name": "Pt-0423", "age": 68, "sex": "Male"},
        "referrer": {"name": "Dr. Sharma", "facility": "CHC Mawlai", "role": "Doctor"},
        "triage": {"complaint": "Cardiac", "decision": {"color": "RED"}, "hr": 135, "sbp": 85, "rr": 22, "spo2": 89, "temp": 36.8, "avpu": "A"},
        "transport": {"priority": "STAT", "ambulance": "ALS", "eta_min": 15},
        "status": "ENROUTE",
        "times": {"first_contact_ts": time.time() - 1800},
        "provisionalDx": {"label": "STEMI, critical condition"}
    })
    
    # Urgent case
    demo_cases.append({
        "id": "DEMO-1002", 
        "patient": {"name": "Pt-0157", "age": 34, "sex": "Female"},
        "referrer": {"name": "ANM Priya", "facility": "PHC Nongpoh", "role": "ANM"},
        "triage": {"complaint": "Maternal", "decision": {"color": "RED"}, "hr": 120, "sbp": 95, "rr": 24, "spo2": 94, "temp": 37.2, "avpu": "A"},
        "transport": {"priority": "Urgent", "ambulance": "ALS", "eta_min": 25},
        "status": "ACCEPTED", 
        "times": {"first_contact_ts": time.time() - 3600},
        "provisionalDx": {"label": "Postpartum hemorrhage"}
    })
    
    # Stable case
    demo_cases.append({
        "id": "DEMO-1003",
        "patient": {"name": "Pt-0891", "age": 45, "sex": "Male"}, 
        "referrer": {"name": "Dr. Singh", "facility": "CHC Jowai", "role": "Doctor"},
        "triage": {"complaint": "Trauma", "decision": {"color": "YELLOW"}, "hr": 88, "sbp": 130, "rr": 18, "spo2": 98, "temp": 36.5, "avpu": "A"},
        "transport": {"priority": "Urgent", "ambulance": "BLS", "eta_min": 40},
        "status": "ENROUTE",
        "times": {"first_contact_ts": time.time() - 2700},
        "provisionalDx": {"label": "Head injury, stable"}
    })
    
    st.session_state.referrals_all = demo_cases
    st.sidebar.success("🎯 Demo scenario loaded! 3 cases added.")
    st.rerun()

# Debug utilities
DEBUG = st.sidebar.checkbox("🔧 Debug Mode", value=False, key="debug_mode_checkbox")

if DEBUG:
    st.sidebar.markdown("### Debug Tools")
    if st.sidebar.button("Reset Data", key="reset_data_unique"):
        st.session_state.referrals_all = seed_referrals_range(days=60, seed=2025)
        st.session_state.data_loaded = True
        st.sidebar.success("Data reset complete")
    
    if st.sidebar.button("Save Data", key="save_data_unique"):
        if save_data():
            st.sidebar.success("Data saved successfully")
    
    if st.sidebar.button("Generate Test Alert", key="test_alert_unique"):
        push_notification("Test Notification", "This is a test notification", "TEST-001", "low")
        st.sidebar.success("Test notification sent")
# -------------------- Intervention Tracking Functions --------------------
def add_referring_intervention(case_id, intervention, details, timestamp=None):
    """Add a referring institution intervention"""
    if case_id not in st.session_state.referring_interventions:
        st.session_state.referring_interventions[case_id] = []
    
    intervention_record = {
        "id": str(uuid.uuid4())[:8],
        "intervention": intervention,
        "details": details,
        "timestamp": timestamp or now_ts(),
        "type": "referring",
        "status": "Completed"
    }
    
    st.session_state.referring_interventions[case_id].append(intervention_record)
    
    # Also add to case audit log
    case = next((r for r in st.session_state.referrals_all if r["id"] == case_id), None)
    if case:
        case["audit_log"].append({
            "ts": datetime.now().isoformat(),
            "action": "REFERRING_INTERVENTION",
            "intervention": intervention,
            "details": details
        })
    
    return intervention_record

def add_emt_intervention(case_id, intervention, details, status="Completed", timestamp=None):
    """Add an EMT intervention during transit"""
    if case_id not in st.session_state.emt_interventions:
        st.session_state.emt_interventions[case_id] = []
    
    intervention_record = {
        "id": str(uuid.uuid4())[:8],
        "intervention": intervention,
        "details": details,
        "timestamp": timestamp or now_ts(),
        "type": "emt",
        "status": status
    }
    
    st.session_state.emt_interventions[case_id].append(intervention_record)
    
    # Publish event for real-time updates
    try:
        publish_event("intervention.added", case_id, actor="emt", payload={
            "name": intervention,
            "details": details,
            "status": status
        })
    except:
        pass  # Silently fail if storage not available
    
    return intervention_record

def get_all_interventions(case_id):
    """Get all interventions for a case, sorted by timestamp"""
    referring = st.session_state.referring_interventions.get(case_id, [])
    emt = st.session_state.emt_interventions.get(case_id, [])
    
    all_interventions = referring + emt
    return sorted(all_interventions, key=lambda x: x["timestamp"], reverse=True)
    
# -------------------- Enhanced Real-time Features --------------------
def setup_real_time_listener():
    """Set up real-time event listening"""
    if "last_poll_time" not in st.session_state:
        st.session_state.last_poll_time = now_ts()
    
    # Get auto-refresh setting from session state or sidebar
    auto_refresh = st.session_state.get('auto_refresh', False)
    
    # Poll for new events every 5 seconds if auto-refresh is enabled
    if auto_refresh and (now_ts() - st.session_state.last_poll_time > 5):
        check_for_new_events()
        st.session_state.last_poll_time = now_ts()

def check_for_new_events():
    """Check for new system-wide events"""
    try:
        new_events = poll_events_since(st.session_state.get("system_last_event_id", 0))
        if new_events:
            st.session_state.system_last_event_id = max(e["id"] for e in new_events)
            for event in new_events:
                handle_system_event(event)
    except Exception as e:
        # Silently fail for now to avoid breaking the app
        pass

def handle_system_event(event):
    """Handle system-wide events"""
    event_type = event.get("type", "")
    case_id = event.get("case_id", "")
    
    if event_type == "system.alert":
        push_notification("SYSTEM_ALERT", event.get("title", "System Alert"), 
                         event.get("message", ""), case_id, "warning")

# Setup real-time listener in main flow
setup_real_time_listener()        
# -------------------- Filtered dataset --------------------
refs = [r for r in st.session_state.referrals_all if r["dest"] == facility and within_date_range(r["times"].get("first_contact_ts", now_ts()), d0, d1)]

# -------------------- Header with Notifications --------------------
left, right = st.columns([6, 2])
with left:
    st.markdown(f'<div class="headerbar"><div class="left"><h2>Receiving Hospital Dashboard – {facility}</h2></div></div>', unsafe_allow_html=True)
with right:
    n_unread = unread_count()
    bell_label = f"🔔 Notifications ({n_unread})" if n_unread else "🔔 Notifications"
    if st.button(bell_label, use_container_width=True):
        st.session_state.show_notifs = not st.session_state.show_notifs

if st.session_state.show_notifs:
    st.markdown("#### Notifications Center")
    colN1, colN2, colN3 = st.columns([1, 1, 2])
    with colN1:
        if st.button("Mark all read"):
            for n in st.session_state.notifications:
                n["read"] = True
            auto_save()    
            st.rerun()
    with colN2:
        if st.button("Clear all"):
            st.session_state.notifications = []
            auto_save() 
            st.rerun()
    with colN3:
        st.caption("System generates notifications on accepted RED cases, ETA soon, and rejections (configurable in sidebar).")

    # Filter controls
    fcol1, fcol2 = st.columns([1, 3])
    with fcol1:
        show_unread_only = st.checkbox("Unread only", value=False)
    with fcol2:
        kind_filter = st.multiselect("Types", ["RED_PREALERT","ETA_SOON","REJECTED","STATUS"], default=[])

    for n in st.session_state.notifications:
        if show_unread_only and n["read"]: 
            continue
        if kind_filter and n["kind"] not in kind_filter:
            continue
        classes = "ntf unread" if not n["read"] else "ntf"
        t = fmt_ts(n["ts"], short=True)
        st.markdown(f"""
        <div class="{classes}">
            <div class="title">{n['title']}</div>
            <div class="meta">{t} • {n['kind']} • Ref: {n.get('ref_id','—')}</div>
            <div class="body small">{n['body']}</div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('<hr class="soft" />', unsafe_allow_html=True)
# -------------------- Performance Optimizations --------------------
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_analytics_data(_adf, d0, d1):
    """Cache expensive analytics calculations"""
    if _adf.empty:
        return {}
    
    # Calculate metrics (this is computationally expensive)
    accept_base = len(_adf[_adf["status"].isin(["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"])])
    rejected = len(_adf[_adf["status"]=="REJECTED"])
    accept_rate = (100.0 * (accept_base - rejected) / accept_base) if accept_base else 0.0
    
    metrics = {
        "total": len(_adf),
        "awaiting": len(_adf[_adf["status"].isin(["PREALERT","ACCEPTED","ENROUTE"])]),
        "enroute": len(_adf[_adf["status"]=="ENROUTE"]),
        "arrived": len(_adf[_adf["status"]=="ARRIVE_DEST"]),
        "handover": len(_adf[_adf["status"]=="HANDOVER"]),
        "rejected": rejected,
        "accept_rate": accept_rate,
        "median_times": calculate_median_times(_adf)
    }
    
    return metrics

def calculate_median_times(df):
    """Calculate median times for SLAs"""
    dd = df["decision_to_dispatch_min"].dropna()
    da = df["dispatch_to_arrival_min"].dropna()
    ah = df["arrival_to_handover_min"].dropna()
    
    return {
        "decision_to_dispatch": median(dd) if not dd.empty else 0,
        "dispatch_to_arrival": median(da) if not da.empty else 0,
        "arrival_to_handover": median(ah) if not ah.empty else 0
    }
# -------------------- KPIs (range) --------------------
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

adf = pd.DataFrame([to_row(r) for r in refs])

# Use cached analytics data for better performance
analytics_data = get_analytics_data(adf, d0, d1)

total = analytics_data.get("total", 0)
awaiting = analytics_data.get("awaiting", 0)
enroute = analytics_data.get("enroute", 0)
arrived = analytics_data.get("arrived", 0)
handover = analytics_data.get("handover", 0)
rejected = analytics_data.get("rejected", 0)
accept_rate = analytics_data.get("accept_rate", 0.0)

# Get ICU beds for current facility
icu_available = st.session_state.resources[facility]["icu_available"]
icu_total = st.session_state.resources[facility]["icu_beds"]

k1,k2,k3,k4,k5,k6 = st.columns(6)
with k1: st.markdown(f'<div class="kpi"><div class="label">Referrals (range)</div><div class="value">{total}</div></div>', unsafe_allow_html=True)
with k2: st.markdown(f'<div class="kpi"><div class="label">Awaiting/Active</div><div class="value">{awaiting}</div></div>', unsafe_allow_html=True)
with k3: st.markdown(f'<div class="kpi"><div class="label">En Route</div><div class="value">{enroute}</div></div>', unsafe_allow_html=True)
with k4: st.markdown(f'<div class="kpi"><div class="label">Arrived</div><div class="value">{arrived}</div></div>', unsafe_allow_html=True)
with k5: st.markdown(f'<div class="kpi"><div class="label">Acceptance Rate</div><div class="value">{accept_rate:.0f}%</div></div>', unsafe_allow_html=True)
with k6: st.markdown(f'<div class="kpi"><div class="label">ICU Beds Available</div><div class="value {"red-text" if icu_available == 0 else "yellow-text" if icu_available < 3 else ""}">{icu_available}/{icu_total}</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="soft" />', unsafe_allow_html=True)

# -------------------- Professional Patient Dashboard --------------------

# Define today_refs for the new dashboard
today = datetime.now().date()
today_refs = [r for r in refs if r["times"].get("first_contact_ts") and datetime.fromtimestamp(r["times"]["first_contact_ts"]).date() == today]

# Also define queue for the table
priority_rank = {"STAT":0, "Urgent":1, "Routine":2}
status_rank = {"PREALERT":0, "ACCEPTED":1, "ENROUTE":2, "ARRIVE_DEST":3, "HANDOVER":4, "REJECTED":5}

queue = sorted(
    [r for r in today_refs if r["status"] in ["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST"]],
    key=lambda x: (status_rank.get(x["status"],9), priority_rank.get(x["transport"].get("priority","Urgent"),1), -x["times"].get("decision_ts", 0))
)

st.subheader("📋 Incoming Patient Summary")
                
# ---------- REAL-TIME FEED PANEL ----------
def _ingest_events_for(case_id: str):
    """Fetch new events for case, append to buffers, raise notifications if needed."""
    last_id = st.session_state.last_event_id.get(case_id, 0)
    new_events = poll_events_since(last_id=last_id, case_id=case_id, limit=500)
    if not new_events: 
        return

    # advance watermark
    st.session_state.last_event_id[case_id] = max(e["id"] for e in new_events)
    st.session_state.live_feed.setdefault(case_id, []).extend(new_events)

    # route to buffers + alerts
    for ev in new_events:
        et = ev["type"]
        pl = ev.get("payload", {}) or {}
        if et == "vitals.update":
            st.session_state.vitals_buffer.setdefault(case_id, []).append({
                "ts": ev["ts"], "hr": pl.get("hr"), "sbp": pl.get("sbp"),
                "rr": pl.get("rr"), "spo2": pl.get("spo2"),
                "temp": pl.get("temp"), "avpu": pl.get("avpu","A")
            })
            # simple alerts
            sbp = pl.get("sbp"); spo2 = pl.get("spo2"); avpu = (pl.get("avpu") or "A")
            if (isinstance(sbp, (int,float)) and sbp < 90) or (isinstance(spo2,(int,float)) and spo2 < 90) or (avpu in ["V","P","U"]):
                push_notification("VITALS_ALERT", "Deterioration detected", f"SBP:{sbp} SpO2:{spo2} AVPU:{avpu}", case_id, "warning")

        elif et == "intervention.added":
            st.session_state.interventions_buffer.setdefault(case_id, []).append({
                "ts": ev["ts"], "name": pl.get("name",""), "status": pl.get("status","completed"),
                "by": ev.get("actor","emt")
            })

        elif et == "status.update":
            # optional: reflect status changes from EMT telematics
            push_notification("STATUS", "Status update", f"{pl.get('status','?')}", case_id, "info")

# Render panel if a case is open
if st.session_state.open_case_id:
    ocid = st.session_state.open_case_id
    st.markdown("### 📡 Live Transfer Feed")
    feed_col1, feed_col2 = st.columns([2, 3])

    # Ingest new events
    _ingest_events_for(ocid)

    # LEFT: latest vitals + small table
    with feed_col1:
        st.markdown("**Latest vitals**")
        vbuf = st.session_state.vitals_buffer.get(ocid, [])
        if vbuf:
            last = vbuf[-1]
            st.write(f"- Time: {fmt_ts(last['ts'], short=True)}")
            st.write(f"- HR: {last['hr']}  •  SBP: {last['sbp']}  •  RR: {last['rr']}")
            st.write(f"- SpO₂: {last['spo2']}  •  Temp: {last['temp']}°C  •  AVPU: {last['avpu']}")
            vdf = pd.DataFrame(vbuf)
            vdf["time"] = pd.to_datetime(vdf["ts"], unit="s").dt.strftime("%H:%M:%S")
            st.dataframe(vdf[["time","hr","sbp","rr","spo2","temp","avpu"]].tail(12), use_container_width=True, height=240)
        else:
            st.info("Waiting for EMT vitals…")

        st.markdown("**Interventions (EMT)**")
        ibuf = st.session_state.interventions_buffer.get(ocid, [])
        if ibuf:
            idf = pd.DataFrame(ibuf)
            idf["time"] = pd.to_datetime(idf["ts"], unit="s").dt.strftime("%H:%M:%S")
            st.dataframe(idf[["time","name","status","by"]].tail(10), use_container_width=True, height=180)
        else:
            st.caption("None yet.")

    # RIGHT: live event log
    with feed_col2:
        st.markdown("**Event log**")
        evs = st.session_state.live_feed.get(ocid, [])
    
        # Also include interventions in the event log
        emt_intervs = st.session_state.emt_interventions.get(ocid, [])
        for interv in emt_intervs[-10:]:  # Show recent EMT interventions
            t = fmt_ts(interv['timestamp'], short=True)
            st.markdown(f"""
            <div class="audit">
                🚑 <strong>INTERVENTION</strong> • {interv['intervention']} ({interv['status']})<br>
                <small>{interv['details']} • {t}</small>
            </div>
            """, unsafe_allow_html=True)
    
        if not evs and not emt_intervs:
            st.caption("No events yet.")
        else:
            for ev in evs[-30:]:
                t = fmt_ts(ev["ts"], short=True)
                if ev["type"] == "vitals.update":
                    p = ev["payload"]; txt = f"{t} • VITALS • HR:{p.get('hr')} SBP:{p.get('sbp')} RR:{p.get('rr')} SpO2:{p.get('spo2')} Temp:{p.get('temp')} AVPU:{p.get('avpu','A')}"
                elif ev["type"] == "intervention.added":
                    p = ev["payload"]; txt = f"{t} • INTERVENTION • {p.get('name','')} ({p.get('status','completed')}) by {ev.get('actor','emt')}"
                else:
                    txt = f"{t} • {ev['type']}"
                st.markdown(f'<div class="audit">{txt}</div>', unsafe_allow_html=True)

        # Controls
        c1, c2, c3 = st.columns(3)
        if c1.button("Mark feed read"):
            # just clear unread notion by not doing anything; notifications carry unread state
            st.success("Feed viewed")
        if c2.button("Clear feed"):
            st.session_state.live_feed[ocid] = []
            st.session_state.vitals_buffer[ocid] = []
            st.session_state.interventions_buffer[ocid] = []
            st.success("Cleared")
        if c3.button("Close feed"):
            st.session_state.open_case_id = None
            st.success("Live feed closed")
            auto_save()
            st.rerun()

# Enhanced real-time features
def setup_real_time_listener():
    """Set up real-time event listening"""
    if "last_poll_time" not in st.session_state:
        st.session_state.last_poll_time = now_ts()
    
    # Poll for new events every 5 seconds if auto-refresh is enabled
    if auto and (now_ts() - st.session_state.last_poll_time > 5):
        check_for_new_events()
        st.session_state.last_poll_time = now_ts()

def check_for_new_events():
    """Check for new system-wide events"""
    try:
        new_events = poll_events_since(st.session_state.get("system_last_event_id", 0))
        if new_events:
            st.session_state.system_last_event_id = max(e["id"] for e in new_events)
            for event in new_events:
                handle_system_event(event)
    except Exception as e:
        st.error(f"Error checking events: {e}")

def handle_system_event(event):
    """Handle system-wide events"""
    event_type = event.get("type", "")
    case_id = event.get("case_id", "")
    
    if event_type == "system.alert":
        push_notification("SYSTEM_ALERT", event.get("title", "System Alert"), 
                         event.get("message", ""), case_id, "warning")
# Performance optimizations with caching
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_analytics_data(_adf, d0, d1):
    """Cache expensive analytics calculations"""
    if _adf.empty:
        return {}
    
    # Calculate metrics (this is computationally expensive)
    metrics = {
        "total": len(_adf),
        "awaiting": len(_adf[_adf["status"].isin(["PREALERT","ACCEPTED","ENROUTE"])]),
        "enroute": len(_adf[_adf["status"]=="ENROUTE"]),
        "arrived": len(_adf[_adf["status"]=="ARRIVE_DEST"]),
        "handover": len(_adf[_adf["status"]=="HANDOVER"]),
        "rejected": len(_adf[_adf["status"]=="REJECTED"]),
        "accept_rate": calculate_accept_rate(_adf),
        "median_times": calculate_median_times(_adf)
    }
    
    return metrics

def calculate_accept_rate(df):
    """Calculate acceptance rate"""
    accept_base = len(df[df["status"].isin(["PREALERT","ACCEPTED","ENROUTE","ARRIVE_DEST","HANDOVER","REJECTED"])])
    rejected = len(df[df["status"]=="REJECTED"])
    return (100.0 * (accept_base - rejected) / accept_base) if accept_base else 0.0

def calculate_median_times(df):
    """Calculate median times for SLAs"""
    return {
        "decision_to_dispatch": median(df["decision_to_dispatch_min"].dropna()) if not df["decision_to_dispatch_min"].dropna().empty else 0,
        "dispatch_to_arrival": median(df["dispatch_to_arrival_min"].dropna()) if not df["dispatch_to_arrival_min"].dropna().empty else 0,
        "arrival_to_handover": median(df["arrival_to_handover_min"].dropna()) if not df["arrival_to_handover_min"].dropna().empty else 0
    }                         
# -------------------- Comprehensive Analytics Dashboard --------------------
st.subheader("📊 Hospital Performance Analytics")

analytics_tab1, analytics_tab2, analytics_tab3, analytics_tab4 = st.tabs(["Overview", "Clinical Metrics", "Operational Efficiency", "Resource Utilization"])

with analytics_tab1:
    col1, col2 = st.columns(2)
    with col1:
        # Triage distribution
        st.markdown("**Triage Distribution**")
        triage_data = adf['triage'].value_counts()
        st.bar_chart(triage_data)
    
    with col2:
        # Status distribution
        st.markdown("**Case Status Distribution**")
        status_data = adf['status'].value_counts()
        st.bar_chart(status_data)

with analytics_tab2:
    col1, col2 = st.columns(2)
    with col1:
        # Case types by triage
        st.markdown("**Case Types by Triage Level**")
        case_triage = pd.crosstab(adf['case_type'], adf['triage'])
        st.bar_chart(case_triage)
    
    with col2:
        # Time-based analysis
        st.markdown("**Referrals by Hour of Day**")
        adf['hour'] = pd.to_datetime(adf['first_contact']).dt.hour
        hourly_counts = adf['hour'].value_counts().sort_index()
        st.line_chart(hourly_counts)

with analytics_tab3:
    # SLA Performance
    st.markdown("**SLA Performance Metrics**")
    sla_col1, sla_col2, sla_col3 = st.columns(3)
    
    with sla_col1:
        median_dispatch = adf['decision_to_dispatch_min'].median()
        st.metric("Decision to Dispatch", f"{median_dispatch:.1f} min")
    
    with sla_col2:
        median_transport = adf['dispatch_to_arrival_min'].median()
        st.metric("Transport Time", f"{median_transport:.1f} min")
    
    with sla_col3:
        acceptance_rate = (len(adf[adf['status'] != 'REJECTED']) / len(adf)) * 100
        st.metric("Acceptance Rate", f"{acceptance_rate:.1f}%")

with analytics_tab4:
    # Resource utilization
    st.markdown("**Resource Utilization**")
    
    # ICU bed utilization
    icu_demand = len(adf[(adf['triage'] == 'RED') & (adf['status'].isin(['ACCEPTED', 'ENROUTE', 'ARRIVE_DEST', 'HANDOVER']))])
    icu_available = st.session_state.resources[facility]['icu_available']
    icu_utilization = (icu_demand / (icu_demand + icu_available)) * 100 if (icu_demand + icu_available) > 0 else 0
    
    util_col1, util_col2 = st.columns(2)
    with util_col1:
        st.metric("ICU Beds Demand", icu_demand)
        st.metric("ICU Beds Available", icu_available)
    with util_col2:
        st.metric("ICU Utilization", f"{icu_utilization:.1f}%")
        
        # Utilization gauge
        if icu_utilization > 80:
            st.error("🚨 High ICU Utilization")
        elif icu_utilization > 60:
            st.warning("⚠️ Moderate ICU Utilization")
        else:
            st.success("✅ Normal ICU Utilization")  
        
# Enhanced export & reporting
def generate_daily_report():
    """Generate comprehensive daily report"""
    today_data = [r for r in refs if safe_date_conversion(r["times"].get("first_contact_ts")) == datetime.now().date()]
    
    report = {
        "date": datetime.now().date().isoformat(),
        "facility": facility,
        "summary": {
            "total_referrals": len(today_data),
            "accepted": len([r for r in today_data if r["status"] != "REJECTED"]),
            "rejected": len([r for r in today_data if r["status"] == "REJECTED"]),
            "completion_rate": f"{calculate_accept_rate(pd.DataFrame([to_row(r) for r in today_data])):.1f}%"
        },
        "metrics": {
            "avg_decision_to_dispatch": median([minutes_between(r["times"].get("decision_ts"), r["times"].get("dispatch_ts")) for r in today_data if r["times"].get("decision_ts") and r["times"].get("dispatch_ts")]) or 0,
            "critical_cases": len([r for r in today_data if r["triage"]["decision"]["color"] == "RED"])
        }
    }
    return report

def export_clinical_summary(referral_id):
    """Export ISBAR summary for clinical handover"""
    referral = next((r for r in refs if r["id"] == referral_id), None)
    if referral:
        return generate_isbar_template(referral)
    return None

def generate_isbar_template(referral):
    """Generate ISBAR handover template"""
    return f"""
ISBAR CLINICAL HANDOVER - {referral['id']}
========================================
IDENTIFICATION:
- Patient: {referral['patient']['name']}
- Age/Sex: {referral['patient']['age']}/{referral['patient']['sex']}
- ID: {referral['patient']['id']}

SITUATION:
- Chief Complaint: {referral['triage']['complaint']}
- Triage: {referral['triage']['decision']['color']}
- Priority: {referral['transport'].get('priority', 'Urgent')}

BACKGROUND:
- Referring Facility: {referral['referrer']['facility']}
- Referring Person: {referral['referrer']['name']} ({referral['referrer']['role']})
- Provisional DX: {referral['provisionalDx'].get('label', '—')}

ASSESSMENT:
- Latest Vitals: HR {referral['triage']['hr']}, BP {referral['triage']['sbp']}, RR {referral['triage']['rr']}, SpO2 {referral['triage']['spo2']}%
- Temperature: {referral['triage']['temp']}°C
- AVPU: {referral['triage']['avpu']}

RECOMMENDATION:
- Current Status: {referral['status']}
- Ambulance: {referral['transport'].get('ambulance', '—')}
- ETA: {referral['transport'].get('eta_min', '—')} minutes
========================================
"""
# -------------------- Exports --------------------
st.subheader("Exports")
colx1, colx2 = st.columns(2)
if not adf.empty:
    csv_bytes = adf.to_csv(index=False).encode("utf-8")
    json_bytes = json.dumps(refs, indent=2).encode("utf-8")
else:
    csv_bytes = "".encode("utf-8")
    json_bytes = "".encode("utf-8")

with colx1:
    st.download_button("⬇️ Download CSV (range @ facility)", data=csv_bytes, file_name="receiving_range.csv", mime="text/csv", disabled=(len(adf)==0))
with colx2:
    st.download_button("⬇️ Download JSON (range @ facility)", data=json_bytes, file_name="receiving_range.json", mime="application/json", disabled=(len(refs)==0))
