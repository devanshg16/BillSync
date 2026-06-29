import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import calendar

# --- CONFIGURATION & SESSION STATE INITIALIZATION ---
st.set_page_config(layout="wide", page_title="Billsync Dashboard")

if "templates" not in st.session_state:
    st.session_state.templates = [
        {"id": 1, "name": "Netflix", "amount": 15.99, "frequency": "Monthly", "day": 15, "category": "Subscriptions", "method": "Visa ...1234", "auto_pay": True, "active": True},
        {"id": 2, "name": "Council Tax", "amount": 160.00, "frequency": "Monthly", "day": 1, "category": "Utilities", "method": "Direct Debit", "auto_pay": True, "active": True},
        {"id": 3, "name": "Car Insurance", "amount": 450.00, "frequency": "Yearly", "day": 10, "category": "Insurance", "method": "Mastercard ...5678", "auto_pay": False, "active": True},
    ]

if "overrides" not in st.session_state:
    st.session_state.overrides = {
        (1, "2026-05-15"): {"amount": 15.99, "paid": True},
        (2, "2026-05-01"): {"amount": 160.00, "paid": True},
    }

# --- SYSTEM CORE LOGIC: INSTANCE GENERATOR ---
def generate_instances(templates, start_date, end_date):
    instances = []
    for tmpl in templates:
        if not tmpl["active"]:
            continue
        scan_date = datetime(start_date.year, start_date.month, 1).date()
        while scan_date <= end_date:
            bill_date = None
            if tmpl["frequency"] == "Monthly":
                last_day = calendar.monthrange(scan_date.year, scan_date.month)[1]
                day = min(tmpl["day"], last_day)
                bill_date = datetime(scan_date.year, scan_date.month, day).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1)
            elif tmpl["frequency"] == "Yearly":
                if scan_date.month == 1:
                    bill_date = datetime(scan_date.year, 1, min(tmpl["day"], 28)).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1)
            else:
                bill_date = datetime(scan_date.year, scan_date.month, min(tmpl["day"], 28)).date()
                scan_date = (scan_date + timedelta(days=32)).replace(day=1)

            if bill_date and start_date <= bill_date <= end_date:
                date_str = bill_date.strftime("%Y-%m-%d")
                override = st.session_state.overrides.get((tmpl["id"], date_str), {})
                instances.append({
                    "template_id": tmpl["id"],
                    "name": tmpl["name"],
                    "date": bill_date,
                    "date_str": date_str,
                    "amount": override.get("amount", tmpl["amount"]),
                    "paid": override.get("paid", False),
                    "category": tmpl["category"],
                    "method": tmpl["method"],
                    "auto_pay": tmpl["auto_pay"]
                })
    return sorted(instances, key=lambda x: x["date"])

