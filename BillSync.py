import streamlit as pd
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar

# --- CONFIGURATION & SESSION STATE INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Billsync Dashboard")

# Initialize mockup database in session state so data persists during the session
if "templates" not in st.session_state:
    st.session_state.templates = [
        {"id": 1, "name": "Netflix", "amount": 15.99, "frequency": "Monthly", "day": 15, "category": "Subscriptions", "method": "Visa ...1234", "auto_pay": True, "active": True},
        {"id": 2, "name": "Council Tax", "amount": 160.00, "frequency": "Monthly", "day": 1, "category": "Utilities", "method": "Direct Debit", "auto_pay": True, "active": True},
        {"id": 3, "name": "Car Insurance", "amount": 450.00, "frequency": "Yearly", "day": 10, "category": "Insurance", "method": "Mastercard ...5678", "auto_pay": False, "active": True},
    ]

if "overrides" not in st.session_state:
    # Keeps track of manual adjustments: {(template_id, date_string): {"amount": X, "paid": True/False}}
    st.session_state.overrides = {
        (1, "2026-05-15"): {"amount": 15.99, "paid": True},
        (2, "2026-05-01"): {"amount": 160.00, "paid": True},
    }

# --- SYSTEM CORE LOGIC: INSTANCE GENERATOR ---
def generate_instances(templates, start_date, end_date):
    """
    Core Logic: Generates specific bill instances from templates dynamically.
    Guarantees all comparisons use pure datetime.date objects.
    """
    instances = []
    
    for tmpl in templates:
        if not tmpl["active"]:
            continue
            
        # Start scanning from the 1st day of the start_date month
        scan_date = datetime(start_date.year, start_date.month, 1).date()
        
        while scan_date <= end_date:
            bill_date = None
            
            if tmpl["frequency"] == "Monthly":
                # Handle month-end overflows safely
                last_day = calendar.monthrange(scan_date.year, scan_date.month)[1]
                day = min(tmpl["day"], last_day)
                bill_date = datetime(scan_date.year, scan_date.month, day).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1) # Move to next month
                
            elif tmpl["frequency"] == "Yearly":
                if scan_date.month == 1: 
                    bill_date = datetime(scan_date.year, 1, min(tmpl["day"], 28)).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1)
            else:
                bill_date = datetime(scan_date.year, scan_date.month, min(tmpl["day"], 28)).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1)

            # Fix: No more .date() calls here since everything is already a date object
            if bill_date and start_date <= bill_date <= end_date:
                date_str = bill_date.strftime("%Y-%m-%d")
                
                # Check for historical overrides or changes
                override = st.session_state.overrides.get((tmpl["id"], date_str), {})
                
                instances.append({
                    "template_id": tmpl["id"],
                    "name": tmpl["name"],
                    "date": bill_date, # Already a date object
                    "date_str": date_str,
                    "amount": override.get("amount", tmpl["amount"]),
                    "paid": override.get("paid", False),
                    "category": tmpl["category"],
                    "method": tmpl["method"],
                    "auto_pay": tmpl["auto_pay"]
                })
                
    return sorted(instances, key=lambda x: x["date"])

# --- APP LAYOUT ---
st.title("💸 BillSync: Recurring Bill Planner")
st.markdown("---")

today = datetime.now().date()
# Main View Tabbing Layout
tab1, tab2 = st.tabs(["🗂️ Grid View (Template Management)", "📅 Timeline View (Live Feed)"])

