import streamlit as st
import sqlite3
import hashlib
import os
from datetime import datetime, timedelta
import calendar
from collections import defaultdict

# --- CONFIGURATION ---
st.set_page_config(layout="wide", page_title="Billsync Dashboard")
DB_PATH = "billsync.db"

# ============================================================
# DATABASE LAYER
# ============================================================

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT UNIQUE NOT NULL,
            password  TEXT NOT NULL,
            created   TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            name       TEXT NOT NULL,
            amount     REAL NOT NULL,
            frequency  TEXT NOT NULL,
            day        INTEGER NOT NULL,
            category   TEXT NOT NULL,
            method     TEXT NOT NULL,
            auto_pay   INTEGER NOT NULL DEFAULT 0,
            active     INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS overrides (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            date_str    TEXT NOT NULL,
            amount      REAL NOT NULL,
            paid        INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, template_id, date_str),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username: str, password: str):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password, created) VALUES (?, ?, ?)",
            (username.strip().lower(), hash_password(password), datetime.now().isoformat())
        )
        conn.commit()
        return True, "Account created successfully!"
    except sqlite3.IntegrityError:
        return False, "Username already taken. Please choose another."
    finally:
        conn.close()

def login_user(username: str, password: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username.strip().lower(), hash_password(password))
    ).fetchone()
    conn.close()
    return dict(row) if row else None

# --- Template CRUD ---