# --- CLEAN TARGETED STICKY CSS & TOP MARGIN REMOVAL ---
st.markdown(
    """
    <style>
    /* 1. Eliminate the huge native Streamlit top whitespace gap */
    div[data-testid="stAppViewBlockContainer"], 
    div[data-testid="stMainBlockContainer"] {
        padding-top: 1.5rem !important;
        margin-top: 0px !important;
    }

    /* Allow layout blocks to let sticky elements float over them safely */
    [data-testid="stAppViewBlockContainer"],
    [data-testid="stMainBlockContainer"],
    [data-testid="stVerticalBlock"],
    [data-testid="stTabPanel"],
    div[role="tabpanel"] {
        overflow: visible !important;
    }

    /* Target the first element inside each tab (our subheader/controls) and stick it */
    div[data-testid="stTabPanel"] > div[data-testid="stVerticalBlock"] > div:first-child {
        position: sticky !important;
        top: 0rem !important; /* Move it up to snap right to the very top edge */
        background-color: white !important;
        z-index: 999 !important;
        padding-top: 10px !important;
        padding-bottom: 15px !important;
        border-bottom: 2px solid #f0f2f6 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

today = datetime.now().date()
tab1, tab2 = st.tabs(["🗂️ Grid View (Template Management)", "📅 Timeline View (Live Feed)"])

# --- TAB 1: GRID VIEW ---
with tab1:
    # This entire block (subheader + form) is the first-child element, so it stays stickied
    with st.container():
        st.subheader("Core Bill Rules & Templates")
        with st.expander("➕ Create New Recurring Bill Template", expanded=False):
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
                
                if st.form_submit_button("Save Template Rule", use_container_width=True):
                    new_id = max([t["id"] for t in st.session_state.templates]) + 1 if st.session_state.templates else 1
                    st.session_state.templates.append({
                        "id": new_id, "name": new_name, "amount": new_amount, "frequency": new_freq,
                        "day": new_day, "category": new_cat, "method": new_method, "auto_pay": new_autopay, "active": True
                    })
                    st.success(f"Template for '{new_name}' deployed successfully!")
                    st.rerun()

    # Dynamic scrollable feed contents below the sticky header
    st.markdown("### 📋 Active Subscriptions & Liabilities")
    if not st.session_state.templates:
        st.info("No active templates created yet. Populate using the expander form above.")
    else:
        for idx, tmpl in enumerate(st.session_state.templates):
            status_color = "🟢 Active" if tmpl["active"] else "⚪ Archived/Paused"
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1], vertical_alignment="center")
                with c1:
                    st.markdown(f"<b style='font-size:1.1rem;'>{tmpl['name']}</b>", unsafe_allow_html=True)
                    st.caption(f"Tag: {tmpl['category']} | Status: {status_color}")
                with c2:
                    st.markdown(f"**Cost:** £{tmpl['amount']:.2f} ({tmpl['frequency']})")
                    st.caption(f"Payment Source: {tmpl['method']}")
                with c3:
                    st.markdown(f"**Auto-Pay:** {'✅ Yes' if tmpl['auto_pay'] else '❌ Manual'}")
                    st.caption(f"Day Cycle target: Day {tmpl['day']}")
                with c4:
                    if tmpl["active"]:
                        if st.button("Archive/Pause", key=f"pause_{tmpl['id']}", use_container_width=True):
                            tmpl["active"] = False
                            st.rerun()
                    else:
                        if st.button("Reactivate", key=f"reactivate_{tmpl['id']}", use_container_width=True):
                            tmpl["active"] = True
                            st.rerun()

# --- TAB 2: TIMELINE VIEW ---
with tab2:
    # Sticky Header Container Injection
    # This locks the subheader and sliders to the top of the screen during scrolling
    st.markdown(
        """
        <style>
        /* Target the top layout elements or columns inside this tab */
        div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stSlider"]) {
            position: sticky;
            top: 2.875rem; /* Aligns right underneath Streamlit's main header navbar */
            background-color: white; /* Matches standard app background to prevent text overlap transparency */
            z-index: 99;
            padding-top: 10px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e6e6e6;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
  
    # Virtual Scrolling configuration interface (This stays pinned now)
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        lookback = st.slider("Lookback History (Days Past)", min_value=0, max_value=365, value=30, step=5)
    with col_v2:
        lookforward = st.slider("Future Forecast Horizon (Days Out)", min_value=0, max_value=365, value=90, step=5)
        
    start_range = today - timedelta(days=lookback)
    end_range = today + timedelta(days=lookforward)
    
    effective_start = today - timedelta(days=365)
    all_instances = generate_instances(st.session_state.templates, effective_start, end_range)
    
    # --- STEP 1: DYNAMIC ROLLING WINDOW CALCULATION ---
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
        
        if is_past:
            if inst["date"] == most_recent_past_dates.get(name):
                default_paid = False
                is_overdue = True
            else:
                default_paid = True
                is_overdue = False
        else:
            default_paid = False
            is_overdue = False

        key = (inst["template_id"], inst["date_str"])
        if key in st.session_state.overrides:
            inst["paid"] = st.session_state.overrides[key]["paid"]
            is_overdue = is_past and not inst["paid"]
        else:
            inst["paid"] = default_paid

        if (inst["date"] >= start_range) or is_overdue:
            inst["_is_overdue_flag"] = is_overdue
            filtered_instances.append(inst)
            
    # --- STEP 3: DYNAMIC FUTURE-PROOF SORTING ---
    def get_sort_key(inst):
        # Dynamically fetch the 1st of the current month based on the system clock
        current_month_start = today.replace(day=1)
        is_overdue = inst.get("_is_overdue_flag", False)
        
        if is_overdue:
            # Overdue items are forced to the start of the current real-world month.
            # Tie-breaker (0) forces them ahead of normal items debuting on the 1st of this month.
            return (current_month_start, 0, inst["date"])
        else:
            # Normal items sort directly by their planned chronological cycle date.
            # Tie-breaker (1) pushes them cleanly underneath any active overdue items.
            return (inst["date"], 1, inst["date"])

    filtered_instances.sort(key=get_sort_key)
    
    # --- TIME-BASED GROUPED FEED RENDER ---
    if not filtered_instances:
        st.warning("No generated schedule instances fall within this selected timeframe.")
    else:
        current_bucket = ""
        overdue_header_placed = False
        
        for inst in filtered_instances:
            is_past = inst["date"] < today
            is_overdue = inst.get("_is_overdue_flag", False)
            
            if is_overdue:
                if not overdue_header_placed:
                    # Bring back the relative invisible target anchor block
                    st.markdown('<div id="overdue-marker" style="position: relative; top: -160px;"></div>', unsafe_allow_html=True)
                    st.markdown("#### 📅 ⚠️ ACTIVELY OVERDUE")
                    overdue_header_placed = True
                current_bucket = "⚠️ ACTIVELY OVERDUE"
            else:
                # Normal calendar month header grouping (Calculated dynamically)
                inst_bucket = inst["date"].strftime("%B %Y")
                if inst_bucket != current_bucket:
                    current_bucket = inst_bucket
                    st.markdown(f"#### 📅 {current_bucket}")
            
            # Determine Status Badge Text
            if inst["paid"]:
                status_text = "🟢 Verified Paid"
            elif is_overdue:
                status_text = "🔴 OVERDUE"
            else:
                status_text = "🟡 Scheduled"

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

        # --- STEP 4: AUTOMATIC VIEWPORT FOCUS INJECTION ---
        st.components.v1.html(
            """
            <script>
                (function() {
                    var parentDoc = window.parent.document;
                    var parentWin = window.parent;

                    function safeScroll() {
                        setTimeout(function() {
                            var element = parentDoc.getElementById("overdue-marker");
                            if (!element) {
                                var headers = parentDoc.querySelectorAll('h4');
                                for (var i = 0; i < headers.length; i++) {
                                    if (headers[i].textContent.includes("📅")) {
                                        element = headers[i];
                                        break;
                                    }
                                }
                            }
                            if (element) {
                                element.scrollIntoView({ behavior: "smooth", block: "start" });
                            }
                        }, 150);
                    }

                    // Clear any old polling interval so we don't stack them on rerenders
                    if (parentWin._tab2PollInterval) {
                        clearInterval(parentWin._tab2PollInterval);
                    }

                    var prevTab2State = null;

                    parentWin._tab2PollInterval = setInterval(function() {
                        var tabs = parentDoc.querySelectorAll('button[role="tab"]');
                        if (!tabs[1]) return;

                        var isTab2Active = tabs[1].getAttribute('aria-selected') === 'true';

                        // Detect the exact moment Tab 2 becomes active
                        if (isTab2Active && prevTab2State === false) {
                            safeScroll();
                        }

                        prevTab2State = isTab2Active;
                    }, 200);
                })();
            </script>
            """,
            height=0,
            width=0
        )