# --- TAB 1: GRID VIEW ---
with tab1:
    st.subheader("Core Bill Rules & Templates")
    
    # Form to add a new template rule
    with st.expander("➕ Create New Recurring Bill Template"):
        with st.form("new_bill_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                new_name = st.text_input("Bill Name", placeholder="e.g. Broadband")
                new_amount = st.number_input("Amount (£)", min_value=0.0, value=10.0, step=0.5)
            with col2:
                new_freq = st.selectbox("Frequency", ["Weekly", "Monthly", "Yearly"])
                new_day = st.number_input("Preferred Payment Day of Month", min_value=1, max_value=31, value=1)
            with col3:
                new_cat = st.selectbox("Category Tagging", ["Utilities", "Subscriptions", "Rent", "Insurance", "Other"])
                new_method = st.text_input("Payment Method Tracking", placeholder="e.g. Visa ...9999")
            
            new_autopay = st.toggle("Auto-Pay Enabled", value=False)
            
            if st.form_submit_button("Save Template Rule"):
                new_id = max([t["id"] for t in st.session_state.templates]) + 1 if st.session_state.templates else 1
                st.session_state.templates.append({
                    "id": new_id, "name": new_name, "amount": new_amount, "frequency": new_freq,
                    "day": new_day, "category": new_cat, "method": new_method, "auto_pay": new_autopay, "active": True
                })
                st.success(f"Template for '{new_name}' deployed successfully!")
                st.rerun()

    # Display Current Active Rules
    st.write("### Active Subscriptions & Liabilities")
    for idx, tmpl in enumerate(st.session_state.templates):
        status_color = "🟢 Active" if tmpl["active"] else "⚪ Archived/Paused"
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
            with c1:
                st.markdown(f"#### {tmpl['name']}")
                st.caption(f"Tag: {tmpl['category']} | Status: {status_color}")
            with c2:
                st.markdown(f"**Cost:** £{tmpl['amount']:.2f} ({tmpl['frequency']})")
                st.caption(f"Payment Source: {tmpl['method']}")
            with c3:
                st.markdown(f"**Auto-Pay:** {'✅ Yes' if tmpl['auto_pay'] else '❌ Manual'}")
                st.caption(f"Day Cycle target: Day {tmpl['day']}")
            with c4:
                # Management Actions
                if tmpl["active"]:
                    if st.button("Archive/Pause", key=f"pause_{tmpl['id']}"):
                        tmpl["active"] = False
                        st.rerun()
                else:
                    if st.button("Reactivate", key=f"reactivate_{tmpl['id']}"):
                        tmpl["active"] = True
                        st.rerun()

# --- TAB 2: TIMELINE VIEW ---
with tab2:
    st.subheader("Chronological Expense Stream")
    
    # Virtual Scrolling configuration interface
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        # max_value is now 365, but the step interval stays at 5 days
        lookback = st.slider("Lookback History (Days Past)", min_value=0, max_value=365, value=30, step=5)
    with col_v2:
        lookforward = st.slider("Future Forecast Horizon (Days Out)", min_value=30, max_value=365, value=90, step=30)
        
    start_range = today - timedelta(days=lookback)
    end_range = today + timedelta(days=lookforward)
    
    # Back-end compilation window extended safely to catch older un-cleared obligations
    effective_start = today - timedelta(days=365)
    all_instances = generate_instances(st.session_state.templates, effective_start, end_range)
    
    # --- STEP 1: DYNAMIC ROLLING WINDOW CALCULATION ---
    # Scan historical instances to map out the absolute latest past date for each individual bill name
    most_recent_past_dates = {}
    for inst in all_instances:
        if inst["date"] < today:
            name = inst["name"]
            if name not in most_recent_past_dates or inst["date"] > most_recent_past_dates[name]:
                most_recent_past_dates[name] = inst["date"]

    # --- STEP 2: APPLY ROLLING RULES & FILTER WINDOW ---
    filtered_instances = []
    for inst in all_instances:
        is_past = inst["date"] < today
        name = inst["name"]
        
        # Default rolling fallback assignments
        if is_past:
            # Only the single most recent historical occurrence defaults to overdue
            if inst["date"] == most_recent_past_dates.get(name):
                default_paid = False
                is_overdue = True
            else:
                # All older historical instances are cleanly swept to true
                default_paid = True
                is_overdue = False
        else:
            # Future instances are pending/scheduled by default
            default_paid = False
            is_overdue = False

        # Load session state overrides if the user interacted manually via toggle buttons
        key = (inst["template_id"], inst["date_str"])
        if key in st.session_state.overrides:
            inst["paid"] = st.session_state.overrides[key]["paid"]
            # Recalculate runtime overdue metric based on current absolute state context
            is_overdue = is_past and not inst["paid"]
        else:
            inst["paid"] = default_paid

        # Match entry against active timeline sliders criteria OR retain if it's explicitly overdue
        if (inst["date"] >= start_range) or is_overdue:
            # Cache active overdue boolean as a secondary sorting attribute key helper
            inst["_is_overdue_flag"] = is_overdue
            filtered_instances.append(inst)
            
    # --- STEP 3: PRIORITY STATUS STREAM SORTING ---
    # Sorts by active overdue status flag first, then falls back to clean chronological sequencing
    filtered_instances.sort(key=lambda x: (not x.get("_is_overdue_flag", False), x["date"]))
    
    # --- TIME-BASED GROUPED FEED RENDER ---
    st.markdown("### 🧭 Live Feed Stream")
    
    if not filtered_instances:
        st.warning("No generated schedule instances fall within this selected timeframe.")
    else:
        current_bucket = ""
        
        for inst in filtered_instances:
            is_past = inst["date"] < today
            is_overdue = inst.get("_is_overdue_flag", False)
            
            # Grouping header logic mapping
            if is_overdue:
                if current_bucket != "⚠️ ACTIVELY OVERDUE":
                    current_bucket = "⚠️ ACTIVELY OVERDUE"
                    st.markdown(f"#### {current_bucket}")
            else:
                inst_bucket = inst["date"].strftime("%B %Y")
                if inst_bucket != current_bucket:
                    current_bucket = inst_bucket
                    st.markdown(f"#### 📅 {current_bucket}")
            
            # Simple high-contrast native text badges
            if inst["paid"]:
                status_text = "🟢 Verified Paid"
            elif is_overdue:
                status_text = "🔴 OVERDUE"
            else:
                status_text = "🟡 Scheduled"

            # Render standard native container with explicit clean borders
            with st.container(border=True):
                cols = st.columns([3, 2, 2, 1.5], vertical_alignment="center")
                
                with cols[0]:
                    text_opacity = "0.5" if (is_past and inst["paid"]) else "1.0"
                    st.markdown(f"<div style='opacity:{text_opacity};'><b style='font-size:1.15rem;'>{inst['name']}</b></div>", unsafe_allow_html=True)
                    st.caption(f"{inst['category']} • {inst['method']}")
                    
                with cols[1]:
                    new_amt = st.number_input(
                        "Amount Due (£)", 
                        value=float(inst["amount"]), 
                        key=f"amt_{inst['template_id']}_{inst['date_str']}",
                        step=0.01,
                        format="%.2f",
                        label_visibility="collapsed"
                    )
                    if new_amt != float(inst["amount"]):
                        key = (inst["template_id"], inst["date_str"])
                        if key not in st.session_state.overrides:
                            st.session_state.overrides[key] = {"amount": new_amt, "paid": inst["paid"]}
                        else:
                            st.session_state.overrides[key]["amount"] = new_amt
                        st.rerun()
                        
                with cols[2]:
                    st.markdown(f"<div><b>{status_text}</b><br><small style='color:gray;'>Due: {inst['date'].strftime('%b %d')}</small></div>", unsafe_allow_html=True)
                        
                with cols[3]:
                    button_label = "Undo" if inst["paid"] else "Mark Paid"
                    if st.button(button_label, key=f"btn_{inst['template_id']}_{inst['date_str']}", use_container_width=True):
                        key = (inst["template_id"], inst["date_str"])
                        target_state = not inst["paid"]
                        
                        if key not in st.session_state.overrides:
                            st.session_state.overrides[key] = {"amount": inst["amount"], "paid": target_state}
                        else:
                            st.session_state.overrides[key]["paid"] = target_state
                        st.rerun()