def load_templates(user_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM templates WHERE user_id = ? ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_template(user_id, name, amount, frequency, day, category, method, auto_pay):
    conn = get_conn()
    conn.execute(
        """INSERT INTO templates (user_id, name, amount, frequency, day, category, method, auto_pay, active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (user_id, name, amount, frequency, day, category, method, int(auto_pay))
    )
    conn.commit()
    conn.close()

def set_template_active(template_id: int, active: bool):
    conn = get_conn()
    conn.execute("UPDATE templates SET active = ? WHERE id = ?", (int(active), template_id))
    conn.commit()
    conn.close()

# --- Override CRUD ---

def load_overrides(user_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM overrides WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return {(r["template_id"], r["date_str"]): {"amount": r["amount"], "paid": bool(r["paid"])} for r in rows}

def upsert_override(user_id, template_id, date_str, amount, paid):
    conn = get_conn()
    conn.execute(
        """INSERT INTO overrides (user_id, template_id, date_str, amount, paid)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, template_id, date_str)
           DO UPDATE SET amount = excluded.amount, paid = excluded.paid""",
        (user_id, template_id, date_str, amount, int(paid))
    )
    conn.commit()
    conn.close()

# ============================================================
# INSTANCE GENERATOR
# ============================================================

def generate_instances(templates, overrides, start_date, end_date):
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
                override = overrides.get((tmpl["id"], date_str), {})
                instances.append({
                    "template_id": tmpl["id"],
                    "name": tmpl["name"],
                    "date": bill_date,
                    "date_str": date_str,
                    "amount": override.get("amount", tmpl["amount"]),
                    "paid": override.get("paid", False),
                    "category": tmpl["category"],
                    "method": tmpl["method"],
                    "auto_pay": tmpl["auto_pay"],
                })
    return sorted(instances, key=lambda x: x["date"])

# ============================================================
# SESSION HELPERS
# ============================================================

def reload_user_data():
    uid = st.session_state.user["id"]
    st.session_state.templates = load_templates(uid)
    st.session_state.overrides = load_overrides(uid)

def logout():
    for key in ["user", "templates", "overrides"]:
        st.session_state.pop(key, None)

# ============================================================
# INIT DB
# ============================================================

init_db()

# ============================================================
# AUTH WALL
# ============================================================

if "user" not in st.session_state:

    st.markdown(
        """
        <style>
        div[data-testid="stAppViewBlockContainer"],
        div[data-testid="stMainBlockContainer"] {
            padding-top: 3rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<h1 style='text-align:center; margin-bottom: 0;'>💸 Billsync</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color: #888; margin-bottom: 2rem;'>Your personal recurring bills tracker</p>", unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        auth_tab, reg_tab = st.tabs(["🔑 Sign In", "📝 Register"])

        with auth_tab:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign In", use_container_width=True):
                    if not username or not password:
                        st.error("Please fill in both fields.")
                    else:
                        user = login_user(username, password)
                        if user:
                            st.session_state.user = user
                            reload_user_data()
                            st.rerun()
                        else:
                            st.error("Incorrect username or password.")

        with reg_tab:
            with st.form("register_form"):
                new_username = st.text_input("Choose a Username")
                new_password = st.text_input("Choose a Password", type="password")
                confirm_password = st.text_input("Confirm Password", type="password")
                if st.form_submit_button("Create Account", use_container_width=True):
                    if not new_username or not new_password:
                        st.error("Please fill in all fields.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters.")
                    else:
                        ok, msg = register_user(new_username, new_password)
                        if ok:
                            st.success(msg + " Please sign in.")
                        else:
                            st.error(msg)

    st.stop()

# ============================================================
# LOAD USER DATA INTO SESSION (if not already loaded)
# ============================================================

if "templates" not in st.session_state or "overrides" not in st.session_state:
    reload_user_data()

# ============================================================
# MAIN APP (authenticated)
# ============================================================

today = datetime.now().date()

# --- GLOBAL CSS ---
st.markdown(
    """
    <style>
    div[data-testid="stAppViewBlockContainer"],
    div[data-testid="stMainBlockContainer"] {
        padding-top: 1.5rem !important;
        margin-top: 0px !important;
    }

    [data-testid="stAppViewBlockContainer"],
    [data-testid="stMainBlockContainer"],
    [data-testid="stVerticalBlock"],
    [data-testid="stTabPanel"],
    div[role="tabpanel"] {
        overflow: visible !important;
    }

    div[data-testid="stTabPanel"] > div[data-testid="stVerticalBlock"] > div:first-child {
        position: sticky !important;
        top: 0rem !important;
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

# --- TOP BAR: user info + logout ---
top_l, top_r = st.columns([6, 1])
with top_l:
    st.markdown(f"<span style='color:#888; font-size:0.9rem;'>Signed in as <b>{st.session_state.user['username']}</b></span>", unsafe_allow_html=True)
with top_r:
    if st.button("Sign Out", use_container_width=True):
        logout()
        st.rerun()

tab1, tab2 = st.tabs(["🗂️ Grid View (Template Management)", "📅 Timeline View (Live Feed)"])

# ============================================================
# TAB 1: GRID VIEW
# ============================================================

with tab1:
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
                    if not new_name.strip():
                        st.error("Please enter a bill name.")
                    else:
                        add_template(
                            st.session_state.user["id"],
                            new_name, new_amount, new_freq, new_day,
                            new_cat, new_method, new_autopay
                        )
                        reload_user_data()
                        st.success(f"Template for '{new_name}' saved!")
                        st.rerun()

    st.markdown("### 📋 Active Subscriptions & Liabilities")
    if not st.session_state.templates:
        st.info("No templates yet. Use the form above to add your first bill.")
    else:
        for tmpl in st.session_state.templates:
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
                            set_template_active(tmpl["id"], False)
                            reload_user_data()
                            st.rerun()
                    else:
                        if st.button("Reactivate", key=f"reactivate_{tmpl['id']}", use_container_width=True):
                            set_template_active(tmpl["id"], True)
                            reload_user_data()
                            st.rerun()

# ============================================================
# TAB 2: TIMELINE VIEW
# ============================================================

with tab2:
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stSlider"]) {
            position: sticky;
            top: 2.875rem;
            background-color: white;
            z-index: 99;
            padding-top: 10px;
            padding-bottom: 15px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    col_v1, col_v2 = st.columns(2)
    with col_v1:
        lookback = st.slider("Lookback History (Days Past)", min_value=0, max_value=365, value=30, step=5)
    with col_v2:
        lookforward = st.slider("Future Forecast Horizon (Days Out)", min_value=0, max_value=365, value=90, step=5)

    start_range = today - timedelta(days=lookback)
    end_range   = today + timedelta(days=lookforward)

    effective_start = today - timedelta(days=365)
    all_instances = generate_instances(
        st.session_state.templates,
        st.session_state.overrides,
        effective_start,
        end_range
    )

    # --- STEP 1: ROLLING WINDOW CALCULATION ---
    most_recent_past_dates = {}
    for inst in all_instances:
        if inst["date"] < today:
            name = inst["name"]
            if name not in most_recent_past_dates or inst["date"] > most_recent_past_dates[name]:
                most_recent_past_dates[name] = inst["date"]

    # --- STEP 2: APPLY ROLLING RULES & FILTER ---
    filtered_instances = []
    for inst in all_instances:
        is_past = inst["date"] < today
        name    = inst["name"]

        if is_past:
            if inst["date"] == most_recent_past_dates.get(name):
                default_paid = False
                is_overdue   = True
            else:
                default_paid = True
                is_overdue   = False
        else:
            default_paid = False
            is_overdue   = False

        key = (inst["template_id"], inst["date_str"])
        if key in st.session_state.overrides:
            inst["paid"] = st.session_state.overrides[key]["paid"]
            is_overdue   = is_past and not inst["paid"]
        else:
            inst["paid"] = default_paid

        if (inst["date"] >= start_range) or is_overdue:
            inst["_is_overdue_flag"] = is_overdue
            filtered_instances.append(inst)

    # --- STEP 3: SORTING ---
    def get_sort_key(inst):
        current_month_start = today.replace(day=1)
        if inst.get("_is_overdue_flag", False):
            return (current_month_start, 0, inst["date"])
        return (inst["date"], 1, inst["date"])

    filtered_instances.sort(key=get_sort_key)

    # --- STEP 4: BUCKET CONFIG ---
    this_week_end  = today + timedelta(days=6)
    next_week_start = today + timedelta(days=7)
    next_week_end  = today + timedelta(days=13)

    def get_bucket_key(inst):
        d = inst["date"]
        if inst.get("_is_overdue_flag", False):
            return "_overdue"
        elif d < today:
            # Check if it falls within the current month and year
            if d.month == today.month and d.year == today.year:
                return "_earlier_this_month"
            return d.strftime("%B %Y")
        elif d == today:
            return "_today"
        elif d <= this_week_end:
            return "_this_week"
        elif d <= next_week_end:
            return "_next_week"
        elif d.month == today.month and d.year == today.year:
            return "_later_this_month"
        else:
            return d.strftime("%B %Y")

    # --- STEP 5: CARD RENDERER ---
    def render_card(inst):
        is_past    = inst["date"] < today
        is_overdue = inst.get("_is_overdue_flag", False)

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
                    upsert_override(
                        st.session_state.user["id"],
                        inst["template_id"], inst["date_str"],
                        new_amt, inst["paid"]
                    )
                    reload_user_data()
                    st.rerun()
            with cols[2]:
                st.markdown(f"<div><b>{status_text}</b><br><small style='color:gray;'>Due: {inst['date'].strftime('%b %d')}</small></div>", unsafe_allow_html=True)
            with cols[3]:
                button_label = "Undo" if inst["paid"] else "Mark Paid"
                if st.button(button_label, key=f"btn_{inst['template_id']}_{inst['date_str']}", use_container_width=True):
                    target_state = not inst["paid"]
                    upsert_override(
                        st.session_state.user["id"],
                        inst["template_id"], inst["date_str"],
                        inst["amount"], target_state
                    )
                    reload_user_data()
                    st.rerun()

    # --- STEP 6: GROUP & BUILD ORDERED BUCKET LIST ---
    if not filtered_instances:
        st.warning("No generated schedule instances fall within this selected timeframe.")
    else:
        buckets = defaultdict(list)
        for inst in filtered_instances:
            buckets[get_bucket_key(inst)].append(inst)

        past_month_buckets = []
        cursor = start_range.replace(day=1)
        while cursor < today.replace(day=1):
            bkey = cursor.strftime("%B %Y")
            past_month_buckets.append((bkey, f"📅 {bkey}", f"Nothing due in {cursor.strftime('%B %Y')} — all clear for this period."))
            cursor = (cursor + timedelta(days=32)).replace(day=1)

        future_month_buckets = []
        cursor = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        while cursor <= end_range:
            bkey = cursor.strftime("%B %Y")
            future_month_buckets.append((bkey, f"📅 {bkey}", f"Nothing scheduled in {cursor.strftime('%B %Y')} — enjoy the quiet."))
            cursor = (cursor + timedelta(days=32)).replace(day=1)

        ordered_buckets = []

        if lookback > 0:
            ordered_buckets += past_month_buckets

        if buckets["_overdue"]:
            ordered_buckets.append(("_overdue", "⚠️ ACTIVELY OVERDUE", None))

        # Add the new section immediately before "Today"
        ordered_buckets.append(("_earlier_this_month", f"📅 Earlier This Month — {today.strftime('%B %Y')}", "No historical items logged earlier this month."))

        ordered_buckets += [
            ("_today",            f"📅 Today — {today.strftime('%b %d')}",                                                                     "Nothing due today — enjoy the day off."),
            ("_this_week",        f"📅 This Week — {(today + timedelta(days=1)).strftime('%b %d')} to {this_week_end.strftime('%b %d')}",  "Nothing due in the next 6 days."),
            ("_next_week",        f"📅 Next Week — {next_week_start.strftime('%b %d')} to {next_week_end.strftime('%b %d')}",              "Nothing due next week."),
            ("_later_this_month", f"📅 Later This Month — {today.strftime('%B')}",                                                         "Nothing else due this month."),
        ]

        ordered_buckets += future_month_buckets

        # --- STEP 7: RENDER ---
        for bucket_key, bucket_label, empty_msg in ordered_buckets:
            if bucket_key == "_overdue":
                st.markdown('<div id="overdue-marker" style="position: relative; top: -160px;"></div>', unsafe_allow_html=True)
                st.markdown(f"#### {bucket_label}")
            else:
                st.markdown(f"#### {bucket_label}")

            items = buckets.get(bucket_key, [])
            if items:
                for inst in items:
                    render_card(inst)
            elif empty_msg:
                st.markdown(f"<div style='color: #999; font-style: italic; padding: 8px 4px;'>— {empty_msg}</div>", unsafe_allow_html=True)

        # --- AUTOSCROLL ---
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

                    var tabs = parentDoc.querySelectorAll('button[role="tab"]');
                    var isTab2Active = tabs[1] && tabs[1].getAttribute('aria-selected') === 'true';

                    if (isTab2Active) {
                        safeScroll();
                    }

                    parentWin._tab2LastState = isTab2Active;

                    if (parentWin._tab2PollInterval) {
                        clearInterval(parentWin._tab2PollInterval);
                    }

                    parentWin._tab2PollInterval = setInterval(function() {
                        var tabs = parentDoc.querySelectorAll('button[role="tab"]');
                        if (!tabs[1]) return;
                        var isNowActive = tabs[1].getAttribute('aria-selected') === 'true';
                        if (isNowActive && parentWin._tab2LastState === false) {
                            safeScroll();
                        }
                        parentWin._tab2LastState = isNowActive;
                    }, 200);
                })();
            </script>
            """,
            height=0,
            width=0
        )
