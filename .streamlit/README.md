# Receiving Hospital – AHECN MVP (Streamlit)

Synthetic, same-day receiving-hospital dashboard: queue, actions (accept/reject/en-route/arrived/handover), vitals & interventions, ISBAR generator, and live analytics.

## Local run
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run receiving_hospital_dashboard.py
