import json
import os

def load_data():
    try:
        with open("data.json", "r") as f:
            return json.load(f)
    except:
        return {"referrals": [], "interventions": {}, "resources": {}}

def save_data(data):
    with open("data.json", "w") as f:
        json.dump(data, f)

# Initialize in your main app
if "app_data" not in st.session_state:
    st.session_state.app_data = load_data()
    st.session_state.referrals_all = st.session_state.app_data.get("referrals", [])
