import streamlit as st
import requests
import datetime
import pandas as pd
import uuid
import json
import io
import zipfile
import fitz
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

# Optional Google Sheets / Drive integration.
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build as google_build
    from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
except Exception:
    service_account = None
    google_build = None
    MediaIoBaseUpload = None
    MediaIoBaseDownload = None

from PIL import Image
from supabase import create_client

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader, simpleSplit


# =========================================================
# PAGE
# =========================================================

st.set_page_config(
    page_title="School Management",
    page_icon="🏫",
    layout="wide"
)


# =========================================================
# SUPABASE
# =========================================================

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_PUBLISHABLE_KEY"]

CREATE_USER = f"{URL}/functions/v1/Create-User"


# =========================================================
# SESSION-SAFE SUPABASE CLIENT
# =========================================================
# Create a fresh client for each Streamlit session/run instead of sharing
# one mutable authenticated client between users. This prevents one user's
# auth token from ever being applied to another user's requests.
def get_supabase_client():
    client = create_client(URL, KEY)

    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")

    if access_token and refresh_token:
        try:
            client.auth.set_session(
                access_token,
                refresh_token
            )
        except Exception:
            try:
                client.postgrest.auth(access_token)
            except Exception:
                pass
    elif access_token:
        try:
            client.postgrest.auth(access_token)
        except Exception:
            pass

    return client


# =========================================================
# SESSION
# =========================================================

for key in [
    "logged_in",
    "user",
    "profile",
    "access_token",
    "refresh_token"
]:
    if key not in st.session_state:
        st.session_state[key] = (
            False if key == "logged_in" else None
        )


# Each Streamlit user/session gets its own Supabase client.
# No authenticated client object is shared between users.
sb = get_supabase_client()



# =========================================================
# MARK FORMAT
# =========================================================
# Marks are rounded to a maximum of 2 decimal places, but unnecessary
# trailing zeros are never displayed: 88 -> 88, 88.5 -> 88.5, 88.25 -> 88.25.
def format_mark(value):
    try:
        number = round(float(value), 2)
        if number == int(number):
            return str(int(number))
        return f"{number:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value) if value is not None else ""


# =========================================================
# SAVE STATUS
# =========================================================
def mark_saved(key, values=None):
    st.session_state["_save_msg_" + key] = "Saved successfully."

def show_save_message(key):
    msg = st.session_state.pop("_save_msg_" + key, None)
    if msg:
        st.success("✅ " + msg)

# =========================================================
# ROLE-BASED DASHBOARD THEME
# =========================================================
ROLE_THEMES = {
    "SuperAdmin": {
        "bg": "#EAF7EE", "surface": "#FFFFFF", "accent": "#198754",
        "accent2": "#146C43", "soft": "#D1E7DD", "text": "#123524"
    },
    "Admin": {
        "bg": "#EAF2FF", "surface": "#FFFFFF", "accent": "#0D6EFD",
        "accent2": "#084298", "soft": "#CFE2FF", "text": "#102A43"
    },
    "Teacher": {
        "bg": "#FFF0F6", "surface": "#FFFFFF", "accent": "#D63384",
        "accent2": "#A61E4D", "soft": "#F7D6E6", "text": "#4A1230"
    },
    "Student": {
        "bg": "#ECECEC", "surface": "#FFFFFF", "accent": "#6C757D",
        "accent2": "#495057", "soft": "#D3D6D8", "text": "#212529"
    },
    "Parent": {
        "bg": "#F5EEFF", "surface": "#FFFFFF", "accent": "#7B2CBF",
        "accent2": "#5A189A", "soft": "#E9D8FD", "text": "#32143F"
    },
}

def get_active_theme_role():
    """
    Admin+Teacher has two working modes:
    - Admin-only work uses the Admin theme.
    - Teacher-only work uses the Teacher theme.
    All other roles keep their normal role theme.
    """
    role = (st.session_state.get("profile") or {}).get("role")

    if role == "Admin+Teacher":
        teacher_menu_items = {
            "🎓 Students",
            "📝 Marks",
            "📅 Attendance",
            "📄 Report Cards",
            "📊 Reports",
        }
        selected_menu = st.session_state.get("admin_dashboard_menu")
        if selected_menu in teacher_menu_items:
            return "Teacher"
        return "Admin"

    return role


def apply_role_theme():
    theme_role = get_active_theme_role()
    theme = ROLE_THEMES.get(theme_role)
    if not theme:
        return

    st.markdown(f"""<style>
    /* Main role theme */
    .stApp {{
        background: linear-gradient(180deg, {theme["bg"]} 0%, #FFFFFF 100%);
        color: {theme["text"]};
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {theme["accent2"]} 0%, {theme["accent"]} 100%);
    }}
    [data-testid="stSidebar"] * {{ color: #FFFFFF !important; }}

    /* Titles, headings and dividers follow the role colour */
    .stApp h1, .stApp h2, .stApp h3 {{
        color: {theme["accent2"]};
    }}
    .stApp hr {{ border-color: {theme["soft"]}; }}

    /* Navigation / radio buttons */
    div[role="radiogroup"] label {{
        border-radius: 10px;
        padding: 5px 9px;
    }}
    div[role="radiogroup"] label:hover {{
        background: {theme["soft"]};
    }}

    /* Buttons */
    .stButton > button {{
        border: 1px solid {theme["accent"]};
        color: {theme["accent2"]};
        border-radius: 10px;
        font-weight: 600;
        transition: all .15s ease;
    }}
    .stButton > button:hover {{
        background: {theme["accent"]};
        color: #FFFFFF;
        border-color: {theme["accent2"]};
    }}
    .stButton > button[kind="primary"] {{
        background: {theme["accent"]};
        color: #FFFFFF;
        border-color: {theme["accent"]};
    }}

    /* Inputs and select controls */
    .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color: {theme["accent"]} !important;
        box-shadow: 0 0 0 1px {theme["accent"]} !important;
    }}
    div[data-baseweb="select"] > div:focus-within {{
        border-color: {theme["accent"]} !important;
        box-shadow: 0 0 0 1px {theme["accent"]} !important;
    }}

    /* Cards / metrics */
    div[data-testid="stMetric"] {{
        background: {theme["surface"]};
        border: 1px solid {theme["soft"]};
        border-top: 4px solid {theme["accent"]};
        border-radius: 14px;
        padding: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }}
    .role-theme-card {{
        background: {theme["surface"]};
        border: 1px solid {theme["soft"]};
        border-left: 5px solid {theme["accent"]};
        border-radius: 14px;
        padding: 14px 16px;
        margin: 8px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,.05);
    }}

    /* Streamlit expanders */
    div[data-testid="stExpander"] {{
        border-color: {theme["soft"]};
        border-radius: 12px;
    }}

    /* Keep data tables/forms readable while the dashboard carries the role theme */
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {{
        border-radius: 10px;
    }}
    </style>""", unsafe_allow_html=True)


# =========================================================
# LOGOUT
# =========================================================

def logout():

    try:
        sb.auth.sign_out()
    except Exception:
        pass

    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.profile = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None

    st.rerun()


# =========================================================
# LOGIN
# =========================================================

def login():

    st.title("🏫 School Management System")

    email = st.text_input("Email")

    password = st.text_input(
        "Password",
        type="password"
    )

    if st.button(
        "🔐 Login",
        use_container_width=True
    ):

        if not email or not password:
            st.warning("Enter email and password.")
            return

        try:

            result = sb.auth.sign_in_with_password({
                "email": email.strip(),
                "password": password
            })

            if not result.user or not result.session:
                st.error("Login failed.")
                return

            st.session_state.user = result.user

            st.session_state.access_token = (
                result.session.access_token
            )

            st.session_state.refresh_token = (
                result.session.refresh_token
            )

            sb.postgrest.auth(
                result.session.access_token
            )

            profile = (
                sb.table("profiles")
                .select("*")
                .eq("id", result.user.id)
                .single()
                .execute()
                .data
            )

            if not profile:
                st.error("Profile not found.")
                return

            if profile.get("active") is False:

                st.error("Your account is inactive.")

                try:
                    sb.auth.sign_out()
                except Exception:
                    pass

                return

            st.session_state.profile = profile
            st.session_state.logged_in = True

            st.rerun()

        except Exception as e:

            st.error("Login failed.")
            st.code(str(e))


# =========================================================
# SCHOOL MANAGEMENT
# =========================================================

def schools():

    st.header("🏫 School Management")

    try:

        school_data = (
            sb.table("schools")
            .select("*")
            .order("created_at", desc=True)
            .execute()
            .data or []
        )

    except Exception as e:

        st.error("Could not load schools.")
        st.code(str(e))
        return

    with st.expander("➕ Add New School"):

        name = st.text_input(
            "School Name",
            key="school_name"
        )

        code = st.text_input(
            "School Code",
            key="school_code"
        )

        address = st.text_area(
            "Address",
            key="school_address"
        )

        if st.button(
            "Add School",
            use_container_width=True
        ):

            if not name.strip() or not code.strip():
                st.warning(
                    "School name and code are required."
                )
                return

            try:

                existing = (
                    sb.table("schools")
                    .select("id")
                    .eq("code", code.strip())
                    .execute()
                    .data or []
                )

                if existing:
                    st.error("School code already exists.")
                    return

                (
                    sb.table("schools")
                    .insert({
                        "name": name.strip(),
                        "code": code.strip(),
                        "address": address.strip(),
                        "active": True
                    })
                    .execute()
                )

                st.success("School added successfully.")
                st.rerun()

            except Exception as e:

                st.error("Could not add school.")
                st.code(str(e))

    st.divider()

    for school in school_data:

        school_id = school["id"]
        active = school.get("active", True)

        with st.container(border=True):

            c1, c2, c3 = st.columns([3, 2, 1])

            with c1:

                st.markdown(
                    f"### 🏫 {school.get('name', '')}"
                )

                st.caption(
                    f"Code: {school.get('code', '')}"
                )

                st.caption(
                    school.get("address") or "No address"
                )

            with c2:

                if active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with c3:

                if st.button(
                    "Deactivate" if active else "Activate",
                    key=f"school_status_{school_id}"
                ):

                    try:

                        (
                            sb.table("schools")
                            .update({
                                "active": not active
                            })
                            .eq("id", school_id)
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

            with st.expander("✏️ Edit"):

                edit_name = st.text_input(
                    "Name",
                    value=school.get("name", ""),
                    key=f"school_edit_name_{school_id}"
                )

                edit_code = st.text_input(
                    "Code",
                    value=school.get("code", ""),
                    key=f"school_edit_code_{school_id}"
                )

                edit_address = st.text_area(
                    "Address",
                    value=school.get("address", ""),
                    key=f"school_edit_address_{school_id}"
                )

                save_key = f"school_save_{school_id}"
                show_save_message(save_key)
                if st.button(
                    "Save",
                    key=save_key,
                ):

                    try:

                        duplicate = (
                            sb.table("schools")
                            .select("id")
                            .eq("code", edit_code.strip())
                            .neq("id", school_id)
                            .execute()
                            .data or []
                        )

                        if duplicate:
                            st.error(
                                "School code already exists."
                            )
                            continue

                        (
                            sb.table("schools")
                            .update({
                                "name": edit_name.strip(),
                                "code": edit_code.strip(),
                                "address": edit_address.strip()
                            })
                            .eq("id", school_id)
                            .execute()
                        )

                        mark_saved(save_key)
                        st.success("School updated.")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))


# =========================================================
# USER MANAGEMENT
# =========================================================

def users():

    st.header("👥 User Management")

    try:
        school_data = (
            sb.table("schools")
            .select("id,name,code,active")
            .order("name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error(str(e))
        return

    active_schools = [x for x in school_data if x.get("active", True)]

    if not active_schools:
        st.warning("Create an active school first.")
        return

    school_map = {
        f"{x['name']} ({x['code']})": x["id"]
        for x in active_schools
    }

    # -----------------------------------------------------
    # SUPERADMIN QUICK ADD SCHOOL
    # -----------------------------------------------------
    if st.session_state.profile.get("role") == "SuperAdmin":
        with st.expander("🏫 ➕ Add New School", expanded=False):
            quick_school_name = st.text_input(
                "School Name",
                key="quick_school_name"
            )
            quick_school_code = st.text_input(
                "School Code",
                key="quick_school_code"
            )
            quick_school_address = st.text_area(
                "Address",
                key="quick_school_address"
            )

            if st.button(
                "➕ Add School",
                use_container_width=True,
                key="quick_add_school_button"
            ):
                if not quick_school_name.strip() or not quick_school_code.strip():
                    st.warning("School Name and School Code are required.")
                else:
                    try:
                        duplicate = (
                            sb.table("schools")
                            .select("id")
                            .eq("code", quick_school_code.strip())
                            .execute()
                            .data or []
                        )
                        if duplicate:
                            st.error("School code already exists.")
                        else:
                            sb.table("schools").insert({
                                "name": quick_school_name.strip(),
                                "code": quick_school_code.strip(),
                                "address": quick_school_address.strip(),
                                "active": True
                            }).execute()
                            st.success("✅ School added successfully.")
                            st.rerun()
                    except Exception as e:
                        st.error("Could not add school.")
                        st.code(str(e))

    # -----------------------------------------------------
    # CREATE USER
    # -----------------------------------------------------
    with st.expander("➕ Create User", expanded=True):

        # SuperAdmin can create users in any active school.
        # Admin can create users only inside their own school.
        if st.session_state.profile.get("role") in ["Admin", "Admin+Teacher"]:
            admin_school_id = str(st.session_state.profile.get("school_id") or "")
            admin_school_label = next(
                (
                    label for label, sid in school_map.items()
                    if str(sid) == admin_school_id
                ),
                None
            )

            if not admin_school_label:
                st.error("Your Admin account is not linked to an active school.")
                return

            st.info(f"🏫 School: **{admin_school_label}**")
            selected_school = admin_school_label
        else:
            selected_school = st.selectbox(
                "School",
                list(school_map.keys()),
                key="create_user_school"
            )

        name = st.text_input("Full Name", key="create_user_name")
        email = st.text_input("Email", key="create_user_email")
        password = st.text_input(
            "Password",
            type="password",
            key="create_user_password"
        )

        creator_role = st.session_state.profile.get("role")
        create_role_options = ["Admin", "Teacher", "Student", "Parent"]

        # Only SuperAdmin/Admin may create a new Admin+Teacher.
        if creator_role in ["SuperAdmin", "Admin"]:
            create_role_options.insert(1, "Admin+Teacher")

        role = st.selectbox(
            "Role",
            create_role_options,
            key="create_user_role"
        )

        if st.button(
            "👤 Create User",
            use_container_width=True,
            key="create_user_button"
        ):

            if not name.strip():
                st.warning("Enter full name.")
                return

            if not email.strip():
                st.warning("Enter email.")
                return

            if not password:
                st.warning("Enter password.")
                return

            if len(password) < 6:
                st.warning("Password must be at least 6 characters.")
                return

            token = st.session_state.access_token

            if not token:
                st.error("Session expired. Logout and login again.")
                return

            # Only SuperAdmin/Admin are authorized to assign the
            # Admin+Teacher role. The Edge Function enforces this too.
            if role == "Admin+Teacher" and creator_role not in ["SuperAdmin", "Admin"]:
                st.error("Only SuperAdmin or Admin can create an Admin+Teacher user.")
                return

            # SuperAdmin has no Admin+Teacher limit.
            # Each school can have at most 3 ACTIVE Admin+Teacher users
            # created/managed by its Admin. The limit is school-wide.
            if role == "Admin+Teacher" and creator_role == "Admin":
                try:
                    hybrid_count = (
                        sb.table("profiles")
                        .select("id", count="exact")
                        .eq("school_id", school_map[selected_school])
                        .eq("role", "Admin+Teacher")
                        .eq("active", True)
                        .execute()
                        .count or 0
                    )
                    if hybrid_count >= 3:
                        st.error("This school already has 3 active Admin+Teacher users. The Admin+Teacher limit is 3 per school.")
                        return
                except Exception as e:
                    st.error("Could not verify the Admin + Teacher limit.")
                    st.code(str(e))
                    return

            try:
                response = requests.post(
                    CREATE_USER,
                    json={
                        "email": email.strip(),
                        "password": password,
                        "full_name": name.strip(),
                        "role": role,
                        "school_id": school_map[selected_school],
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": KEY,
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )

                if 200 <= response.status_code < 300:
                    st.success("✅ User created successfully.")
                    st.rerun()
                else:
                    st.error(
                        f"Create-User failed: HTTP {response.status_code}"
                    )
                    st.code(response.text)

            except Exception as e:
                st.error("Could not connect to Create-User.")
                st.code(str(e))

    st.divider()
    st.subheader("📋 Existing Users")

    try:
        user_query = (
            sb.table("profiles")
            .select("id,email,full_name,role,active,school_id")
        )

        # Admin must only load users belonging to their own school.
        if st.session_state.profile.get("role") == "Admin":
            user_query = user_query.eq(
                "school_id",
                st.session_state.profile.get("school_id")
            )

        user_data = (
            user_query
            .order("full_name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error(str(e))
        return

    school_names = {
        str(x["id"]): x["name"]
        for x in school_data
    }

    # -----------------------------------------------------
    # TEACHER ASSIGNMENT DATA
    # -----------------------------------------------------
    def load_teacher_assignments(teacher_id):
        try:
            return (
                sb.table("teacher_subject_assignments")
                .select(
                    "id,school_id,teacher_id,class_id,subject_id"
                )
                .eq("teacher_id", teacher_id)
                .eq("school_id", school_map[selected_school])
                .execute()
                .data or []
            )
        except Exception:
            return []

    # -----------------------------------------------------
    # USER LIST FILTER / SELECT
    # -----------------------------------------------------
    role = st.session_state.profile.get("role")

    if role == "SuperAdmin":
        filter_school_options = ["All Schools"] + list(school_map.keys())
        filter_school = st.selectbox(
            "🏫 Select School",
            filter_school_options,
            key="users_filter_school"
        )
    else:
        filter_school = list(school_map.keys())[0]

    filter_role = st.selectbox(
        "👤 Select Role",
        ["All Roles", "Admin", "Admin+Teacher", "Teacher", "Student", "Parent"],
        key="users_filter_role"
    )

    filtered_users = list(user_data)

    if role == "SuperAdmin" and filter_school != "All Schools":
        selected_filter_school_id = school_map[filter_school]
        filtered_users = [
            u for u in filtered_users
            if str(u.get("school_id") or "") == str(selected_filter_school_id)
        ]
    elif role in ["Admin", "Admin+Teacher"]:
        admin_school_id = st.session_state.profile.get("school_id")
        filtered_users = [
            u for u in filtered_users
            if str(u.get("school_id") or "") == str(admin_school_id)
        ]

    if filter_role != "All Roles":
        filtered_users = [
            u for u in filtered_users
            if u.get("role") == filter_role
        ]

    user_labels = {}
    for u in filtered_users:
        label = (
            f"{u.get('full_name') or 'User'}"
            f" — {u.get('email') or '-'}"
            f" — {u.get('role') or '-'}"
        )
        user_labels[label] = u

    if not user_labels:
        st.info("No users found for the selected filters.")
        return

    select_all_key = (
        "superadmin_user_select_all"
        if role == "SuperAdmin"
        else "admin_user_select_all"
    )
    selected_users_key = (
        "superadmin_selected_users"
        if role == "SuperAdmin"
        else "admin_selected_users"
    )
    previous_key = selected_users_key + "_previous"

    select_all_users = st.checkbox(
        "☑️ Select All Users",
        key=select_all_key
    )

    previous_select_all = st.session_state.get(previous_key, False)

    if select_all_users and not previous_select_all:
        st.session_state[selected_users_key] = list(user_labels.keys())
    elif not select_all_users and previous_select_all:
        st.session_state[selected_users_key] = []

    st.session_state[previous_key] = select_all_users

    selected_user_labels = st.multiselect(
        "👥 Select Users",
        list(user_labels.keys()),
        placeholder="Select one or more users",
        key=selected_users_key
    )

    selected_users = [
        user_labels[label]
        for label in selected_user_labels
        if label in user_labels
    ]

    st.caption(
        f"Selected {len(selected_users)} of {len(filtered_users)} user(s)."
    )

    if not selected_users:
        st.info("Select user(s) from the dropdown above to modify or manage them.")
        return

    # -----------------------------------------------------
    # MODIFY USERS
    # -----------------------------------------------------
    for user in selected_users:

        user_id = user["id"]
        active = user.get("active", True)

        with st.container(border=True):

            c1, c2, c3 = st.columns([3, 2, 1])

            with c1:
                st.write(
                    user.get("full_name")
                    or user.get("email")
                )
                st.caption(user.get("email"))

            with c2:
                st.write(f"Role: **{user.get('role')}**")
                st.caption(
                    school_names.get(
                        str(user.get("school_id")),
                        "No school"
                    )
                )

            with c3:
                if st.button(
                    "Deactivate" if active else "Activate",
                    key=f"user_status_{user_id}"
                ):
                    try:
                        # Re-activating an Admin+Teacher must also respect
                        # the school-wide maximum of 3 active accounts.
                        if (
                            not active
                            and user.get("role") == "Admin+Teacher"
                            and role == "Admin"
                        ):
                            hybrid_count = (
                                sb.table("profiles")
                                .select("id", count="exact")
                                .eq("school_id", user.get("school_id"))
                                .eq("role", "Admin+Teacher")
                                .eq("active", True)
                                .execute()
                                .count or 0
                            )
                            if hybrid_count >= 3:
                                st.error("This school already has 3 active Admin+Teacher users. Deactivate one before re-activating another.")
                                continue

                        (
                            sb.table("profiles")
                            .update({"active": not active})
                            .eq("id", user_id)
                            .execute()
                        )
                        st.success("✅ User status saved successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error("Could not update user status.")
                        st.code(str(e))

            with st.expander("✏️ Modify User"):

                edit_name = st.text_input(
                    "Full Name",
                    value=user.get("full_name") or "",
                    key=f"edit_user_name_{user_id}"
                )

                current_role = user.get("role")

                # Role-change rules:
                # SuperAdmin: can change to any role, across every school.
                # Admin:
                #   - can create/promote users to Admin+Teacher, subject to
                #     the school-wide maximum of 3 ACTIVE Admin+Teacher users.
                #   - can reverse Admin+Teacher only to Admin or Teacher.
                # Admin+Teacher: cannot change/reverse anyone's role.
                if role == "SuperAdmin":
                    role_options = [
                        "Admin",
                        "Admin+Teacher",
                        "Teacher",
                        "Student",
                        "Parent"
                    ]
                    edit_role = st.selectbox(
                        "Role",
                        role_options,
                        index=(
                            role_options.index(current_role)
                            if current_role in role_options
                            else 0
                        ),
                        key=f"edit_user_role_{user_id}"
                    )

                elif role == "Admin":
                    if current_role == "Admin+Teacher":
                        # Admin can reverse an Admin+Teacher only to Admin
                        # or Teacher (or leave it unchanged).
                        role_options = [
                            "Admin+Teacher",
                            "Admin",
                            "Teacher"
                        ]
                    else:
                        role_options = [
                            "Admin",
                            "Admin+Teacher",
                            "Teacher",
                            "Student",
                            "Parent"
                        ]

                    edit_role = st.selectbox(
                        "Role",
                        role_options,
                        index=(
                            role_options.index(current_role)
                            if current_role in role_options
                            else 0
                        ),
                        key=f"edit_user_role_{user_id}"
                    )

                elif role == "Admin+Teacher":
                    # Admin+Teacher is NOT allowed to reverse or otherwise
                    # change another user's role.
                    edit_role = st.selectbox(
                        "Role",
                        [current_role],
                        index=0,
                        disabled=True,
                        key=f"edit_user_role_{user_id}"
                    )

                else:
                    edit_role = current_role

                current_school_id = str(user.get("school_id") or "")
                school_labels = list(school_map.keys())

                current_school_label = next(
                    (
                        label
                        for label, sid in school_map.items()
                        if str(sid) == current_school_id
                    ),
                    school_labels[0]
                )

                # Admin cannot move a user to another school.
                if role in ["Admin", "Admin+Teacher"]:
                    admin_school_id = str(
                        st.session_state.profile.get("school_id") or ""
                    )
                    if current_school_id != admin_school_id:
                        st.error("This user does not belong to your school.")
                        continue

                    st.info(
                        f"🏫 School: **{current_school_label}** "
                        "(Admin can manage users only in this school.)"
                    )
                    edit_school_label = current_school_label
                else:
                    edit_school_label = st.selectbox(
                        "School",
                        school_labels,
                        index=school_labels.index(current_school_label),
                        key=f"edit_user_school_{user_id}"
                    )

                st.text_input(
                    "Email",
                    value=user.get("email") or "",
                    disabled=True,
                    key=f"edit_user_email_{user_id}"
                )

                st.caption(
                    "Email is the login email and is not changed here."
                )

                # -----------------------------------------
                # PARENT → STUDENT LINKING
                # -----------------------------------------
                selected_parent_student_ids = []
                if edit_role == "Parent":
                    edit_school_id = school_map[edit_school_label]

                    try:
                        parent_student_rows = (
                            sb.table("students")
                            .select(
                                "id,name,admission_no,class_name,section,active"
                            )
                            .eq("school_id", edit_school_id)
                            .eq("active", True)
                            .order("name")
                            .execute()
                            .data or []
                        )
                    except Exception:
                        parent_student_rows = []

                    try:
                        current_parent_links = (
                            sb.table("parent_student_links")
                            .select("student_id")
                            .eq("parent_id", user_id)
                            .execute()
                            .data or []
                        )
                    except Exception:
                        current_parent_links = []

                    current_parent_student_ids = {
                        str(x.get("student_id"))
                        for x in current_parent_links
                        if x.get("student_id")
                    }

                    parent_student_options = {}
                    for student_row in parent_student_rows:
                        label = (
                            f"{student_row.get('name') or 'Student'}"
                            f" — Admission: {student_row.get('admission_no') or '-'}"
                            f" — Class: {student_row.get('class_name') or '-'}"
                            f" — Section: {student_row.get('section') or '-'}"
                        )
                        parent_student_options[label] = student_row["id"]

                    selected_parent_student_labels = st.multiselect(
                        "👨‍👩‍👧 Parent — Linked Student(s)",
                        list(parent_student_options.keys()),
                        default=[
                            label
                            for label, student_id_value in parent_student_options.items()
                            if str(student_id_value) in current_parent_student_ids
                        ],
                        key=f"parent_student_links_{user_id}"
                    )

                    selected_parent_student_ids = [
                        parent_student_options[label]
                        for label in selected_parent_student_labels
                        if label in parent_student_options
                    ]

                    st.caption(
                        "Select one or multiple students/children for this Parent. "
                        "The Parent will only see the linked students' permitted data."
                    )

                # -----------------------------------------
                # TEACHER CLASS / SUBJECT ASSIGNMENTS
                # -----------------------------------------
                if edit_role in ["Teacher", "Admin+Teacher"]:

                    edit_school_id = school_map[edit_school_label]

                    try:
                        edit_classes = (
                            sb.table("classes")
                            .select(
                                "id,class_name,section,academic_year,active"
                            )
                            .eq("school_id", edit_school_id)
                            .eq("active", True)
                            .order("class_name")
                            .order("section")
                            .execute()
                            .data or []
                        )
                    except Exception:
                        edit_classes = []

                    class_labels = {}
                    for cl in edit_classes:
                        label = (
                            f"{cl.get('class_name') or '-'}"
                            f" | Section: {cl.get('section') or '-'}"
                            f" | {cl.get('academic_year') or '-'}"
                        )
                        class_labels[label] = cl

                    # Class Teacher assignments are stored on classes.
                    if class_labels:
                        try:
                            class_teacher_rows = (
                                sb.table("classes")
                                .select(
                                    "id,class_name,section,academic_year"
                                )
                                .eq(
                                    "school_id",
                                    edit_school_id
                                )
                                .eq(
                                    "class_teacher_id",
                                    user_id
                                )
                                .eq("active", True)
                                .execute()
                                .data or []
                            )
                        except Exception:
                            class_teacher_rows = []

                        current_ct_ids = {
                            str(x["id"])
                            for x in class_teacher_rows
                        }

                        selected_ct_labels = st.multiselect(
                            "👨‍🏫 Class Teacher — Assigned Classes",
                            list(class_labels.keys()),
                            default=[
                                label
                                for label, cl in class_labels.items()
                                if str(cl["id"]) in current_ct_ids
                            ],
                            key=f"class_teacher_assign_{user_id}"
                        )

                        st.caption(
                            "A teacher can be Class Teacher of multiple classes. "
                            "Only Admin can change these assignments."
                        )

                    # Subject-teacher assignments.
                    try:
                        assignment_rows = (
                            sb.table("teacher_subject_assignments")
                            .select(
                                "id,class_id,subject_id"
                            )
                            .eq("teacher_id", user_id)
                            .eq("school_id", edit_school_id)
                            .execute()
                            .data or []
                        )
                    except Exception:
                        assignment_rows = []

                    assignment_ids = {
                        (
                            str(x.get("class_id")),
                            str(x.get("subject_id"))
                        )
                        for x in assignment_rows
                    }

                    subject_options = {}
                    if class_labels:
                        for cl_label, cl in class_labels.items():
                            try:
                                subjects_for_class = (
                                    sb.table("subjects")
                                    .select(
                                        "id,name,subject_name,class_id,active"
                                    )
                                    .eq(
                                        "school_id",
                                        edit_school_id
                                    )
                                    .eq(
                                        "class_id",
                                        cl["id"]
                                    )
                                    .eq("active", True)
                                    .order("subject_name")
                                    .execute()
                                    .data or []
                                )
                            except Exception:
                                subjects_for_class = []

                            for sub in subjects_for_class:
                                sub_name = (
                                    sub.get("subject_name")
                                    or sub.get("name")
                                    or "Subject"
                                )
                                label = (
                                    f"{cl_label} → {sub_name}"
                                )
                                subject_options[label] = (
                                    cl["id"],
                                    sub["id"]
                                )

                    current_assignment_labels = [
                        label
                        for label, ids in subject_options.items()
                        if (
                            str(ids[0]),
                            str(ids[1])
                        ) in assignment_ids
                    ]

                    selected_subject_assignments = st.multiselect(
                        "📖 Subject Teacher — Class + Subject Assignments",
                        list(subject_options.keys()),
                        default=current_assignment_labels,
                        key=f"subject_teacher_assign_{user_id}"
                    )

                    st.caption(
                        "One teacher can teach many classes and many subjects. "
                        "Each permission is an exact Class + Subject combination."
                    )

                save_key = f"save_user_{user_id}"
                show_save_message(save_key)
                if st.button(
                    "💾 Save User Changes",
                    key=save_key,
                    use_container_width=True,
                ):

                    if not edit_name.strip():
                        st.warning("Full Name is required.")
                        continue

                    try:
                        # Enforce role-change permissions server-side in the
                        # Streamlit layer as well as in the visible controls.
                        if (
                            current_role == "Admin+Teacher"
                            and edit_role != "Admin+Teacher"
                            and role not in ["SuperAdmin", "Admin"]
                        ):
                            st.error(
                                "Admin+Teacher cannot change or reverse user roles."
                            )
                            continue

                        # Only Admin and SuperAdmin may assign Admin+Teacher.
                        if (
                            edit_role == "Admin+Teacher"
                            and current_role != "Admin+Teacher"
                            and role not in ["SuperAdmin", "Admin"]
                        ):
                            st.error(
                                "Only Admin or SuperAdmin can assign the Admin+Teacher role."
                            )
                            continue

                        # An Admin can reverse Admin+Teacher only to Admin or
                        # Teacher. No other role is allowed in that transition.
                        if (
                            current_role == "Admin+Teacher"
                            and role == "Admin"
                            and edit_role not in ["Admin+Teacher", "Admin", "Teacher"]
                        ):
                            st.error(
                                "Admin can reverse Admin+Teacher only to Admin or Teacher."
                            )
                            continue

                        # Admin+Teacher cannot reverse or change roles at all.
                        if role == "Admin+Teacher" and edit_role != current_role:
                            st.error(
                                "Admin+Teacher is not authorized to change user roles."
                            )
                            continue

                        # Admin: maximum 3 ACTIVE Admin+Teacher users per school.
                        if (
                            edit_role == "Admin+Teacher"
                            and current_role != "Admin+Teacher"
                            and role == "Admin"
                        ):
                            target_school_id = school_map[edit_school_label]
                            hybrid_count = (
                                sb.table("profiles")
                                .select("id", count="exact")
                                .eq("school_id", target_school_id)
                                .eq("role", "Admin+Teacher")
                                .eq("active", True)
                                .execute()
                                .count or 0
                            )
                            if hybrid_count >= 3:
                                st.error(
                                    "This school already has 3 active Admin+Teacher users. "
                                    "The Admin+Teacher limit is 3 per school."
                                )
                                continue

                        (
                            sb.table("profiles")
                            .update({
                                "full_name": edit_name.strip(),
                                "role": edit_role,
                                "school_id": school_map[edit_school_label],
                            })
                            .eq("id", user_id)
                            .execute()
                        )

                        # Save Parent → Student links.
                        if edit_role == "Parent":
                            edit_school_id = school_map[edit_school_label]

                            (
                                sb.table("parent_student_links")
                                .delete()
                                .eq("parent_id", user_id)
                                .execute()
                            )

                            new_parent_links = [
                                {
                                    "parent_id": user_id,
                                    "student_id": student_id_value
                                }
                                for student_id_value in selected_parent_student_ids
                            ]

                            if new_parent_links:
                                (
                                    sb.table("parent_student_links")
                                    .insert(new_parent_links)
                                    .execute()
                                )

                        # Save teacher assignments only when the user is a Teacher.
                        if edit_role in ["Teacher", "Admin+Teacher"]:

                            edit_school_id = school_map[edit_school_label]

                            # Class Teacher: first clear this teacher's
                            # existing assignments, then apply the selected ones.
                            (
                                sb.table("classes")
                                .update({
                                    "class_teacher_id": None,
                                    "updated_at":
                                        datetime.datetime.now(
                                            datetime.timezone.utc
                                        ).isoformat()
                                })
                                .eq("school_id", edit_school_id)
                                .eq("class_teacher_id", user_id)
                                .execute()
                            )

                            for label in selected_ct_labels:
                                cl = class_labels[label]
                                (
                                    sb.table("classes")
                                    .update({
                                        "class_teacher_id": user_id,
                                        "updated_at":
                                            datetime.datetime.now(
                                                datetime.timezone.utc
                                            ).isoformat()
                                    })
                                    .eq("id", cl["id"])
                                    .execute()
                                )

                            # Subject Teacher: replace the teacher's exact
                            # Class + Subject assignment set.
                            (
                                sb.table("teacher_subject_assignments")
                                .delete()
                                .eq("teacher_id", user_id)
                                .eq("school_id", edit_school_id)
                                .execute()
                            )

                            new_assignments = []
                            for label in selected_subject_assignments:
                                class_id_value, subject_id_value = (
                                    subject_options[label]
                                )
                                new_assignments.append({
                                    "school_id": edit_school_id,
                                    "teacher_id": user_id,
                                    "class_id": class_id_value,
                                    "subject_id": subject_id_value
                                })

                            if new_assignments:
                                (
                                    sb.table(
                                        "teacher_subject_assignments"
                                    )
                                    .insert(new_assignments)
                                    .execute()
                                )

                        else:
                            # If the role is changed away from Teacher,
                            # remove all teacher permissions.
                            (
                                sb.table("classes")
                                .update({
                                    "class_teacher_id": None,
                                    "updated_at":
                                        datetime.datetime.now(
                                            datetime.timezone.utc
                                        ).isoformat()
                                })
                                .eq("class_teacher_id", user_id)
                                .execute()
                            )

                            (
                                sb.table("teacher_subject_assignments")
                                .delete()
                                .eq("teacher_id", user_id)
                                .execute()
                            )

                        mark_saved(save_key)
                        st.session_state["saved_user_changes"] = True
                        st.rerun()

                    except Exception as e:
                        st.error("Could not save user changes.")
                        st.code(str(e))

    if st.session_state.pop("saved_user_changes", False):
        st.success("✅ User changes saved successfully.")


# =========================================================
# GET ACTIVE SCHOOL
# =========================================================

# =========================================================
# EXAM / ASSESSMENT SETTINGS
# =========================================================

def get_exam_assessments(school_id, active_only=True):
    try:
        query = sb.table("exam_assessments").select(
            "id,school_id,name,active,created_at"
        ).eq("school_id", school_id).order("name")
        if active_only:
            query = query.eq("active", True)
        return query.execute().data or []
    except Exception:
        return []


def exam_assessment_settings():
    st.header("📝 Exam / Assessment Settings")
    role = st.session_state.profile.get("role")
    if role not in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        st.error("Only Admin can manage Exam / Assessment names.")
        return

    school_id = get_selected_school("exam_settings_school")
    if not school_id:
        return

    exams = get_exam_assessments(school_id, active_only=False)

    with st.expander("➕ Add Exam / Assessment", expanded=True):
        new_name = st.text_input(
            "Exam / Assessment Name",
            placeholder="Example: PT1, Half Yearly, Annual",
            key="new_exam_assessment_name"
        ).strip()

        save_key = "save_exam_assessment"
        show_save_message(save_key)
        if st.button("💾 Save Exam / Assessment", type="primary",
                     use_container_width=True, key=save_key,
                     ):
            if not new_name:
                st.warning("Enter an Exam / Assessment name.")
                return
            if any(
                str(x.get("name") or "").strip().lower() == new_name.lower()
                and x.get("active", True) for x in exams
            ):
                st.warning("This Exam / Assessment already exists.")
                return
            try:
                sb.table("exam_assessments").insert({
                    "school_id": school_id, "name": new_name, "active": True
                }).execute()
                mark_saved(save_key)
                st.success("Exam / Assessment saved successfully.")
                st.rerun()
            except Exception as e:
                st.error("Could not save Exam / Assessment.")
                st.code(str(e))

    st.subheader("Existing Exam / Assessments")
    for exam in exams:
        exam_id = exam["id"]
        active = exam.get("active", True)
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"**{exam.get('name', '')}**")
                st.caption("ACTIVE" if active else "INACTIVE")
            with c2:
                if st.button(
                    "Deactivate" if active else "Activate",
                    key=f"exam_status_{exam_id}"
                ):
                    try:
                        sb.table("exam_assessments").update(
                            {"active": not active}
                        ).eq("id", exam_id).execute()
                        st.success("Saved successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error("Could not update Exam / Assessment.")
                        st.code(str(e))


def get_selected_school(key_prefix):

    profile = st.session_state.profile

    role = profile.get("role")
    school_id = profile.get("school_id")

    if role == "SuperAdmin":

        try:

            schools_data = (
                sb.table("schools")
                .select("id,name,code,active")
                .order("name")
                .execute()
                .data or []
            )

        except Exception as e:

            st.error("Could not load schools.")
            st.code(str(e))
            return None

        active_schools = [
            s for s in schools_data
            if s.get("active", True)
        ]

        if not active_schools:
            st.warning("Create an active school first.")
            return None

        school_map = {
            f"{s['name']} ({s['code']})": s["id"]
            for s in active_schools
        }

        selected_school = st.selectbox(
            "🏫 Select School",
            list(school_map.keys()),
            key=key_prefix
        )

        return school_map[selected_school]

    if not school_id:

        st.error(
            "Your account is not assigned to a school."
        )
        return None

    try:

        school_info = (
            sb.table("schools")
            .select("name,code")
            .eq("id", school_id)
            .maybe_single()
            .execute()
            .data
        )

        if school_info:

            st.info(
                f"🏫 {school_info['name']} "
                f"({school_info['code']})"
            )

    except Exception:
        pass

    return school_id


# =========================================================
# STORAGE HELPER
# =========================================================

def upload_student_file(
    school_id,
    student_id,
    uploaded_file,
    folder,
    allowed_extensions,
    min_kb=None,
    max_kb=None
):

    if not uploaded_file:
        return None

    extension = (
        uploaded_file.name
        .split(".")[-1]
        .lower()
    )

    if extension not in allowed_extensions:
        raise Exception("Invalid file type.")

    file_bytes = uploaded_file.getvalue()
    file_size_kb = len(file_bytes) / 1024

    if min_kb is not None and file_size_kb < min_kb:
        raise Exception(
            f"File must be at least {min_kb} KB."
        )

    if max_kb is not None and file_size_kb > max_kb:
        raise Exception(
            f"File must not exceed {max_kb} KB."
        )

    unique_name = (
        f"{uuid.uuid4().hex}.{extension}"
    )

    storage_path = (
        f"{school_id}/"
        f"students/"
        f"{student_id}/"
        f"{folder}/"
        f"{unique_name}"
    )

    content_type_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "pdf": "application/pdf"
    }

    (
        sb.storage
        .from_("school-assets")
        .upload(
            storage_path,
            file_bytes,
            file_options={
                "content-type":
                    content_type_map.get(
                        extension,
                        "application/octet-stream"
                    ),
                "upsert": "true"
            }
        )
    )

    return storage_path


# =========================================================
# STUDENT MANAGEMENT
# =========================================================

def make_student_records_excel(student_rows, selected_fields):
    """Create an Excel workbook containing only the fields selected by the user."""
    field_map = {
        "Student ID": "id",
        "School ID": "school_id",
        "User ID": "user_id",
        "Student Name": "name",
        "Admission No.": "admission_no",
        "Class": "class_name",
        "Section": "section",
        "Date of Birth": "date_of_birth",
        "Gender": "gender",
        "Father Name": "father_name",
        "Mother Name": "mother_name",
        "Parent Phone": "parent_phone",
        "Address": "address",
        "Remarks": "remarks",
        "Photo Path": "photo_path",
        "Teacher Signature Path": "teacher_signature_path",
        "Principal Signature Path": "principal_signature_path",
        "Active": "active",
        "Created At": "created_at",
        "Updated At": "updated_at",
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Student Records"
    ws.append(selected_fields)

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    selected_columns = [field_map[x] for x in selected_fields]

    for row in student_rows:
        ws.append([
            row.get(column, "") if row.get(column, "") is not None else ""
            for column in selected_columns
        ])

    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions

    widths = {
        "Student ID": 38, "School ID": 38, "User ID": 38,
        "Student Name": 25, "Admission No.": 18, "Class": 12,
        "Section": 12, "Date of Birth": 16, "Gender": 12,
        "Father Name": 24, "Mother Name": 24, "Parent Phone": 18,
        "Address": 40, "Photo Path": 45, "Teacher Signature Path": 45,
        "Principal Signature Path": 45, "Active": 12,
        "Created At": 24, "Updated At": 24,
    }

    from openpyxl.utils import get_column_letter
    for index, field in enumerate(selected_fields, start=1):
        ws.column_dimensions[get_column_letter(index)].width = widths.get(field, 20)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def students():

    st.header("🎓 Student Management")

    role = st.session_state.profile.get("role")

    school_id = get_selected_school(
        "student_selected_school"
    )

    if not school_id:
        return

    # Teachers can only view/change students belonging to classes
    # where they are assigned as the Class Teacher.
    assigned_class_keys = None
    if role == "Teacher":
        try:
            assigned_classes = (
                sb.table("classes")
                .select("id,class_name,section,class_teacher_id,active")
                .eq("school_id", school_id)
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .execute()
                .data or []
            )
            assigned_class_keys = {
                (
                    str(x.get("class_name") or "").strip().lower(),
                    str(x.get("section") or "").strip().lower()
                )
                for x in assigned_classes
            }
            assigned_class_keys.discard(("", ""))

            if not assigned_class_keys:
                st.info("No class is assigned to you as Class Teacher yet.")
                return

            st.success(
                f"Assigned Class(es): {len(assigned_class_keys)}. "
                "You have full control over students in these classes except deleting students."
            )
        except Exception as e:
            st.error("Could not load your assigned classes.")
            st.code(str(e))
            return

    st.divider()

    try:

        student_users = (
            sb.table("profiles")
            .select("id,email,full_name")
            .eq("role", "Student")
            .eq("school_id", school_id)
            .eq("active", True)
            .order("full_name")
            .execute()
            .data or []
        )

    except Exception:

        student_users = []

    user_options = {"Not linked": None}

    for user in student_users:

        label = (
            f"{user.get('full_name') or 'Student'} "
            f"— {user.get('email')}"
        )

        user_options[label] = user["id"]

    # -----------------------------------------------------
    # ADD STUDENT
    # -----------------------------------------------------

    with st.expander("➕ Add New Student"):

        name = st.text_input(
            "Student Name",
            key="student_add_name"
        )

        admission_no = st.text_input(
            "Admission No.",
            key="student_add_admission"
        )

        class_name = st.text_input(
            "Class",
            key="student_add_class"
        )

        section = st.text_input(
            "Section",
            key="student_add_section"
        )

        date_of_birth = st.date_input(
            "Date of Birth",
            value=datetime.date(2010, 1, 1),
            key="student_add_date_of_birth"
        )

        gender = st.selectbox(
            "Gender",
            ["Male", "Female", "Other"],
            key="student_add_gender"
        )

        father_name = st.text_input(
            "Father Name",
            key="student_add_father_name"
        )

        mother_name = st.text_input(
            "Mother Name",
            key="student_add_mother_name"
        )

        parent_phone = st.text_input(
            "Parent Phone",
            key="student_add_parent_phone"
        )

        address = st.text_area(
            "Address",
            key="student_add_address"
        )

        remarks = st.text_area(
            "Remarks",
            key="student_add_remarks"
        )

        student_photo = st.file_uploader(
            "📷 Student Photo",
            type=["jpg", "jpeg", "png"],
            help="Photo must be between 10 KB and 200 KB.",
            key="student_add_photo"
        )

        if student_photo:

            photo_size_kb = student_photo.size / 1024

            if 10 <= photo_size_kb <= 200:

                st.success(
                    f"Photo size: {photo_size_kb:.1f} KB ✓"
                )

                st.image(
                    student_photo,
                    width=150
                )

            else:

                st.error(
                    f"Photo size is {photo_size_kb:.1f} KB. "
                    "It must be between 10 KB and 200 KB."
                )

        selected_user = st.selectbox(
            "🔗 Student Login Account",
            list(user_options.keys()),
            key="student_add_user"
        )

        if st.button(
            "➕ Add Student",
            use_container_width=True,
            key="add_student_button"
        ):

            if role == "Teacher":
                entered_class_key = (
                    str(class_name or "").strip().lower(),
                    str(section or "").strip().lower()
                )
                if entered_class_key not in assigned_class_keys:
                    st.error("You can only add a student to your assigned Class Teacher class.")
                    return


            if not name.strip():
                st.warning(
                    "Student name is required."
                )
                return

            if student_photo:

                photo_size_kb = student_photo.size / 1024

                if not 10 <= photo_size_kb <= 200:

                    st.error(
                        "Student photo must be between "
                        "10 KB and 200 KB."
                    )

                    return

            try:

                student_id = str(uuid.uuid4())

                student_record = {
                    "id": student_id,
                    "school_id": school_id,
                    "user_id": user_options[selected_user],
                    "name": name.strip(),
                    "admission_no": admission_no.strip(),
                    "class_name": class_name.strip(),
                    "section": section.strip(),
                    "date_of_birth": str(date_of_birth),
                    "gender": gender,
                    "father_name": father_name.strip(),
                    "parent_name": father_name.strip(),
                    "mother_name": mother_name.strip(),
                    "parent_phone": parent_phone.strip(),
                    "address": address.strip(),
                    "remarks": remarks.strip(),
                    "active": True
                }

                (
                    sb.table("students")
                    .insert(student_record)
                    .execute()
                )

                if student_photo:

                    photo_path = upload_student_file(
                        school_id,
                        student_id,
                        student_photo,
                        "photo",
                        ["jpg", "jpeg", "png"],
                        min_kb=10,
                        max_kb=200
                    )

                    (
                        sb.table("students")
                        .update({
                            "photo_path": photo_path
                        })
                        .eq("id", student_id)
                        .execute()
                    )

                st.success(
                    "Student added successfully."
                )

                st.rerun()

            except Exception as e:

                st.error(
                    "Could not add student."
                )

                st.code(str(e))

    # -----------------------------------------------------
    # LOAD STUDENTS
    # -----------------------------------------------------

    try:

        student_data = (
            sb.table("students")
            .select(
                "id,school_id,user_id,name,"
                "admission_no,class_name,section,"
                "date_of_birth,gender,father_name,"
                "parent_name,mother_name,parent_phone,address,remarks,"
                "photo_path,teacher_signature_path,"
                "principal_signature_path,active,"
                "created_at,updated_at"
            )
            .eq("school_id", school_id)            .order("name")
            .execute()            .data or []
        )
    except Exception as e:

        st.error("Could not load students.")
        st.code(str(e))
        return

    if role == "Teacher" and assigned_class_keys is not None:
        student_data = [
            student
            for student in student_data
            if (
                str(student.get("class_name") or "").strip().lower(),
                str(student.get("section") or "").strip().lower()
            ) in assigned_class_keys
        ]

    st.subheader(
        f"📋 Students ({len(student_data)})"
    )

    if not student_data:

        st.info("No students added yet.")
        return

    search = st.text_input(
        "🔍 Search Student",
        placeholder="Name or admission no.",
        key="student_search"
    )

    if search.strip():

        search_text = search.strip().lower()

        student_data = [
            student
            for student in student_data
            if (
                search_text
                in str(student.get("name", "")).lower()
                or
                search_text
                in str(
                    student.get("admission_no", "")
                ).lower()
            )
        ]

    # -----------------------------------------------------
    # EXCEL EXPORT
    # -----------------------------------------------------
    st.divider()
    st.subheader("📥 Student Records Excel")
    st.caption(
        "Excel contains only the required student information."
    )

    export_fields = [
        "Student Name",
        "Admission No.",
        "Class",
        "Section",
        "Date of Birth",
        "Gender",
        "Father Name",
        "Mother Name",
        "Parent Phone",
        "Address",
    ]

    excel_bytes = make_student_records_excel(
        student_data,
        export_fields
    )
    st.download_button(
        "⬇️ Download Student Records Excel",
        data=excel_bytes,
        file_name="Student_Records.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"download_student_records_{role}_{school_id}",
    )

    # -----------------------------------------------------
    # STUDENT SELECTION
    # -----------------------------------------------------
    # Teachers should not see every student card on the dashboard.
    # They select one or more students from a dropdown (multiselect
    # displays checkbox options) and can also Select All.
    if role == "Teacher":

        student_labels = {}
        for student in student_data:
            label = (
                f"{student.get('name') or 'Student'}"
                f" — Admission: {student.get('admission_no') or '-'}"
            )
            student_labels[label] = student

        if not student_labels:
            st.info("No students found in your assigned class.")
            return

        # The checkbox and dropdown work together:
        # - Turning Select All ON selects every student.
        # - Turning it OFF clears the selection.
        # - After that, the teacher can freely select individual students
        #   from the dropdown without the checkbox forcing all students again.
        select_all = st.checkbox(
            "☑️ Select All Students",
            key="teacher_select_all_students"
        )

        previous_select_all = st.session_state.get(
            "teacher_select_all_students_previous",
            False
        )

        if select_all and not previous_select_all:
            st.session_state["teacher_selected_students"] = list(
                student_labels.keys()
            )
        elif not select_all and previous_select_all:
            st.session_state["teacher_selected_students"] = []

        st.session_state["teacher_select_all_students_previous"] = select_all

        selected_labels = st.multiselect(
            "🎓 Select Students",
            list(student_labels.keys()),
            placeholder="Select one or more students",
            key="teacher_selected_students"
        )

        selected_students = [
            student_labels[label]
            for label in selected_labels
            if label in student_labels
        ]

        st.caption(
            f"Selected {len(selected_students)} of {len(student_data)} student(s)."
        )

        if not selected_students:
            st.info("Select student(s) from the dropdown above to view or modify their details.")
            return

        display_students = selected_students

    else:
        # Admin/SuperAdmin should not see every student card at once.
        # First filter by Class and Section, then choose Select All or
        # individual students from the dropdown.
        class_options = sorted({
            str(s.get("class_name") or "").strip()
            for s in student_data
            if str(s.get("class_name") or "").strip()
        })

        class_filter = st.selectbox(
            "🏫 Select Class",
            ["All Classes"] + class_options,
            key=f"{role.lower()}_student_class_filter"
        )

        filtered_students = student_data

        if class_filter != "All Classes":
            filtered_students = [
                s for s in filtered_students
                if str(s.get("class_name") or "").strip() == class_filter
            ]

        section_options = sorted({
            str(s.get("section") or "").strip()
            for s in filtered_students
            if str(s.get("section") or "").strip()
        })

        section_filter = st.selectbox(
            "📚 Select Section",
            ["All Sections"] + section_options,
            key=f"{role.lower()}_student_section_filter"
        )

        if section_filter != "All Sections":
            filtered_students = [
                s for s in filtered_students
                if str(s.get("section") or "").strip() == section_filter
            ]

        st.caption(
            f"Found {len(filtered_students)} student(s) after Class/Section filter."
        )

        student_labels = {}
        for student in filtered_students:
            label = (
                f"{student.get('name') or 'Student'}"
                f" — Admission: {student.get('admission_no') or '-'}"
                f" — {student.get('class_name') or '-'}"
                f"/{student.get('section') or '-'}"
            )
            student_labels[label] = student

        if not student_labels:
            st.info("No students found for the selected Class/Section.")
            return

        select_all_key = (
            "superadmin_student_select_all"
            if role == "SuperAdmin"
            else "admin_student_select_all"
        )
        selected_key = (
            "superadmin_selected_students"
            if role == "SuperAdmin"
            else "admin_selected_students"
        )
        previous_key = selected_key + "_previous"

        select_all = st.checkbox(
            "☑️ Select All Students",
            key=select_all_key
        )

        previous_select_all = st.session_state.get(
            previous_key,
            False
        )

        if select_all and not previous_select_all:
            st.session_state[selected_key] = list(student_labels.keys())
        elif not select_all and previous_select_all:
            st.session_state[selected_key] = []

        st.session_state[previous_key] = select_all

        selected_labels = st.multiselect(
            "🎓 Select Students",
            list(student_labels.keys()),
            placeholder="Select one or more students",
            key=selected_key
        )

        selected_students = [
            student_labels[label]
            for label in selected_labels
            if label in student_labels
        ]

        st.caption(
            f"Selected {len(selected_students)} of {len(filtered_students)} student(s)."
        )

        if not selected_students:
            st.info(
                "Select student(s) from the dropdown above to view or modify their details."
            )
            return

        display_students = selected_students

    for student in display_students:

        student_id = student["id"]

        with st.container(border=True):

            c1, c2, c3 = st.columns([1, 4, 1])

            with c1:

                photo_path = student.get("photo_path")

                if photo_path:

                    try:

                        photo_bytes = (
                            sb.storage
                            .from_("school-assets")
                            .download(photo_path)
                        )

                        st.image(
                            photo_bytes,
                            width=100
                        )

                    except Exception:
                        st.write("📷")

                else:
                    st.write("📷")

            with c2:

                st.markdown(
                    f"### 🎓 {student.get('name', '-')}"
                )

                st.caption(
                    f"Class: {student.get('class_name') or '-'} "
                    f"| Section: {student.get('section') or '-'}"
                )

                st.caption(
                    f"Admission No.: "
                    f"{student.get('admission_no') or '-'}"
                )

                st.caption(
                    f"Father Name: "
                    f"{student.get('father_name') or student.get('parent_name') or '-'}"
                )

                st.caption(
                    f"DOB: {student.get('date_of_birth') or '-'} "
                    f"| Gender: {student.get('gender') or '-'}"
                )

            with c3:

                if student.get("active", True):
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

                if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                    if st.button(
                        "🗑️ Delete",
                        key=f"delete_student_{student_id}"
                    ):

                        try:

                            paths_to_delete = []

                            for field in [
                                "photo_path",
                                "teacher_signature_path",
                                "principal_signature_path"
                            ]:

                                path = student.get(field)

                                if path:
                                    paths_to_delete.append(path)

                            if paths_to_delete:

                                (
                                    sb.storage
                                    .from_("school-assets")
                                    .remove(paths_to_delete)
                                )

                            (
                                sb.table("students")
                                .delete()
                                .eq("id", student_id)
                                .execute()
                            )

                            st.success("Student deleted.")
                            st.rerun()

                        except Exception as e:

                            st.error("Delete failed.")
                            st.code(str(e))

            # -------------------------------------------------
            # MODIFY
            # -------------------------------------------------

            with st.expander("✏️ Modify Student"):

                edit_name = st.text_input(
                    "Student Name",
                    value=student.get("name") or "",
                    key=f"edit_name_{student_id}"
                )

                edit_admission = st.text_input(
                    "Admission No.",
                    value=student.get("admission_no") or "",
                    key=f"edit_admission_{student_id}"
                )

                edit_class = st.text_input(
                    "Class",
                    value=student.get("class_name") or "",
                    key=f"edit_class_{student_id}"
                )

                edit_section = st.text_input(
                    "Section",
                    value=student.get("section") or "",
                    key=f"edit_section_{student_id}"
                )

                try:

                    existing_dob = datetime.date.fromisoformat(
                        str(student.get("date_of_birth"))[:10]
                    )

                except Exception:

                    existing_dob = datetime.date(
                        2010, 1, 1
                    )

                edit_date_of_birth = st.date_input(
                    "Date of Birth",
                    value=existing_dob,
                    key=f"edit_date_of_birth_{student_id}"
                )

                gender_options = [
                    "Male",
                    "Female",
                    "Other"
                ]

                existing_gender = student.get("gender")

                if existing_gender not in gender_options:
                    existing_gender = "Male"

                edit_gender = st.selectbox(
                    "Gender",
                    gender_options,
                    index=gender_options.index(
                        existing_gender
                    ),
                    key=f"edit_gender_{student_id}"
                )

                edit_father_name = st.text_input(
                    "Father Name",
                    value=(
                        student.get("father_name")
                        or student.get("parent_name")
                        or ""
                    ),
                    key=f"edit_father_name_{student_id}"
                )

                edit_mother_name = st.text_input(
                    "Mother Name",
                    value=student.get("mother_name") or "",
                    key=f"edit_mother_name_{student_id}"
                )

                edit_parent_phone = st.text_input(
                    "Parent Phone",
                    value=student.get("parent_phone") or "",
                    key=f"edit_parent_phone_{student_id}"
                )

                edit_address = st.text_area(
                    "Address",
                    value=student.get("address") or "",
                    key=f"edit_address_{student_id}"
                )

                edit_remarks = st.text_area(
                    "Remarks",
                    value=student.get("remarks") or "",
                    key=f"edit_remarks_{student_id}"
                )

                st.markdown("#### 📷 Student Photo")

                if student.get("photo_path"):

                    try:

                        current_photo = (
                            sb.storage
                            .from_("school-assets")
                            .download(
                                student["photo_path"]
                            )
                        )

                        st.image(
                            current_photo,
                            width=120
                        )

                    except Exception:
                        pass

                edit_photo = st.file_uploader(
                    "Replace Student Photo",
                    type=["jpg", "jpeg", "png"],
                    help="New photo must be between 10 KB and 200 KB.",
                    key=f"edit_photo_{student_id}"
                )

                if edit_photo:

                    edit_photo_size = edit_photo.size / 1024

                    if 10 <= edit_photo_size <= 200:

                        st.success(
                            f"Photo size: "
                            f"{edit_photo_size:.1f} KB ✓"
                        )

                        st.image(
                            edit_photo,
                            width=120
                        )

                    else:

                        st.error(
                            "Photo must be between 10 KB and 200 KB."
                        )

                # IMPORTANT:
                # Signature image uploaders removed.
                # Report Card now prints text labels only.

                edit_active = st.checkbox(
                    "Student Active",
                    value=student.get("active", True),
                    key=f"edit_active_{student_id}"
                )

                edit_user_options = {
                    "Not linked": None
                }

                current_user_id = student.get("user_id")
                current_user_label = "Not linked"

                for user in student_users:

                    label = (
                        f"{user.get('full_name') or 'Student'} "
                        f"— {user.get('email')}"
                    )

                    edit_user_options[label] = user["id"]

                    if str(user["id"]) == str(current_user_id):
                        current_user_label = label

                user_labels = list(
                    edit_user_options.keys()
                )

                if current_user_label not in user_labels:
                    current_user_label = "Not linked"

                selected_edit_user = st.selectbox(
                    "🔗 Student Login Account",
                    user_labels,
                    index=user_labels.index(
                        current_user_label
                    ),
                    key=f"edit_user_{student_id}"
                )

                save_key = f"save_student_{student_id}"
                show_save_message(save_key)
                if st.button(
                    "💾 Save Changes",
                    key=save_key,
                    use_container_width=True,
                ):

                    if role == "Teacher" and (
                        str(student.get("class_name") or "").strip().lower(),
                        str(student.get("section") or "").strip().lower()
                    ) not in assigned_class_keys:
                        st.error("You can only change students assigned to your class.")
                        return

                    try:

                        if edit_photo:

                            photo_size_kb = (
                                edit_photo.size / 1024
                            )

                            if not 10 <= photo_size_kb <= 200:

                                st.error(
                                    "Student photo must be between "
                                    "10 KB and 200 KB."
                                )

                                return

                        update_record = {

                            "user_id":
                                edit_user_options[
                                    selected_edit_user
                                ],

                            "name":
                                edit_name.strip(),

                            "admission_no":
                                edit_admission.strip(),

                            "class_name":
                                edit_class.strip(),

                            "section":
                                edit_section.strip(),

                            "date_of_birth":
                                str(edit_date_of_birth),

                            "gender":
                                edit_gender,

                            "father_name":
                                edit_father_name.strip(),

                            "parent_name":
                                edit_father_name.strip(),

                            "mother_name":
                                edit_mother_name.strip(),

                            "parent_phone":
                                edit_parent_phone.strip(),

                            "address":
                                edit_address.strip(),

                            "remarks":
                                edit_remarks.strip(),

                            "active":
                                edit_active
                        }

                        if edit_photo:

                            old_photo = student.get(
                                "photo_path"
                            )

                            new_photo_path = upload_student_file(
                                school_id,
                                student_id,
                                edit_photo,
                                "photo",
                                ["jpg", "jpeg", "png"],
                                min_kb=10,
                                max_kb=200
                            )

                            update_record[
                                "photo_path"
                            ] = new_photo_path

                            if old_photo:

                                try:

                                    (
                                        sb.storage
                                        .from_("school-assets")
                                        .remove([old_photo])
                                    )

                                except Exception:
                                    pass

                        (
                            sb.table("students")
                            .update(update_record)
                            .eq("id", student_id)
                            .execute()
                        )

                        mark_saved(save_key)
                        st.success("Student updated successfully.")

                        st.rerun()

                    except Exception as e:

                        st.error(
                            "Could not update student."
                        )

                        st.code(str(e))


# =========================================================
# CLASSES & SUBJECTS
# =========================================================

def classes_subjects():

    role = st.session_state.profile.get("role")

    st.header("📚 Classes & Subjects")

    school_id = get_selected_school(
        "class_subject_school"
    )

    if not school_id:
        return

    st.divider()

    st.subheader("📚 Classes")

    try:

        class_data = (
            sb.table("classes")
            .select(
                "id,school_id,class_name,section,"
                "academic_year,active,class_teacher_id,"
                "created_at,updated_at"
            )
            .eq("school_id", school_id)
            .order("class_name")
            .order("section")
            .execute()
            .data or []
        )

    except Exception as e:

        st.error("Could not load classes.")
        st.code(str(e))
        return

    # Teachers can see only classes where they are the Class Teacher.
    if role == "Teacher":
        class_data = [
            x for x in class_data
            if str(x.get("class_teacher_id")) == str(st.session_state.user.id)
        ]
        if not class_data:
            st.info("No class has been assigned to you as Class Teacher yet.")
            return

    # -----------------------------------------------------
    # CLASS TEACHER ASSIGNMENT
    # -----------------------------------------------------
    try:
        teacher_data = (
            sb.table("profiles")
            .select("id,full_name,email")
            .eq("school_id", school_id)
            .eq("role", "Teacher")
            .eq("active", True)
            .order("full_name")
            .execute()
            .data or []
        )
    except Exception as e:
        teacher_data = []
        if st.session_state.profile.get("role") in ["SuperAdmin", "Admin"]:
            st.warning("Could not load teachers for class assignment.")

    teacher_options = {"Not Assigned": None}
    for teacher in teacher_data:
        label = f"{teacher.get('full_name') or 'Teacher'} — {teacher.get('email') or ''}"
        teacher_options[label] = teacher["id"]

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        with st.expander("👨‍🏫 Assign Class Teachers"):
            st.caption("Assign one class teacher to each class. Teachers will only see students from their assigned classes.")

            if not teacher_data:
                st.info("Create an active Teacher account first.")

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        with st.expander(        "➕ Add New Class",
            expanded=True    ):
    
            c1, c2, c3 = st.columns(3)
    
            with c1:
    
                new_class = st.text_input(
                    "Class Name",
                    placeholder="Example: Class 10",
                    key="new_class_name"
                )
    
            with c2:
    
                new_section = st.text_input(
                    "Section",
                    placeholder="Example: A",
                    key="new_class_section"
                )
    
            with c3:
    
                new_academic_year = st.text_input(
                    "Academic Year",
                    placeholder="Example: 2026-27",
                    key="new_academic_year"
                )
    
            if st.button(
                "➕ Add Class",
                use_container_width=True,
                key="add_class_button"
            ):
    
                if not new_class.strip():
    
                    st.warning("Class name is required.")
    
                else:
    
                    try:
    
                        existing = (
                            sb.table("classes")
                            .select("id")
                            .eq("school_id", school_id)
                            .eq(
                                "class_name",
                                new_class.strip()
                            )
                            .eq(
                                "section",
                                new_section.strip()
                            )
                            .eq(
                                "academic_year",
                                new_academic_year.strip()
                            )
                            .execute()
                            .data or []
                        )
    
                        if existing:
    
                            st.error(
                                "This class already exists for this academic year."
                            )
    
                        else:
    
                            (
                                sb.table("classes")
                                .insert({
                                    "school_id": school_id,
                                    "class_name":
                                        new_class.strip(),
                                    "section":
                                        new_section.strip(),
                                    "academic_year":
                                        new_academic_year.strip(),
                                    "active": True
                                })
                                .execute()
                            )
    
                            st.success(
                                "Class added successfully."
                            )
    
                            st.rerun()
    
                    except Exception as e:
    
                        st.error("Could not add class.")
                        st.code(str(e))
    
    if st.session_state.pop("saved_class_changes", False):
        st.success("✅ Class teacher / class changes saved successfully.")

    st.divider()

    # -----------------------------------------------------
    # ADMIN / SUPERADMIN CLASS SELECTION
    # -----------------------------------------------------
    # Do not display every class card at once. First select the
    # class/section, then Select All or individual classes.
    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        class_filter_options = ["All Classes"] + [
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'} | {x.get('academic_year') or '-'}"
            for x in class_data
        ]

        class_filter = st.selectbox(
            "🏫 Select Class",
            class_filter_options,
            key=f"{role.lower()}_class_subject_class_filter"
        )

        class_labels_for_selection = {
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'} | {x.get('academic_year') or '-'}": x
            for x in class_data
        }

        filtered_class_data = class_data
        if class_filter != "All Classes":
            filtered_class_data = [class_labels_for_selection[class_filter]]

        class_select_labels = {
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'} | {x.get('academic_year') or '-'}": x
            for x in filtered_class_data
        }

        select_all_classes_key = f"{role.lower()}_class_subject_select_all"
        selected_classes_key = f"{role.lower()}_class_subject_selected"
        previous_classes_key = selected_classes_key + "_previous"

        select_all_classes = st.checkbox(
            "☑️ Select All Classes",
            key=select_all_classes_key
        )
        previous_select_all_classes = st.session_state.get(previous_classes_key, False)

        if select_all_classes and not previous_select_all_classes:
            st.session_state[selected_classes_key] = list(class_select_labels.keys())
        elif not select_all_classes and previous_select_all_classes:
            st.session_state[selected_classes_key] = []

        st.session_state[previous_classes_key] = select_all_classes

        selected_class_labels = st.multiselect(
            "📚 Select Classes",
            list(class_select_labels.keys()),
            placeholder="Select one or more classes",
            key=selected_classes_key
        )

        class_data = [
            class_select_labels[label]
            for label in selected_class_labels
            if label in class_select_labels
        ]

        st.caption(f"Selected {len(class_data)} class(es).")

        if not class_data:
            st.info("Select class(es) from the dropdown above to view or modify them.")
            return

    st.caption(
        f"Total Selected Classes: {len(class_data)}"
    )

    for class_item in class_data:

        class_id = class_item["id"]

        class_title = (
            class_item.get("class_name") or "-"
        )

        section = (
            class_item.get("section") or "-"
        )

        academic_year = (
            class_item.get("academic_year") or "-"
        )

        active = class_item.get("active", True)

        with st.container(border=True):

            c1, c2, c3 = st.columns([4, 2, 1])

            with c1:

                st.markdown(
                    f"### 📚 {class_title}"
                )

                st.caption(
                    f"Section: {section} "
                    f"| Academic Year: {academic_year}"
                )

                current_teacher = next(
                    (
                        t for t in teacher_data
                        if str(t.get("id")) == str(class_item.get("class_teacher_id"))
                    ),
                    None
                )
                st.caption(
                    "Class Teacher: "
                    + (
                        current_teacher.get("full_name")
                        if current_teacher
                        else "Not Assigned"
                    )
                )

            with c2:

                if active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with c3:

                if role in ["SuperAdmin", "Admin", "Admin+Teacher"] and st.button(
                    "Deactivate" if active else "Activate",
                    key=f"class_active_{class_id}"
                ):

                    try:

                        (
                            sb.table("classes")
                            .update({
                                "active": not active,
                                "updated_at":
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                            })
                            .eq("id", class_id)
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

            if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                current_teacher_id = class_item.get("class_teacher_id")
                current_teacher_label = "Not Assigned"

                for label, teacher_id in teacher_options.items():
                    if teacher_id and str(teacher_id) == str(current_teacher_id):
                        current_teacher_label = label
                        break

                assignment_label = st.selectbox(
                    "👨‍🏫 Assign Class Teacher",
                    list(teacher_options.keys()),
                    index=list(teacher_options.keys()).index(
                        current_teacher_label
                    ),
                    key=f"assign_teacher_{class_id}"
                )

                save_key = f"save_teacher_{class_id}"
                show_save_message(save_key)
                if st.button(
                    "💾 Save Class Teacher",
                    key=save_key,
                    use_container_width=True,
                ):
                    try:
                        (
                            sb.table("classes")
                            .update({
                                "class_teacher_id":
                                    teacher_options[assignment_label],
                                "updated_at":
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                            })
                            .eq("id", class_id)
                            .execute()
                        )

                        mark_saved(save_key)
                        st.session_state["saved_class_changes"] = True
                        st.rerun()

                    except Exception as e:
                        st.error(
                            "Could not assign Class Teacher. "
                            "Make sure the classes table has the "
                            "class_teacher_id column."
                        )
                        st.code(str(e))

            if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                with st.expander("✏️ Edit Class"):
    
                    edit_class_name = st.text_input(
                        "Class Name",
                        value=class_title,
                        key=f"edit_class_name_{class_id}"
                    )
    
                    edit_section = st.text_input(
                        "Section",
                        value=class_item.get("section") or "",
                        key=f"edit_class_section_{class_id}"
                    )
    
                    edit_year = st.text_input(
                        "Academic Year",
                        value=class_item.get("academic_year") or "",
                        key=f"edit_class_year_{class_id}"
                    )
    
                    selected_teacher_label = None
    
                    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                        teacher_labels = list(teacher_options.keys())
                        current_teacher_id = class_item.get("class_teacher_id")
                        current_teacher_label = "Not Assigned"
    
                        for label, teacher_id in teacher_options.items():
                            if teacher_id and str(teacher_id) == str(current_teacher_id):
                                current_teacher_label = label
                                break
    
                        selected_teacher_label = st.selectbox(
                            "👨‍🏫 Class Teacher",
                            teacher_labels,
                            index=teacher_labels.index(current_teacher_label),
                            key=f"edit_class_teacher_{class_id}"
                        )
    
                    save_key = f"save_class_{class_id}"
                    show_save_message(save_key)
                    if st.button(
                        "💾 Save Class",
                        key=save_key,
                    ):
    
                        try:
    
                            class_update_record = {
                                "class_name":
                                    edit_class_name.strip(),
                                "section":
                                    edit_section.strip(),
                                "academic_year":
                                    edit_year.strip(),
                                "updated_at":
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                            }
    
                            if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                                class_update_record["class_teacher_id"] = (
                                    teacher_options[selected_teacher_label]
                                )
    
                            update_result = (
                                sb.table("classes")
                                .update(class_update_record)
                                .eq("id", class_id)
                                .execute()
                            )
    
                            mark_saved(save_key)
                            st.session_state["saved_class_changes"] = True
                            st.rerun()
    
                        except Exception as e:
    
                            st.error(
                                "Could not update class."
                            )
    
                            st.code(str(e))
    
                    if st.button(
                        "🗑️ Delete Class",
                        key=f"delete_class_{class_id}"
                    ):
    
                        try:
    
                            (
                                sb.table("classes")
                                .delete()
                                .eq("id", class_id)
                                .execute()
                            )
    
                            st.success("Class deleted.")
                            st.rerun()
    
                        except Exception as e:
    
                            st.error(
                                "Could not delete class."
                            )
    
                            st.code(str(e))
    
                st.markdown("#### 📖 Subjects")

            try:

                subject_data = (
                    sb.table("subjects")
                    .select(
                        "id,school_id,name,code,active,"
                        "class_id,subject_name,max_marks,"
                        "passing_marks"
                    )
                    .eq("school_id", school_id)
                    .eq("class_id", class_id)
                    .order("subject_name")
                    .execute()
                    .data or []
                )

            except Exception as e:

                st.error("Could not load subjects.")
                st.code(str(e))
                subject_data = []

            for subject in subject_data:

                subject_id = subject["id"]

                display_subject_name = (
                    subject.get("subject_name")
                    or subject.get("name")
                    or "-"
                )

                subject_code = (
                    subject.get("code") or "-"
                )

                max_marks = (
                    subject.get("max_marks")
                    if subject.get("max_marks") is not None
                    else 100
                )

                passing_marks = (
                    subject.get("passing_marks")
                    if subject.get("passing_marks") is not None
                    else 33
                )

                s1, s2, s3 = st.columns([4, 2, 1])

                with s1:

                    st.write(
                        f"**{display_subject_name}**"
                    )

                    st.caption(
                        f"Code: {subject_code} "
                        f"| Maximum: {max_marks} "
                        f"| Passing: {passing_marks}"
                    )

                with s2:

                    if subject.get("active", True):
                        st.success("ACTIVE")
                    else:
                        st.error("INACTIVE")

                with s3:

                    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
                        if st.button(
                            "✏️ Edit",
                            key=f"edit_subject_button_{subject_id}"
                        ):

                            st.session_state[
                                f"editing_subject_{subject_id}"
                            ] = True

                            st.rerun()

                if role in ["SuperAdmin", "Admin", "Admin+Teacher"] and st.session_state.get(
                    f"editing_subject_{subject_id}",
                    False
                ):

                    with st.container(border=True):

                        edit_subject_name = st.text_input(
                            "Subject Name",
                            value=display_subject_name,
                            key=f"subject_name_{subject_id}"
                        )

                        edit_subject_code = st.text_input(
                            "Subject Code",
                            value=subject.get("code") or "",
                            key=f"subject_code_{subject_id}"
                        )

                        e1, e2 = st.columns(2)

                        with e1:

                            edit_max = st.number_input(
                                "Maximum Marks",
                                min_value=1.0,
                                value=float(max_marks),
                                key=f"subject_max_{subject_id}"
                            )

                        with e2:

                            edit_pass = st.number_input(
                                "Passing Marks",
                                min_value=0.0,
                                value=float(passing_marks),
                                key=f"subject_pass_{subject_id}"
                            )

                        edit_active = st.checkbox(
                            "Subject Active",
                            value=subject.get(
                                "active",
                                True
                            ),
                            key=f"subject_active_{subject_id}"
                        )

                        b1, b2 = st.columns(2)

                        with b1:

                            save_key = f"save_subject_{subject_id}"
                            show_save_message(save_key)
                            if st.button(
                                "💾 Save Subject",
                                key=save_key,
                                use_container_width=True,
                            ):

                                if edit_pass > edit_max:

                                    st.error(
                                        "Passing marks cannot exceed maximum marks."
                                    )

                                elif not edit_subject_name.strip():

                                    st.error(
                                        "Subject name is required."
                                    )

                                else:

                                    try:

                                        (
                                            sb.table("subjects")
                                            .update({
                                                "name":
                                                    edit_subject_name.strip(),
                                                "subject_name":
                                                    edit_subject_name.strip(),
                                                "code":
                                                    edit_subject_code.strip(),
                                                "max_marks":
                                                    edit_max,
                                                "passing_marks":
                                                    edit_pass,
                                                "active":
                                                    edit_active
                                            })
                                            .eq(
                                                "id",
                                                subject_id
                                            )
                                            .execute()
                                        )

                                        mark_saved(save_key)
                                        st.success(
                                            "Subject updated."
                                        )

                                        st.session_state[
                                            f"editing_subject_{subject_id}"
                                        ] = False

                                        st.rerun()

                                    except Exception as e:

                                        st.error(
                                            "Could not update subject."
                                        )

                                        st.code(str(e))

                        with b2:

                            if st.button(
                                "🗑️ Delete Subject",
                                key=f"delete_subject_{subject_id}",
                                use_container_width=True
                            ):

                                try:

                                    (
                                        sb.table("subjects")
                                        .delete()
                                        .eq(
                                            "id",
                                            subject_id
                                        )
                                        .execute()
                                    )

                                    st.success(
                                        "Subject deleted."
                                    )

                                    st.rerun()

                                except Exception as e:

                                    st.error(
                                        "Could not delete subject."
                                    )

                                    st.code(str(e))

            if role in ["SuperAdmin", "Admin", "Admin+Teacher"] and subject_data:
                subject_labels = {}
                for sub in subject_data:
                    sub_display = sub.get("subject_name") or sub.get("name") or "Subject"
                    subject_labels[f"{sub_display} | Code: {sub.get('code') or '-'}"] = sub

                subject_select_all_key = f"{role.lower()}_subject_select_all_{class_id}"
                subject_selected_key = f"{role.lower()}_selected_subjects_{class_id}"
                subject_previous_key = subject_selected_key + "_previous"

                select_all_subjects = st.checkbox(
                    "☑️ Select All Subjects",
                    key=subject_select_all_key
                )
                previous_select_all_subjects = st.session_state.get(subject_previous_key, False)

                if select_all_subjects and not previous_select_all_subjects:
                    st.session_state[subject_selected_key] = list(subject_labels.keys())
                elif not select_all_subjects and previous_select_all_subjects:
                    st.session_state[subject_selected_key] = []

                st.session_state[subject_previous_key] = select_all_subjects

                selected_subject_labels = st.multiselect(
                    "📖 Select Subjects",
                    list(subject_labels.keys()),
                    placeholder="Select one or more subjects",
                    key=subject_selected_key
                )

                subject_data = [
                    subject_labels[label]
                    for label in selected_subject_labels
                    if label in subject_labels
                ]

                st.caption(f"Selected {len(subject_data)} subject(s).")

                if not subject_data:
                    st.info("Select subject(s) from the dropdown above to view or modify them.")

            if not subject_data:
                st.caption(
                    "No subjects selected/added for this class."
                )

            with st.expander("➕ Add Subject"):

                new_subject_name = st.text_input(
                    "Subject Name",
                    placeholder="Example: Mathematics",
                    key=f"new_subject_name_{class_id}"
                )
                new_subject_code = st.text_input(
                    "Subject Code",
                    placeholder="Example: MATH",                    key=f"new_subject_code_{class_id}"
                )
                sc1, sc2 = st.columns(2)

                with sc1:

                    new_max_marks = st.number_input(
                        "Maximum Marks",
                        min_value=1.0,
                        value=100.0,
                        key=f"new_subject_max_{class_id}"
                    )

                with sc2:

                    new_passing_marks = st.number_input(
                        "Passing Marks",
                        min_value=0.0,
                        value=33.0,
                        key=f"new_subject_pass_{class_id}"
                    )

                if st.button(
                    "➕ Add Subject",
                    key=f"add_subject_{class_id}",
                    use_container_width=True
                ):

                    if not new_subject_name.strip():

                        st.warning(
                            "Subject name is required."
                        )

                    elif new_passing_marks > new_max_marks:

                        st.error(
                            "Passing marks cannot exceed maximum marks."
                        )

                    else:

                        try:

                            existing_subject = (
                                sb.table("subjects")
                                .select("id")
                                .eq(
                                    "school_id",
                                    school_id
                                )
                                .eq(
                                    "class_id",
                                    class_id
                                )
                                .eq(
                                    "subject_name",
                                    new_subject_name.strip()
                                )
                                .execute()
                                .data or []
                            )

                            if existing_subject:

                                st.error(
                                    "This subject already exists for this class."
                                )

                            else:

                                (
                                    sb.table("subjects")
                                    .insert({
                                        "school_id":
                                            school_id,
                                        "class_id":
                                            class_id,
                                        "name":
                                            new_subject_name.strip(),
                                        "subject_name":
                                            new_subject_name.strip(),
                                        "code":
                                            new_subject_code.strip(),
                                        "max_marks":
                                            new_max_marks,
                                        "passing_marks":
                                            new_passing_marks,
                                        "active":
                                            True
                                    })
                                    .execute()
                                )

                                st.success(
                                    "Subject added successfully."
                                )

                                st.rerun()

                        except Exception as e:

                            st.error(
                                "Could not add subject."
                            )

                            st.code(str(e))


# =========================================================
# BULK MARKS
# =========================================================

def bulk_marks():

    st.header("📝 Bulk Marks Entry")

    # Show the automatic Excel backup created after the previous successful save.
    pending_backup = st.session_state.pop("_marks_backup_bytes", None)
    pending_backup_name = st.session_state.pop(
        "_marks_backup_filename",
        None
    )
    if pending_backup:
        st.success("✅ Marks were saved and a fresh Excel backup was created.")
        st.download_button(
            "⬇️ Download Fresh Marks Backup",
            data=pending_backup,
            file_name=pending_backup_name or "Marks_Backup.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="bulk_marks_fresh_backup_download"
        )
        st.divider()

    role = st.session_state.profile.get("role")

    if role not in ["SuperAdmin", "Admin", "Admin+Teacher", "Teacher"]:
        st.error("You do not have permission to enter marks.")
        return

    school_id = get_selected_school("marks_school")
    if not school_id:
        return

    try:
        class_data = (
            sb.table("classes")
            .select(
                "id,school_id,class_name,section,"
                "academic_year,active"
            )
            .eq("school_id", school_id)
            .eq("active", True)
            .order("class_name")
            .order("section")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load classes.")
        st.code(str(e))
        return

    if not class_data:
        st.info("No active classes found.")
        return

    # Teachers see only classes for which they have a subject assignment.
    if role == "Teacher":
        try:
            teacher_assignments = (
                sb.table("teacher_subject_assignments")
                .select("class_id,subject_id")
                .eq("school_id", school_id)
                .eq("teacher_id", st.session_state.user.id)
                .execute()
                .data or []
            )
        except Exception as e:
            st.error(
                "Teacher subject assignments are not available. "
                "Ask Admin to create the teacher_subject_assignments table."
            )
            st.code(str(e))
            return

        if not teacher_assignments:
            st.info(
                "No subject-teaching assignments have been given to you yet."
            )
            return

        assigned_class_ids = {
            str(x.get("class_id"))
            for x in teacher_assignments
        }

        class_data = [
            x for x in class_data
            if str(x.get("id")) in assigned_class_ids
        ]

        if not class_data:
            st.info("No classes are assigned to you for teaching.")
            return

    class_map = {}

    for item in class_data:
        label = (
            f"{item.get('class_name') or '-'}"
            f" | Section: {item.get('section') or '-'}"
            f" | {item.get('academic_year') or '-'}"
        )
        class_map[label] = item

    selected_class_label = st.selectbox(
        "📚 Select Class",
        list(class_map.keys()),
        key="marks_class"
    )

    selected_class = class_map[selected_class_label]
    class_id = selected_class["id"]

    class_name = selected_class.get("class_name") or ""
    section = selected_class.get("section") or ""

    try:
        subject_data = (
            sb.table("subjects")
            .select(
                "id,school_id,name,code,active,class_id,"
                "subject_name,max_marks,passing_marks"
            )
            .eq("school_id", school_id)
            .eq("class_id", class_id)
            .eq("active", True)
            .order("subject_name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load subjects.")
        st.code(str(e))
        return

    if not subject_data:
        st.warning("No active subjects found for this class.")
        return

    # Teachers see only the subjects assigned to them in the selected class.
    if role == "Teacher":
        assigned_subject_ids = {
            str(x.get("subject_id"))
            for x in teacher_assignments
            if str(x.get("class_id")) == str(class_id)
        }

        subject_data = [
            x for x in subject_data
            if str(x.get("id")) in assigned_subject_ids
        ]

        if not subject_data:
            st.info(
                "No subject is assigned to you for this class."
            )
            return

    subject_map = {}

    for subject in subject_data:
        subject_name = (
            subject.get("subject_name")
            or subject.get("name")
            or "Subject"
        )
        max_marks = (
            subject.get("max_marks")
            if subject.get("max_marks") is not None
            else 100
        )
        label = f"{subject_name} (Max: {max_marks})"
        subject_map[label] = subject

    selected_subject_label = st.selectbox(
        "📖 Select Subject",
        list(subject_map.keys()),
        key="marks_subject"
    )

    selected_subject = subject_map[selected_subject_label]
    subject_id = selected_subject["id"]

    # Admin / SuperAdmin can work with every active class and every
    # active subject in the selected school. Teachers remain restricted
    # to their exact assigned class + subject combinations.
    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        st.success(
            f"Admin access: all {len(class_data)} active classes are available, "
            f"and all active subjects for the selected class can be modified below."
        )

    subject_name = (
        selected_subject.get("subject_name")
        or selected_subject.get("name")
        or "Subject"
    )

    max_marks = float(selected_subject.get("max_marks") or 100)
    passing_marks = float(selected_subject.get("passing_marks") or 0)

    st.caption(
        f"Maximum Marks: **{max_marks:.2f}** "
        f"| Passing Marks: **{passing_marks:.2f}**"
    )

    exam_options = get_exam_assessments(school_id)
    if not exam_options:
        st.warning("No Exam / Assessment has been created by Admin yet.")
        return

    exam_names = [
        str(x.get("name") or "").strip()
        for x in exam_options if x.get("name")
    ]
    exam_name = st.selectbox(
        "📝 Exam / Assessment",
        exam_names,
        key="marks_exam_name"
    ).strip()

    try:
        student_data = (
            sb.table("students")
            .select(
                "id,name,admission_no,"
                "class_name,section,active"
            )
            .eq("school_id", school_id)
            .eq("class_name", class_name)
            .eq("section", section)
            .eq("active", True)
            .order("name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load students.")
        st.code(str(e))
        return

    students_for_class = [
        student for student in student_data
        if (
            str(student.get("class_name") or "").strip().lower()
            == str(class_name).strip().lower()
            and
            str(student.get("section") or "").strip().lower()
            == str(section).strip().lower()
        )
    ]

    if not students_for_class:
        st.warning(
            f"No active students found for {class_name} / Section {section}."
        )
        return

    try:
        existing_marks = (
            sb.table("marks")
            .select(
                "id,student_id,subject_id,"
                "exam_name,marks,max_marks,class_id"
            )
            .eq("school_id", school_id)
            .eq("class_id", class_id)
            .eq("subject_id", subject_id)
            .eq("exam_name", exam_name)
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load existing marks.")
        st.code(str(e))
        return

    marks_by_student = {
        str(row["student_id"]): row
        for row in existing_marks
    }

    editor_rows = []

    for student in students_for_class:
        student_id = str(student["id"])
        existing = marks_by_student.get(student_id)

        editor_rows.append({
            "Student ID": student_id,
            "Student Name": student.get("name") or "",
            "Admission No.": student.get("admission_no") or "",
            "Marks": existing.get("marks") if existing else None
        })

    marks_df = pd.DataFrame(editor_rows)

    st.markdown(f"### 📝 {subject_name} — {exam_name}")
    st.caption(
        f"{len(students_for_class)} students | Maximum {max_marks:.2f} marks"
    )

    edited_df = st.data_editor(
        marks_df,
        hide_index=True,
        use_container_width=True,
        disabled=[
            "Student ID",
            "Student Name",
            "Admission No."
        ],
        column_config={
            "Marks": st.column_config.NumberColumn(
                "Marks",
                min_value=0.0,
                max_value=max_marks,
                step=0.5,
                format="%.2f"
            )
        },
        key=(
            f"marks_editor_{school_id}_"
            f"{class_id}_{subject_id}_{exam_name}"
        )
    )

    st.divider()

    save_key = "save_all_marks"
    # Marks are edited in a DataFrame, so compare the editor's actual values
    # with the values loaded from Supabase rather than relying on widget state.
    marks_save_values = edited_df[["Student ID", "Marks"]].copy()
    show_save_message(save_key)
    if st.button(
        "💾 Save All Marks",
        type="primary",
        use_container_width=True,
        key=save_key,
    ):

        errors = []
        records_to_insert = []
        updates = []
        deletes = []

        for _, row in edited_df.iterrows():

            student_id = str(row["Student ID"])
            value = row["Marks"]
            existing = marks_by_student.get(student_id)

            if (
                value is None
                or pd.isna(value)
                or str(value).strip() == ""
            ):
                if existing:
                    deletes.append({
                        "id": existing["id"],
                        "old_marks": existing.get("marks")
                    })
                continue

            try:
                mark_value = round(float(value), 2)
            except Exception:
                errors.append(
                    f"{row['Student Name']}: Invalid marks."
                )
                continue

            if mark_value < 0:
                errors.append(
                    f"{row['Student Name']}: Marks cannot be negative."
                )
                continue

            if mark_value > max_marks:
                errors.append(
                    f"{row['Student Name']}: {format_mark(mark_value)} exceeds "
                    f"maximum {format_mark(max_marks)}."
                )
                continue

            if existing:
                old_value = existing.get("marks")
                old_num = None
                if old_value is not None and not pd.isna(old_value):
                    try:
                        old_num = float(old_value)
                    except Exception:
                        old_num = None

                # Do not write unchanged rows. This reduces database traffic
                # and avoids unnecessary row/version churn for concurrent users.
                if old_num is None or abs(old_num - mark_value) > 1e-9:
                    updates.append({
                        "id": existing["id"],
                        "old_marks": old_num,
                        "marks": mark_value,
                        "max_marks": max_marks,
                        "class_id": class_id
                    })
            else:
                records_to_insert.append({
                    "school_id": school_id,
                    "student_id": student_id,
                    "subject_id": subject_id,
                    "exam_name": exam_name,
                    "marks": mark_value,
                    "max_marks": max_marks,
                    "class_id": class_id
                })

        if errors:
            st.error("Please correct these errors:")
            for error in errors:
                st.error(error)
            return

        try:
            if records_to_insert:
                sb.table("marks").insert(records_to_insert).execute()

            conflicts = []

            for update_row in updates:
                query = (
                    sb.table("marks")
                    .update({
                        "marks": update_row["marks"],
                        "max_marks": update_row["max_marks"],
                        "class_id": update_row["class_id"]
                    })
                    .eq("id", update_row["id"])
                )

                if update_row["old_marks"] is None:
                    query = query.is_("marks", "null")
                else:
                    query = query.eq("marks", update_row["old_marks"])

                result = query.select("id").execute()
                if not result.data:
                    conflicts.append(
                        f"Student ID {update_row['id']}: "
                        "this mark was changed by another user. Reload and review before saving."
                    )

            for delete_row in deletes:
                query = (
                    sb.table("marks")
                    .delete()
                    .eq("id", delete_row["id"])
                )

                old_delete_value = delete_row.get("old_marks")
                if old_delete_value is None:
                    query = query.is_("marks", "null")
                else:
                    query = query.eq("marks", old_delete_value)

                result = query.select("id").execute()
                if not result.data:
                    conflicts.append(
                        f"Mark record {delete_row['id']}: it was already changed or removed by another user."
                    )

            if conflicts:
                st.warning(
                    "Some records were not changed because another user "
                    "updated them at the same time."
                )
                for conflict in conflicts:
                    st.warning(conflict)
                return

            try:
                fresh_backup = build_marks_backup_workbook(school_id)
                fresh_stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                st.session_state["_marks_backup_bytes"] = fresh_backup
                st.session_state["_marks_backup_filename"] = (
                    f"Marks_Backup_{str(exam_name).replace('/', '_').replace(' ', '_')}_{fresh_stamp}.xlsx"
                )
            except Exception:
                # Saving marks must not fail just because backup generation fails.
                pass

            mark_saved(save_key, marks_save_values)
            st.success("✅ Marks saved successfully.")
            st.rerun()

        except Exception as e:
            st.error("Could not save marks.")
            st.code(str(e))



def attendance():
    st.header("📅 Attendance")

    role = st.session_state.profile.get("role")

    if role not in ["SuperAdmin", "Admin", "Admin+Teacher", "Teacher"]:
        st.error("You do not have permission to manage attendance.")
        return

    school_id = get_selected_school("attendance_school")
    if not school_id:
        return

    selected_date = st.date_input(
        "Attendance Date",
        value=datetime.date.today(),
        key="attendance_date"
    )

    try:
        students_data = (
            sb.table("students")
            .select("id,name,class_name,section,admission_no,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .order("name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load students.")
        st.code(str(e))
        return

    if not students_data:
        st.info("No active students found.")
        return

    # Class Teacher can see/fill attendance only for classes assigned
    # to them as Class Teacher. Admin/SuperAdmin retain full access.
    assigned_class_rows = []
    if role == "Teacher":
        try:
            assigned_class_rows = (
                sb.table("classes")
                .select("id,class_name,section,academic_year")
                .eq("school_id", school_id)
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .order("class_name")
                .order("section")
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load your Class Teacher assignments.")
            st.code(str(e))
            return

        if not assigned_class_rows:
            st.warning(
                "No class has been assigned to you as Class Teacher yet."
            )
            return

        assigned_pairs = {
            (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            )
            for x in assigned_class_rows
        }

        students_data = [
            x for x in students_data
            if (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            ) in assigned_pairs
        ]

        class_options = [
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}"
            for x in assigned_class_rows
        ]
        class_lookup = {
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}": x
            for x in assigned_class_rows
        }
    else:
        class_options = ["All Classes"] + sorted({
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}"
            for x in students_data
            if str(x.get("class_name") or "")
        })
        class_lookup = {}

    selected_class = st.selectbox(
        "Class",
        class_options,
        key="attendance_class"
    )

    selected_class_row = class_lookup.get(selected_class)

    if selected_class != "All Classes":
        if role == "Teacher" and selected_class_row:
            target_name = str(selected_class_row.get("class_name") or "").strip().lower()
            target_section = str(selected_class_row.get("section") or "").strip().lower()
            students_data = [
                x for x in students_data
                if str(x.get("class_name") or "").strip().lower() == target_name
                and str(x.get("section") or "").strip().lower() == target_section
            ]
        else:
            # Admin/SuperAdmin
            parts = selected_class.split(" | Section: ", 1)
            target_name = parts[0].strip().lower()
            target_section = parts[1].strip().lower() if len(parts) > 1 else ""
            students_data = [
                x for x in students_data
                if str(x.get("class_name") or "").strip().lower() == target_name
                and str(x.get("section") or "").strip().lower() == target_section
            ]

    try:
        existing = (
            sb.table("attendance")
            .select("id,student_id,attendance_date,present")
            .eq("school_id", school_id)
            .eq("attendance_date", str(selected_date))
            .execute()
            .data or []
        )
    except Exception as e:
        st.error(
            "Attendance table could not be loaded. "
            "Create the attendance table in Supabase first."
        )
        st.code(str(e))
        return

    existing_by_student = {
        str(x["student_id"]): x for x in existing
    }

    entries = []

    for student in students_data:
        sid = str(student["id"])
        old = existing_by_student.get(sid, {})
        old_present = old.get("present", True)

        status = st.selectbox(
            student.get("name") or "Student",
            ["Present", "Absent"],
            index=0 if bool(old_present) else 1,
            key=f"attendance_{sid}_{selected_date}"
        )

        entries.append((
            sid,
            status == "Present",
            old.get("id"),
            old.get("present")
        ))

    save_key = "save_attendance_button"
    show_save_message(save_key)
    if st.button(
        "💾 Save Attendance",
        type="primary",
        use_container_width=True,
        key=save_key,
    ):
        try:
            conflicts = []

            for sid, status, old_id, old_present in entries:
                if old_id:
                    # Skip unchanged attendance rows.
                    if old_present is not None and bool(old_present) == bool(status):
                        continue

                    query = (
                        sb.table("attendance")
                        .update({"present": status})
                        .eq("id", old_id)
                    )

                    if old_present is None:
                        query = query.is_("present", "null")
                    else:
                        query = query.eq("present", bool(old_present))

                    result = query.select("id").execute()
                    if not result.data:
                        conflicts.append(
                            f"Student ID {sid}: attendance was changed by another user."
                        )
                else:
                    (
                        sb.table("attendance")
                        .insert({
                            "school_id": school_id,
                            "student_id": sid,
                            "attendance_date": str(selected_date),
                            "present": status
                        })
                        .execute()
                    )

            if conflicts:
                st.warning(
                    "Some attendance records were not changed because another "
                    "user updated them at the same time."
                )
                for conflict in conflicts:
                    st.warning(conflict)
                return

            mark_saved(save_key)
            st.success("Attendance saved successfully.")
            st.rerun()

        except Exception as e:
            st.error("Could not save attendance.")
            st.code(str(e))


def print_templates():

    st.header("🖨️ A4 Print Templates")

    role = st.session_state.profile.get("role")

    if role not in [
        "SuperAdmin",
        "Admin",
        "Admin+Teacher"
    ]:

        st.error(
            "You do not have permission to manage print templates."
        )

        return

    school_id = get_selected_school("template_school")

    if not school_id:
        return

    try:

        school_info = (
            sb.table("schools")
            .select("id,name,code,address")
            .eq("id", school_id)
            .maybe_single()
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            "Could not load school information."
        )

        st.code(str(e))
        return

    school_name = (
        school_info.get("name")
        if school_info
        else "School"
    )

    school_code = (
        school_info.get("code")
        if school_info
        else str(school_id)
    )

    st.info(
        f"🏫 Templates for: **{school_name} "
        f"({school_code})**"
    )

    st.markdown(
        """
        ### A4 School Paper Designs

        Each school can keep its own A4 designs.

        Supported files: **PDF, PNG, JPG, JPEG**
        """
    )

    st.divider()

    with st.expander(
        "➕ Upload New A4 Template",
        expanded=True
    ):

        template_name = st.text_input(
            "Template Name",
            placeholder="Example: Annual Report Card 2026-27",
            key="template_name"
        )

        template_type = st.selectbox(
            "Template Type",
            [
                "Report Card",
                "Certificate",
                "Fee Receipt",
                "Attendance",
                "Other"
            ],
            key="template_type"
        )

        orientation = st.radio(
            "A4 Orientation",
            ["Portrait", "Landscape"],
            horizontal=True,
            key="template_orientation"
        )

        uploaded_file = st.file_uploader(
            "Upload A4 Design",
            type=["pdf", "png", "jpg", "jpeg"],
            key="template_file"
        )

        if uploaded_file:

            st.write(
                f"📄 **{uploaded_file.name}**"
            )

            st.caption(
                f"File size: "
                f"{uploaded_file.size / 1024:.1f} KB"
            )

            extension = (
                uploaded_file.name
                .split(".")[-1]
                .lower()
            )

            if extension in [
                "png",
                "jpg",
                "jpeg"
            ]:

                st.image(
                    uploaded_file,
                    caption="Template Preview",
                    use_container_width=True
                )

        save_key = "upload_template_button"
        show_save_message(save_key)
        if st.button(
            "⬆️ Upload & Save Template",
            type="primary",
            use_container_width=True,
            key=save_key,
        ):

            if not template_name.strip():

                st.warning(
                    "Enter a template name."
                )
                return

            if not uploaded_file:

                st.warning(
                    "Select a PDF or image file first."
                )
                return

            try:

                original_name = uploaded_file.name

                extension = (
                    original_name
                    .split(".")[-1]
                    .lower()
                )

                unique_name = (
                    f"{uuid.uuid4().hex}.{extension}"
                )

                storage_path = (
                    f"{school_id}/"
                    f"templates/"
                    f"{unique_name}"
                )

                file_bytes = uploaded_file.getvalue()

                content_type_map = {
                    "pdf": "application/pdf",
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg"
                }

                (
                    sb.storage
                    .from_("school-assets")
                    .upload(
                        storage_path,
                        file_bytes,
                        file_options={
                            "content-type":
                                content_type_map.get(
                                    extension,
                                    "application/octet-stream"
                                ),
                            "upsert": "false"
                        }
                    )
                )

                config = {
                    "template_type": template_type,
                    "original_file_name": original_name
                }

                (
                    sb.table("print_templates")
                    .insert({
                        "school_id": school_id,
                        "name": template_name.strip(),
                        "template_name": template_name.strip(),
                        "page_size": "A4",
                        "orientation": orientation,
                        "storage_path": storage_path,
                        "file_path": storage_path,
                        "file_type": extension,
                        "config_json": json.dumps(config),
                        "active": True
                    })
                    .execute()
                )

                mark_saved(save_key)
                st.success("✅ Saved successfully.")

                st.rerun()

            except Exception as e:

                st.error(
                    "Could not upload the template."
                )

                st.code(str(e))

    st.divider()

    st.subheader("📋 Existing A4 Templates")

    try:

        template_data = (
            sb.table("print_templates")
            .select(
                "id,school_id,name,template_name,"
                "page_size,orientation,storage_path,"
                "config_json,active,created_at,"
                "updated_at,file_path,file_type"
            )
            .eq("school_id", school_id)
            .order("created_at", desc=True)
            .execute()
            .data or []
        )

    except Exception as e:

        st.error("Could not load templates.")
        st.code(str(e))
        return

    if not template_data:

        st.info(
            "No A4 templates uploaded for this school yet."
        )

        return

    for template in template_data:

        template_id = template["id"]

        template_name_value = (
            template.get("template_name")
            or template.get("name")
            or "Unnamed Template"
        )

        orientation_value = (
            template.get("orientation")
            or "Portrait"
        )

        page_size_value = (
            template.get("page_size")
            or "A4"
        )

        file_path = (
            template.get("file_path")
            or template.get("storage_path")
            or ""
        )

        file_type = (
            template.get("file_type")
            or ""
        )

        active = template.get("active", True)

        try:

            config = (
                json.loads(
                    template["config_json"]
                )
                if template.get("config_json")
                else {}
            )

        except Exception:

            config = {}

        original_file_name = (
            config.get("original_file_name")
            or (
                f"{template_name_value}.{file_type}"
                if file_type
                else template_name_value
            )
        )

        template_type_value = (
            config.get("template_type")
            or "Other"
        )

        with st.container(border=True):

            c1, c2, c3 = st.columns([4, 3, 1])

            with c1:

                st.markdown(
                    f"### 📄 {template_name_value}"
                )

                st.caption(
                    f"Type: {template_type_value}"
                )

                st.caption(
                    f"File: {original_file_name}"
                )

            with c2:

                st.write(
                    f"**{page_size_value} "
                    f"{orientation_value}**"
                )

                if active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with c3:

                if st.button(
                    "🗑️ Delete",
                    key=f"delete_template_{template_id}"
                ):

                    try:

                        if file_path:

                            (
                                sb.storage
                                .from_("school-assets")
                                .remove([file_path])
                            )

                        (
                            sb.table("print_templates")
                            .delete()
                            .eq("id", template_id)
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            "Could not delete template."
                        )

                        st.code(str(e))

            if file_path:

                try:

                    template_bytes = (
                        sb.storage
                        .from_("school-assets")
                        .download(file_path)
                    )

                    mime_map = {
                        "pdf": "application/pdf",
                        "png": "image/png",
                        "jpg": "image/jpeg",
                        "jpeg": "image/jpeg"
                    }

                    st.download_button(
                        "⬇️ Download Template",
                        data=template_bytes,
                        file_name=original_file_name,
                        mime=mime_map.get(
                            file_type.lower(),
                            "application/octet-stream"
                        ),
                        key=f"download_template_{template_id}",
                        use_container_width=True
                    )

                except Exception:

                    st.error(
                        "Could not prepare template download."
                    )

            # Immediate status update
            new_active = st.checkbox(
                "Template Active",
                value=active,                key=f"template_active_{template_id}"
            )

            if new_active != active:

                try:
                    (
                        sb.table("print_templates")
                        .update({
                            "active": new_active,                            "updated_at":
                                datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat()
                        })
                        .eq("id", template_id)
                        .execute()
                    )

                    st.success(
                        "Template status updated."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        "Could not update template."
                    )

                    st.code(str(e))


# =========================================================
# ATTENDANCE
# =========================================================

def attendance():
    st.header("📅 Attendance")

    role = st.session_state.profile.get("role")

    if role not in ["SuperAdmin", "Admin", "Admin+Teacher", "Teacher"]:
        st.error("You do not have permission to manage attendance.")
        return

    school_id = get_selected_school("attendance_school")
    if not school_id:
        return

    selected_date = st.date_input(
        "Attendance Date",
        value=datetime.date.today(),
        key="attendance_date"
    )

    try:
        students_data = (
            sb.table("students")
            .select("id,name,class_name,section,admission_no,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .order("name")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load students.")
        st.code(str(e))
        return

    if not students_data:
        st.info("No active students found.")
        return

    # Class Teacher can see/fill attendance only for classes assigned
    # to them as Class Teacher. Admin/SuperAdmin retain full access.
    assigned_class_rows = []
    if role == "Teacher":
        try:
            assigned_class_rows = (
                sb.table("classes")
                .select("id,class_name,section,academic_year")
                .eq("school_id", school_id)
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .order("class_name")
                .order("section")
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load your Class Teacher assignments.")
            st.code(str(e))
            return

        if not assigned_class_rows:
            st.warning(
                "No class has been assigned to you as Class Teacher yet."
            )
            return

        assigned_pairs = {
            (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            )
            for x in assigned_class_rows
        }

        students_data = [
            x for x in students_data
            if (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            ) in assigned_pairs
        ]

        class_options = [
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}"
            for x in assigned_class_rows
        ]
        class_lookup = {
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}": x
            for x in assigned_class_rows
        }
    else:
        class_options = ["All Classes"] + sorted({
            f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}"
            for x in students_data
            if str(x.get("class_name") or "")
        })
        class_lookup = {}

    selected_class = st.selectbox(
        "Class",
        class_options,
        key="attendance_class"
    )

    selected_class_row = class_lookup.get(selected_class)

    if selected_class != "All Classes":
        if role == "Teacher" and selected_class_row:
            target_name = str(selected_class_row.get("class_name") or "").strip().lower()
            target_section = str(selected_class_row.get("section") or "").strip().lower()
            students_data = [
                x for x in students_data
                if str(x.get("class_name") or "").strip().lower() == target_name
                and str(x.get("section") or "").strip().lower() == target_section
            ]
        else:
            # Admin/SuperAdmin
            parts = selected_class.split(" | Section: ", 1)
            target_name = parts[0].strip().lower()
            target_section = parts[1].strip().lower() if len(parts) > 1 else ""
            students_data = [
                x for x in students_data
                if str(x.get("class_name") or "").strip().lower() == target_name
                and str(x.get("section") or "").strip().lower() == target_section
            ]

    try:
        existing = (
            sb.table("attendance")
            .select("id,student_id,attendance_date,present")
            .eq("school_id", school_id)
            .eq("attendance_date", str(selected_date))
            .execute()
            .data or []
        )
    except Exception as e:
        st.error(
            "Attendance table could not be loaded. "
            "Create the attendance table in Supabase first."
        )
        st.code(str(e))
        return

    existing_by_student = {
        str(x["student_id"]): x for x in existing
    }

    entries = []

    for student in students_data:
        sid = str(student["id"])
        old = existing_by_student.get(sid, {})
        old_present = old.get("present", True)

        status = st.selectbox(
            student.get("name") or "Student",
            ["Present", "Absent"],
            index=0 if bool(old_present) else 1,
            key=f"attendance_{sid}_{selected_date}"
        )

        entries.append((sid, status == "Present", old.get("id")))

    save_key = "save_attendance_button"
    show_save_message(save_key)
    if st.button(
        "💾 Save Attendance",
        type="primary",
        use_container_width=True,
        key=save_key,
    ):
        try:
            for sid, status, old_id in entries:
                if old_id:
                    (
                        sb.table("attendance")
                        .update({"present": status})
                        .eq("id", old_id)
                        .execute()
                    )
                else:
                    (
                        sb.table("attendance")
                        .insert({
                            "school_id": school_id,
                            "student_id": sid,
                            "attendance_date": str(selected_date),
                            "present": status
                        })
                        .execute()
                    )

            st.success("Attendance saved successfully.")
            st.rerun()

        except Exception as e:
            st.error("Could not save attendance.")
            st.code(str(e))


def get_template_config(template):

    try:
        value = template.get("config_json")

        if isinstance(value, dict):
            return dict(value)

        if isinstance(value, str) and value.strip():
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed

    except Exception:
        pass

    return {}


def grade_from_percentage(percentage):
    try:
        p = float(percentage)
    except Exception:
        p = 0

    if p >= 91: return "A1"
    if p >= 81: return "A2"
    if p >= 71: return "B1"
    if p >= 61: return "B2"
    if p >= 51: return "C1"
    if p >= 41: return "C2"
    if p >= 33: return "D"
    return "E"


def download_storage_file(path):
    if not path:
        return None

    path = str(path).strip()

    if path.startswith("http://") or path.startswith("https://"):
        try:
            response = requests.get(path, timeout=20)
            if response.ok:
                return response.content
        except Exception:
            pass

    for bucket in ["school-assets", "student-photos"]:
        try:
            data = sb.storage.from_(bucket).download(path)
            if data:
                return data
        except Exception:
            pass

    return None


def attendance_summary(student_id, school_id):
    try:
        rows = (
            sb.table("attendance")
            .select("id,attendance_date,present")
            .eq("school_id", school_id)
            .eq("student_id", student_id)
            .execute()
            .data or []
        )
    except Exception:
        return 0, 0

    total_days = len(rows)
    present_days = sum(
        1 for row in rows
        if bool(row.get("present"))
    )
    return total_days, present_days


def school_logo_from_template(template):
    config = get_template_config(template)

    for key in [
        "school_logo_path",
        "logo_path",
        "school_logo",
        "logo"
    ]:
        value = config.get(key)
        if value:
            return str(value).strip()

    return None


def school_logo_size_from_template(template):
    config = get_template_config(template)

    try:
        size = int(config.get("school_logo_size", 52))
    except Exception:
        size = 52

    return max(20, min(30, size))


def pdf_page_size(orientation):

    if orientation == "Landscape":
        return landscape(A4)

    return A4


def draw_wrapped_text(
    pdf,
    text,
    x,
    y,
    width,
    font="Helvetica",
    size=10,
    leading=13
):

    if not text:
        return y

    lines = simpleSplit(
        str(text),
        font,
        size,
        width
    )

    pdf.setFont(font, size)

    for line in lines:

        pdf.drawString(
            x,
            y,
            line
        )

        y -= leading

    return y


def create_report_overlay(
    student,
    school_info,
    subjects,
    marks_rows,
    exam_name,
    orientation,
    total_attendance=0,
    present_days=0,
    school_logo_path=None,
    school_logo_size=52
):

    width, height = pdf_page_size(
        orientation
    )

    buffer = io.BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=(width, height)
    )

    # -----------------------------------------------------
    # Standard A4 positions
    # -----------------------------------------------------

    portrait = orientation != "Landscape"

    if portrait:

        left = 45
        right = width - 45

        photo_x = width - 125
        photo_y = height - 175
        photo_w = 75
        photo_h = 95

        info_y = height - 75

        table_x = 45
        table_y = height - 250
        table_width = width - 90

        remarks_y = 120

        teacher_x = 100
        principal_x = width - 180

    else:

        left = 45
        right = width - 45

        photo_x = width - 145
        photo_y = height - 145
        photo_w = 85
        photo_h = 105

        info_y = height - 65

        table_x = 45
        table_y = height - 190
        table_width = width - 90

        remarks_y = 75

        teacher_x = width * 0.25
        principal_x = width * 0.70

    # -----------------------------------------------------
    # School information
    # -----------------------------------------------------

    school_name = (
        school_info.get("name")
        or "School"
    )

    school_address = (
        school_info.get("address")
        or ""
    )

    pdf.setFont(
        "Helvetica-Bold",
        19
    )

    pdf.drawCentredString(
        width / 2,
        height - 32,
        school_name
    )

    if school_address:

        pdf.setFont(
            "Helvetica",
            8
        )

        pdf.drawCentredString(
            width / 2,
            height - 49,
            school_address
        )

    # School logo on the LEFT side
    if school_logo_path:
        try:
            logo_bytes = download_storage_file(
                school_logo_path
            )

            if logo_bytes:
                logo_image = Image.open(
                    io.BytesIO(logo_bytes)
                ).convert("RGBA")

                from PIL import ImageOps

                # Use a larger logo while keeping it centered on
                # the School Name row. The size can be adjusted in the UI.
                logo_size = max(
                    38,
                    min(60, int(school_logo_size or 50))
                )

                logo_image.thumbnail(
                    (logo_size - 4, logo_size - 4),
                    Image.Resampling.LANCZOS
                )

                logo_buffer = io.BytesIO()
                logo_image.save(
                    logo_buffer,
                    format="PNG"
                )
                logo_buffer.seek(0)

                # Left margin matches the report content margin.
                # Vertically center the larger logo on the School Name row.
                logo_box_x = left
                logo_box_w = logo_size
                logo_box_h = logo_size
                logo_center_y = height - 32
                logo_box_y = (
                    logo_center_y
                    - (logo_box_h / 2)
                )

                pdf.setStrokeColorRGB(
                    0.75, 0.75, 0.75
                )
                pdf.rect(
                    logo_box_x,
                    logo_box_y,
                    logo_box_w,
                    logo_box_h,
                    stroke=1,
                    fill=0
                )

                pdf.drawImage(
                    ImageReader(logo_buffer),
                    logo_box_x + 2,
                    logo_box_y + 2,
                    width=logo_box_w - 4,
                    height=logo_box_h - 4,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto"
                )

        except Exception:
            # Never let a missing logo prevent report generation.
            pass

    pdf.setFont(
        "Helvetica-Bold",
        13
    )

    pdf.drawCentredString(
        width / 2,
        height - 68,
        "REPORT CARD"
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawCentredString(
        width / 2,
        height - 82,
        str(exam_name)    )

    # -----------------------------------------------------
    # Student details
    # -----------------------------------------------------

    detail_y = info_y - 35
    details = [

        (
            "Student Name",
            student.get("name") or "-"        ),

        (
            "Father Name",
            student.get("father_name")
            or student.get("parent_name")
            or "-"
        ),

        (
            "Class",
            student.get("class_name") or "-"
        ),

        (
            "Section",
            student.get("section") or "-"
        ),

        (
            "Admission No.",
            student.get("admission_no") or "-"
        ),

        (
            "Date of Birth",
            student.get("date_of_birth") or "-"
        )
    ]

    pdf.setFont(
        "Helvetica",
        9
    )

    col1_x = left
    col2_x = left + 255

    for index, item in enumerate(details):

        col = index % 2
        row = index // 2

        x = (
            col1_x
            if col == 0
            else col2_x
        )

        y = detail_y - (row * 20)

        label, value = item

        pdf.setFont(
            "Helvetica-Bold",
            9
        )

        pdf.drawString(
            x,
            y,
            f"{label}:"
        )

        pdf.setFont(
            "Helvetica",
            9
        )

        pdf.drawString(
            x + 78,
            y,
            str(value)
        )

    # -----------------------------------------------------
    # Student photo
    # -----------------------------------------------------

    photo_path = student.get("photo_path")

    if photo_path:
        try:
            photo_bytes = download_storage_file(photo_path)

            if photo_bytes:
                from PIL import ImageOps

                image = Image.open(
                    io.BytesIO(photo_bytes)
                ).convert("RGB")

                image = ImageOps.fit(
                    image,
                    (
                        max(1, int(photo_w * 3)),
                        max(1, int(photo_h * 3))
                    ),
                    method=Image.Resampling.LANCZOS
                )

                img_buffer = io.BytesIO()
                image.save(
                    img_buffer,
                    format="PNG"
                )
                img_buffer.seek(0)

                pdf.drawImage(
                    ImageReader(img_buffer),
                    photo_x,
                    photo_y,
                    width=photo_w,
                    height=photo_h,
                    preserveAspectRatio=False,
                    mask="auto"
                )

                pdf.setStrokeColorRGB(
                    0.45, 0.45, 0.45
                )
                pdf.rect(
                    photo_x,
                    photo_y,
                    photo_w,
                    photo_h,
                    stroke=1,
                    fill=0
                )

        except Exception:
            pass

    # -----------------------------------------------------
    # Marks table
    # -----------------------------------------------------

    table_top = table_y

    # Keep every marks-related column comfortably visible.
    subject_col = table_width * 0.38
    max_col = table_width * 0.15
    marks_col = table_width * 0.17
    result_col = table_width * 0.15
    grade_col = table_width * 0.15

    headers = [
        "Subject",
        "Max Marks",
        "Marks Obtained",
        "Result",
        "Grade"
    ]

    x_positions = [
        table_x,
        table_x + subject_col,
        table_x + subject_col + max_col,
        table_x + subject_col + max_col + marks_col,
        table_x + subject_col + max_col + marks_col + result_col
    ]

    subject_count = max(1, len(marks_rows))

    # A4-safe dynamic row height. Do not make rows so small that
    # marks/result/grade become unreadable.
    available_height = max(
        300,
        table_top - (remarks_y + 95)
    )

    row_height = min(
        20,
        max(
            13,
            available_height / (subject_count + 1)
        )
    )

    header_font = 8 if row_height < 16 else 8.5
    body_font = 7.5 if row_height < 16 else 8.5

    pdf.setFont(
        "Helvetica-Bold",
        header_font
    )

    pdf.rect(
        table_x,
        table_top - row_height,
        table_width,
        row_height
    )

    for i in range(1, 5):
        pdf.line(
            x_positions[i],
            table_top,
            x_positions[i],
            table_top - row_height
        )

    # Header alignment
    header_centers = [
        table_x + subject_col / 2,
        x_positions[1] + max_col / 2,
        x_positions[2] + marks_col / 2,
        x_positions[3] + result_col / 2,
        x_positions[4] + grade_col / 2
    ]

    for i, header in enumerate(headers):
        if i == 0:
            pdf.drawString(
                table_x + 4,
                table_top - row_height + max(3, row_height / 2 - 3),
                header
            )
        else:
            pdf.drawCentredString(
                header_centers[i],
                table_top - row_height + max(3, row_height / 2 - 3),
                header
            )

    y = table_top - row_height

    total_marks = 0
    total_max = 0

    pdf.setFont(
        "Helvetica",
        body_font
    )

    for row in marks_rows:

        y -= row_height

        subject_name = (
            row.get("subject_name")
            or row.get("name")
            or "Subject"
        )

        mark_value = row.get("marks")
        max_value = row.get("max_marks")

        try:
            mark_number = float(mark_value)
            mark_display = format_mark(mark_number)
        except Exception:
            mark_number = 0
            mark_display = "-"

        try:
            max_number = float(max_value)
        except Exception:
            max_number = 100

        total_marks += mark_number
        total_max += max_number

        passing = row.get("passing_marks")

        try:
            passing_number = float(passing)
        except Exception:
            passing_number = 0

        if mark_value is None:
            result = "-"
            grade = "-"
        else:
            result = (
                "PASS"
                if mark_number >= passing_number
                else "FAIL"
            )

            row_percentage = (
                (mark_number / max_number) * 100
                if max_number
                else 0
            )

            grade = grade_from_percentage(
                row_percentage
            )

        pdf.rect(
            table_x,
            y,
            table_width,
            row_height
        )

        for i in range(1, 5):
            pdf.line(
                x_positions[i],
                y,
                x_positions[i],
                y + row_height
            )

        baseline = y + max(
            3,
            (row_height - body_font) / 2
        )

        subject_text = str(subject_name)
        if len(subject_text) > 31:
            subject_text = subject_text[:30] + "…"

        # Subject
        pdf.drawString(
            table_x + 4,
            baseline,
            subject_text
        )

        # All numeric/result/grade values are centered in their columns.
        pdf.drawCentredString(
            header_centers[1],
            baseline,
            format_mark(max_number)
        )

        pdf.drawCentredString(
            header_centers[2],
            baseline,
            mark_display
        )

        pdf.drawCentredString(
            header_centers[3],
            baseline,
            result
        )

        pdf.drawCentredString(
            header_centers[4],
            baseline,
            grade
        )

    # -----------------------------------------------------
    # Total / percentage / attendance
    # -----------------------------------------------------

    percentage = (
        (total_marks / total_max) * 100
        if total_max
        else 0
    )

    summary_y = y - 22

    pdf.setFont(
        "Helvetica-Bold",
        9.5
    )

    total_x = table_x
    percentage_x = table_x + table_width * 0.43
    grade_x = table_x + table_width * 0.76

    pdf.drawString(
        total_x,
        summary_y,
        f"Total Marks: {format_mark(total_marks)} / {format_mark(total_max)}"
    )

    pdf.drawString(
        percentage_x,
        summary_y,
        f"Percentage: {percentage:.2f}%"
    )

    overall_grade = grade_from_percentage(
        percentage
    )

    pdf.drawString(
        grade_x,
        summary_y,
        f"Grade: {overall_grade}"
    )

    attendance_y = summary_y - 19

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    # Present Days is directly below the Percentage column.
    pdf.drawString(
        total_x,
        attendance_y,
        f"Total Attendance: {int(total_attendance)}"
    )

    pdf.drawString(
        percentage_x,
        attendance_y,
        f"Present Days: {int(present_days)}"
    )

    # -----------------------------------------------------
    # Remarks
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        table_x,
        remarks_y + 35,
        "Remarks:"
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    draw_wrapped_text(
        pdf,
        student.get("remarks") or "",
        table_x,
        remarks_y + 20,
        table_width,
        "Helvetica",
        9,
        12
    )

    # -----------------------------------------------------
    # Signature labels ONLY
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawCentredString(
        teacher_x,
        45,
        "Teacher Signature"
    )

    pdf.drawCentredString(
        principal_x,
        45,
        "Principal Signature"
    )

    pdf.save()

    buffer.seek(0)

    return buffer.getvalue()


def make_report_card_pdf(
    template_bytes,
    template_type,
    orientation,
    student,
    school_info,
    subjects,
    marks_rows,
    exam_name,
    file_type,
    total_attendance=0,
    present_days=0,
    school_logo_path=None,
    school_logo_size=52
):

    overlay_bytes = create_report_overlay(
        student=student,
        school_info=school_info,
        subjects=subjects,        marks_rows=marks_rows,
        exam_name=exam_name,
        orientation=orientation,
        total_attendance=total_attendance,
        present_days=present_days,
        school_logo_path=school_logo_path,
        school_logo_size=school_logo_size
    )
    overlay_doc = fitz.open(
        stream=overlay_bytes,
        filetype="pdf"
    )

    # -----------------------------------------------------
    # PDF template    # -----------------------------------------------------

    if file_type.lower() == "pdf":

        template_doc = fitz.open(
            stream=template_bytes,
            filetype="pdf"
        )

        if len(template_doc) == 0:

            raise Exception(
                "The PDF template has no pages."
            )

        page = template_doc[0]

        page.show_pdf_page(
            page.rect,
            overlay_doc,
            0,
            overlay=True
        )

        output = template_doc.tobytes(
            garbage=4,
            deflate=True
        )

        template_doc.close()
        overlay_doc.close()

        return output

    # -----------------------------------------------------
    # Image template
    # -----------------------------------------------------

    image = Image.open(
        io.BytesIO(template_bytes)
    ).convert("RGB")

    width, height = pdf_page_size(
        orientation
    )

    base_buffer = io.BytesIO()

    base_pdf = canvas.Canvas(
        base_buffer,
        pagesize=(width, height)
    )

    base_pdf.drawImage(
        ImageReader(image),
        0,
        0,
        width=width,
        height=height,
        preserveAspectRatio=False
    )

    base_pdf.save()

    base_buffer.seek(0)

    base_doc = fitz.open(
        stream=base_buffer.getvalue(),
        filetype="pdf"
    )

    page = base_doc[0]

    page.show_pdf_page(
        page.rect,
        overlay_doc,
        0,
        overlay=True
    )

    output = base_doc.tobytes(
        garbage=4,
        deflate=True
    )

    base_doc.close()
    overlay_doc.close()

    return output



# =========================================================
# MARKS BACKUP / RECOVERY / RESULT WEIGHTAGE
# =========================================================

def build_marks_backup_workbook(school_id):
    """Create a complete Excel backup of the school's exam marks."""
    school = (
        sb.table("schools")
        .select("id,name,code")
        .eq("id", school_id)
        .maybe_single()
        .execute()
        .data
    ) or {}

    exams = get_exam_assessments(school_id, active_only=False)

    students = (
        sb.table("students")
        .select("id,name,admission_no,class_name,section,school_id")
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    subjects = (
        sb.table("subjects")
        .select(
            "id,school_id,class_id,name,subject_name,code,"
            "max_marks,passing_marks,active"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    marks = (
        sb.table("marks")
        .select(
            "id,school_id,student_id,subject_id,exam_name,"
            "marks,max_marks,class_id"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    student_map = {str(x["id"]): x for x in students}
    subject_map = {str(x["id"]): x for x in subjects}

    wb = Workbook()
    info_ws = wb.active
    info_ws.title = "Backup_Info"

    info_rows = [
        ["School ID", str(school_id)],
        ["School Name", school.get("name") or ""],
        ["School Code", school.get("code") or ""],
        ["Backup Created", datetime.datetime.now(datetime.timezone.utc).isoformat()],
        ["Backup Purpose", "Marks backup and recovery"],
        ["Restore Rule", "Rows in exam sheets are matched by Student ID + Subject ID + Exam Name"],
    ]

    info_ws.append(["Key", "Value"])
    for row in info_rows:
        info_ws.append(row)

    for cell in info_ws[1]:
        cell.font = Font(bold=True)

    # Always include all existing exam names, including inactive exams.
    exam_names = []
    for exam in exams:
        name = str(exam.get("name") or "").strip()
        if name and name not in exam_names:
            exam_names.append(name)

    # Also include marks whose exam name may no longer be in exam_assessments.
    for mark in marks:
        name = str(mark.get("exam_name") or "").strip()
        if name and name not in exam_names:
            exam_names.append(name)

    if not exam_names:
        exam_names = ["Marks"]

    used_sheet_names = set()
    for exam_name in exam_names:
        base = exam_name[:31] or "Exam"
        sheet_name = base
        counter = 2
        while sheet_name in used_sheet_names or sheet_name == "Backup_Info":
            suffix = f"_{counter}"
            sheet_name = (base[:31-len(suffix)] + suffix)[:31]
            counter += 1
        used_sheet_names.add(sheet_name)

        ws = wb.create_sheet(sheet_name)
        headers = [
            "School ID", "Exam Name", "Student ID", "Student Name",
            "Admission No.", "Class", "Section", "Subject ID",
            "Subject Name", "Subject Code", "Class ID",
            "Marks", "Maximum Marks", "Passing Marks"
        ]
        ws.append(headers)

        exam_marks = [
            m for m in marks
            if str(m.get("exam_name") or "").strip() == exam_name
        ]

        for mark in exam_marks:
            student = student_map.get(str(mark.get("student_id")), {})
            subject = subject_map.get(str(mark.get("subject_id")), {})

            ws.append([
                str(school_id),
                exam_name,
                str(mark.get("student_id") or ""),
                student.get("name") or "",
                student.get("admission_no") or "",
                student.get("class_name") or "",
                student.get("section") or "",
                str(mark.get("subject_id") or ""),
                subject.get("subject_name") or subject.get("name") or "",
                subject.get("code") or "",
                str(mark.get("class_id") or subject.get("class_id") or ""),
                mark.get("marks"),
                mark.get("max_marks")
                    if mark.get("max_marks") is not None
                    else subject.get("max_marks"),
                subject.get("passing_marks"),
            ])

        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for column in ws.columns:
            max_len = 0
            col_letter = column[0].column_letter
            for cell in column[:300]:
                value = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(value))
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 32)

    # -----------------------------------------------------
    # ANALYSIS SHEETS
    # -----------------------------------------------------
    # These sheets are designed for school result analysis:
    # Exam_Wise, Class_Wise, Students_Wise, Subjects_Wise and Total_All.
    # Total/percentage are calculated from obtained marks / maximum marks.
    # Class toppers in Total_All are highlighted green.
    def _safe_number(value):
        try:
            if value is None or pd.isna(value):
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    enriched = []
    for mark in marks:
        student = student_map.get(str(mark.get("student_id")), {})
        subject = subject_map.get(str(mark.get("subject_id")), {})
        exam = str(mark.get("exam_name") or "").strip()
        if not exam:
            continue

        max_marks = (
            mark.get("max_marks")
            if mark.get("max_marks") is not None
            else subject.get("max_marks")
        )

        enriched.append({
            "Exam": exam,
            "Class": str(student.get("class_name") or "").strip(),
            "Section": str(student.get("section") or "").strip(),
            "Student ID": str(mark.get("student_id") or ""),
            "Student Name": student.get("name") or "",
            "Admission No.": student.get("admission_no") or "",
            "Subject ID": str(mark.get("subject_id") or ""),
            "Subject": subject.get("subject_name") or subject.get("name") or "",
            "Marks": _safe_number(mark.get("marks")),
            "Maximum Marks": _safe_number(max_marks),
            "Passing Marks": _safe_number(subject.get("passing_marks")),
        })

    detail_df = pd.DataFrame(enriched)

    def _write_df(ws, df, widths=None):
        if df.empty:
            ws.append(["No data"])
            return

        ws.append(list(df.columns))
        for row in df.itertuples(index=False, name=None):
            ws.append([
                "" if value is None or (isinstance(value, float) and pd.isna(value))
                else value
                for value in row
            ])

        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill = PatternFill("solid", fgColor="D9EAF7")

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for column in ws.columns:
            max_len = 0
            col_letter = column[0].column_letter
            for cell in column[:1000]:
                value = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(value))
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 32)

    # 1. EXAM_WISE
    exam_rows = []
    if not detail_df.empty:
        for (exam, student_id, student_name, admission, class_name, section), g in detail_df.groupby(
            ["Exam", "Student ID", "Student Name", "Admission No.", "Class", "Section"],
            dropna=False
        ):
            obtained = float(g["Marks"].sum())
            maximum = float(g["Maximum Marks"].sum())
            exam_rows.append({
                "Exam": exam,
                "Class": class_name,
                "Section": section,
                "Student ID": student_id,
                "Student Name": student_name,
                "Admission No.": admission,
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": round((obtained / maximum) * 100, 2) if maximum else 0,
                "Subjects": int(g["Subject ID"].nunique()),
            })

    exam_df = pd.DataFrame(exam_rows)
    if not exam_df.empty:
        exam_df = exam_df.sort_values(
            ["Exam", "Class", "Section", "Percentage", "Student Name"],
            ascending=[True, True, True, False, True]
        )

    ws = wb.create_sheet("Exam_Wise")
    _write_df(ws, exam_df)

    # 2. CLASS_WISE
    class_rows = []
    if not detail_df.empty:
        for (exam, class_name, section), g in detail_df.groupby(
            ["Exam", "Class", "Section"], dropna=False
        ):
            obtained = float(g["Marks"].sum())
            maximum = float(g["Maximum Marks"].sum())
            class_rows.append({
                "Exam": exam,
                "Class": class_name,
                "Section": section,
                "Students": int(g["Student ID"].nunique()),
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": round((obtained / maximum) * 100, 2) if maximum else 0,
                "Average Student %": round(
                    float(
                        exam_df[
                            (exam_df["Exam"] == exam)
                            & (exam_df["Class"] == class_name)
                            & (exam_df["Section"] == section)
                        ]["Percentage"].mean()
                    ), 2
                ) if not exam_df.empty else 0,
            })

    class_df = pd.DataFrame(class_rows)
    if not class_df.empty:
        class_df = class_df.sort_values(
            ["Exam", "Class", "Section"]
        )

    ws = wb.create_sheet("Class_Wise")
    _write_df(ws, class_df)

    # 3. STUDENTS_WISE
    # One row per student per exam, with complete totals and percentage.
    ws = wb.create_sheet("Students_Wise")
    _write_df(ws, exam_df)

    # Highlight each student's row when it is the class topper for that exam.
    if not exam_df.empty:
        for (exam, class_name, section), group in exam_df.groupby(
            ["Exam", "Class", "Section"], dropna=False
        ):
            if group.empty:
                continue
            highest = float(group["Percentage"].max())
            for idx in group.index:
                if float(group.loc[idx, "Percentage"]) == highest:
                    excel_row = int(group.index.get_loc(idx)) + 2
                    # Locate the actual Excel row after sorting.
                    matching_rows = [
                        r for r in range(2, ws.max_row + 1)
                        if str(ws.cell(r, 1).value) == str(exam)
                        and str(ws.cell(r, 2).value) == str(class_name)
                        and str(ws.cell(r, 3).value) == str(section)
                        and str(ws.cell(r, 4).value) == str(group.loc[idx, "Student ID"])
                    ]
                    for excel_row in matching_rows:
                        for cell in ws[excel_row]:
                            cell.fill = PatternFill("solid", fgColor="90EE90")
                            cell.font = Font(bold=True)

    # 4. SUBJECTS_WISE
    subject_rows = []
    if not detail_df.empty:
        for (exam, class_name, section, subject_id, subject), g in detail_df.groupby(
            ["Exam", "Class", "Section", "Subject ID", "Subject"], dropna=False
        ):
            obtained = float(g["Marks"].sum())
            maximum = float(g["Maximum Marks"].sum())
            subject_rows.append({
                "Exam": exam,
                "Class": class_name,
                "Section": section,
                "Subject ID": subject_id,
                "Subject": subject,
                "Students": int(g["Student ID"].nunique()),
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": round((obtained / maximum) * 100, 2) if maximum else 0,
                "Average Marks": round(float(g["Marks"].mean()), 2) if len(g) else 0,
                "Highest Marks": round(float(g["Marks"].max()), 2) if len(g) else 0,
                "Lowest Marks": round(float(g["Marks"].min()), 2) if len(g) else 0,
                "Pass Count": int((g["Marks"] >= g["Passing Marks"]).sum()),
                "Fail Count": int((g["Marks"] < g["Passing Marks"]).sum()),
            })

    subject_df = pd.DataFrame(subject_rows)
    if not subject_df.empty:
        subject_df = subject_df.sort_values(
            ["Exam", "Class", "Section", "Subject"]
        )

    ws = wb.create_sheet("Subjects_Wise")
    _write_df(ws, subject_df)

    # 5. TOTAL_ALL
    # One row per student across all exams. This is the main recovery/result
    # overview and is where class-wise toppers are highlighted green.
    total_rows = []
    if not detail_df.empty:
        for (student_id, student_name, admission, class_name, section), g in detail_df.groupby(
            ["Student ID", "Student Name", "Admission No.", "Class", "Section"],
            dropna=False
        ):
            obtained = float(g["Marks"].sum())
            maximum = float(g["Maximum Marks"].sum())
            total_rows.append({
                "Class": class_name,
                "Section": section,
                "Student ID": student_id,
                "Student Name": student_name,
                "Admission No.": admission,
                "Exams": int(g["Exam"].nunique()),
                "Subjects": int(g["Subject ID"].nunique()),
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": round((obtained / maximum) * 100, 2) if maximum else 0,
            })

    total_df = pd.DataFrame(total_rows)
    if not total_df.empty:
        total_df = total_df.sort_values(
            ["Class", "Section", "Percentage", "Student Name"],
            ascending=[True, True, False, True]
        )

    ws = wb.create_sheet("Total_All")
    _write_df(ws, total_df)

    # Green = class topper. Ties are also highlighted.
    if not total_df.empty:
        for (class_name, section), group in total_df.groupby(
            ["Class", "Section"], dropna=False
        ):
            if group.empty:
                continue
            highest = float(group["Percentage"].max())
            for _, student_row in group.iterrows():
                if float(student_row["Percentage"]) == highest:
                    matches = [
                        r for r in range(2, ws.max_row + 1)
                        if str(ws.cell(r, 1).value) == str(class_name)
                        and str(ws.cell(r, 2).value) == str(section)
                        and str(ws.cell(r, 3).value) == str(student_row["Student ID"])
                    ]
                    for excel_row in matches:
                        for cell in ws[excel_row]:
                            cell.fill = PatternFill("solid", fgColor="90EE90")
                            cell.font = Font(bold=True)

    # Add a legend at the top-right area without disturbing the table.
    if not total_df.empty:
        legend_col = max(12, ws.max_column + 2)
        ws.cell(1, legend_col, "GREEN = CLASS TOPPER")
        ws.cell(1, legend_col).fill = PatternFill("solid", fgColor="90EE90")
        ws.cell(1, legend_col).font = Font(bold=True)

    # Add student and subject master data to make the backup self-contained.
    for title, rows, headers in [
        (
            "Students",
            students,
            ["Student ID", "Name", "Admission No.", "Class", "Section"]
        ),
        (
            "Subjects",
            subjects,
            ["Subject ID", "Subject Name", "Code", "Class ID", "Maximum Marks", "Passing Marks", "Active"]
        ),
    ]:
        ws = wb.create_sheet(title)
        ws.append(headers)
        for item in rows:
            if title == "Students":
                ws.append([
                    str(item.get("id") or ""),
                    item.get("name") or "",
                    item.get("admission_no") or "",
                    item.get("class_name") or "",
                    item.get("section") or "",
                ])
            else:
                ws.append([
                    str(item.get("id") or ""),
                    item.get("subject_name") or item.get("name") or "",
                    item.get("code") or "",
                    str(item.get("class_id") or ""),
                    item.get("max_marks"),
                    item.get("passing_marks"),
                    item.get("active"),
                ])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def restore_marks_from_backup(uploaded_file, school_id):
    """Restore marks from a previously generated workbook."""
    workbook = pd.read_excel(
        uploaded_file,
        sheet_name=None,
        engine="openpyxl"
    )

    info = workbook.get("Backup_Info")
    if info is None or info.empty:
        raise ValueError("This is not a valid School Marks Backup file.")

    info_map = {}
    for _, row in info.iterrows():
        if len(row) >= 2:
            key = str(row.iloc[0]).strip()
            info_map[key] = row.iloc[1]

    backup_school_id = str(info_map.get("School ID") or "").strip()
    if backup_school_id and backup_school_id != str(school_id):
        raise ValueError(
            "This backup belongs to another school. "
            "Restore was stopped for safety."
        )

    students = (
        sb.table("students")
        .select("id,school_id")
        .eq("school_id", school_id)
        .execute()
        .data or []
    )
    subjects = (
        sb.table("subjects")
        .select("id,school_id,max_marks")
        .eq("school_id", school_id)
        .execute()
        .data or []
    )
    existing = (
        sb.table("marks")
        .select(
            "id,student_id,subject_id,exam_name,marks,max_marks,class_id"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    valid_students = {str(x["id"]) for x in students}
    valid_subjects = {str(x["id"]): x for x in subjects}
    existing_map = {
        (
            str(x.get("student_id")),
            str(x.get("subject_id")),
            str(x.get("exam_name") or "").strip()
        ): x
        for x in existing
    }

    updates = []
    inserts = []
    skipped = []
    restored = 0

    for sheet_name, df in workbook.items():
        if sheet_name in {"Backup_Info", "Students", "Subjects"}:
            continue
        if df is None or df.empty:
            continue

        normalized = {
            str(c).strip().lower(): c
            for c in df.columns
        }
        required = ["student id", "subject id", "marks"]
        if any(x not in normalized for x in required):
            skipped.append(
                f"{sheet_name}: missing required columns."
            )
            continue

        for _, row in df.iterrows():
            student_id = str(row.get(normalized["student id"]) or "").strip()
            subject_id = str(row.get(normalized["subject id"]) or "").strip()
            raw_marks = row.get(normalized["marks"])

            exam_col = normalized.get("exam name")
            class_col = normalized.get("class id")
            max_col = normalized.get("maximum marks")

            exam_name = (
                str(row.get(exam_col) or sheet_name).strip()
                if exam_col else sheet_name
            )

            if not student_id or not subject_id:
                continue
            if student_id not in valid_students:
                skipped.append(
                    f"{sheet_name}: unknown Student ID {student_id}."
                )
                continue
            if subject_id not in valid_subjects:
                skipped.append(
                    f"{sheet_name}: unknown Subject ID {subject_id}."
                )
                continue
            if raw_marks is None or pd.isna(raw_marks) or str(raw_marks).strip() == "":
                continue

            try:
                mark_value = round(float(raw_marks), 2)
            except Exception:
                skipped.append(
                    f"{sheet_name}: invalid marks for {student_id}/{subject_id}."
                )
                continue

            subject_info = valid_subjects[subject_id]
            max_marks = subject_info.get("max_marks")
            if max_col:
                try:
                    if not pd.isna(row.get(max_col)):
                        max_marks = float(row.get(max_col))
                except Exception:
                    pass

            if max_marks is not None and mark_value > float(max_marks):
                skipped.append(
                    f"{sheet_name}: {mark_value:.2f} exceeds maximum "
                    f"{format_mark(float(max_marks))} for {student_id}/{subject_id}."
                )
                continue
            if mark_value < 0:
                skipped.append(
                    f"{sheet_name}: negative marks for {student_id}/{subject_id}."
                )
                continue

            class_id = None
            if class_col:
                value = row.get(class_col)
                if value is not None and not pd.isna(value):
                    class_id = str(value).strip() or None

            key = (student_id, subject_id, exam_name)
            old = existing_map.get(key)

            if old:
                updates.append({
                    "id": old["id"],
                    "marks": mark_value,
                    "max_marks": max_marks,
                    "class_id": class_id or old.get("class_id")
                })
            else:
                inserts.append({
                    "school_id": school_id,
                    "student_id": student_id,
                    "subject_id": subject_id,
                    "exam_name": exam_name,
                    "marks": mark_value,
                    "max_marks": max_marks,
                    "class_id": class_id
                })
            restored += 1

    for item in inserts:
        sb.table("marks").insert(item).execute()

    for item in updates:
        sb.table("marks").update({
            "marks": item["marks"],
            "max_marks": item["max_marks"],
            "class_id": item["class_id"]
        }).eq("id", item["id"]).execute()

    return restored, len(inserts), len(updates), skipped


def get_school_academic_year(school_id):
    try:
        rows = (
            sb.table("classes")
            .select("academic_year")
            .eq("school_id", school_id)
            .eq("active", True)
            .order("academic_year", desc=True)
            .limit(1)
            .execute()
            .data or []
        )
        if rows and rows[0].get("academic_year"):
            return str(rows[0]["academic_year"])
    except Exception:
        pass
    return ""


def get_exam_result_weights(school_id, academic_year):
    try:
        rows = (
            sb.table("exam_result_weights")
            .select("exam_id,weight_percent")
            .eq("school_id", school_id)
            .eq("academic_year", academic_year)
            .execute()
            .data or []
        )
        return {
            str(x.get("exam_id")): float(x.get("weight_percent") or 0)
            for x in rows
        }
    except Exception:
        return {}


def marks_backup_and_result_tools(school_id):
    role = st.session_state.profile.get("role")

    if role not in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        return

    st.subheader("📦 Marks Backup, Recovery & Result Weightage")
    st.caption(
        "Download a complete Excel backup of all exams for this school. "
        "Each exam is kept in a separate Excel sheet."
    )

    # -----------------------------------------------------
    # DIRECT EXCEL DOWNLOAD
    # -----------------------------------------------------
    # Always prepare the current backup so the Download Excel
    # button is immediately visible. No extra Create button is required.
    try:
        current_backup = build_marks_backup_workbook(school_id)
        school_name = (
            str(st.session_state.get("selected_school_name") or "School")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )
        backup_stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        direct_name = f"{school_name}_All_Exam_Marks_Backup_{backup_stamp}.xlsx"

        st.download_button(
            "⬇️ Download All Exam Marks Excel",
            data=current_backup,
            file_name=direct_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"direct_all_exam_marks_download_{school_id}"
        )
        st.success(
            "✅ Excel backup is ready. It contains separate sheets for PT-1, "
            "PT-2, Half Yearly, Annual and other exams available in this school."
        )
    except Exception as e:
        st.error("Could not prepare the current Excel marks backup.")
        st.code(str(e))

    # Backup created immediately after Save All Marks.
    pending_bytes = st.session_state.pop("_marks_backup_bytes", None)
    pending_name = st.session_state.pop("_marks_backup_filename", None)
    if pending_bytes:
        st.download_button(
            "⬇️ Download Fresh Backup After Last Marks Update",
            data=pending_bytes,
            file_name=pending_name or "School_Marks_Backup.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"fresh_marks_backup_download_{school_id}"
        )

    st.divider()

    # -----------------------------------------------------
    # GOOGLE SHEETS / DRIVE
    # -----------------------------------------------------
    st.markdown("### ☁️ Google Sheets / Google Drive")
    st.caption(
        "Sync the current marks backup to this school's Google Sheet and "
        "save a dated .xlsx copy in Google Drive."
    )

    if not st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        st.warning(
            "Google backup is not connected yet. The Excel download above "
            "works without Google. Add GOOGLE_SERVICE_ACCOUNT_JSON to "
            "Streamlit Secrets to enable Google Sheets + Drive."
        )
    else:
        if st.button(
            "☁️ Sync All Exam Marks to Google Sheets + Drive",
            use_container_width=True,
            key=f"sync_google_marks_report_{school_id}"
        ):
            try:
                result = sync_school_marks_to_google(school_id)
                st.session_state["_google_marks_sheet_url"] = result["spreadsheet_url"]
                st.session_state["_google_marks_xlsx_name"] = result["xlsx_name"]
                st.success("✅ Google Sheet and dated Excel backup updated.")
                st.markdown(
                    f"[📊 Open School Google Sheet]({result['spreadsheet_url']})"
                )
                st.caption(
                    f"📁 Dated Excel saved in Google Drive: {result['xlsx_name']}"
                )
            except Exception as e:
                st.error("Google backup could not be completed.")
                st.code(str(e))

        saved_sheet_url = st.session_state.get("_google_marks_sheet_url")
        if saved_sheet_url:
            st.markdown(
                f"[📊 Open Last Synced Google Sheet]({saved_sheet_url})"
            )

    st.divider()

    # -----------------------------------------------------
    # RECOVERY
    # -----------------------------------------------------
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("### ♻️ Recover Marks")
        uploaded_backup = st.file_uploader(
            "Upload a previous Marks Backup Excel",
            type=["xlsx"],
            key=f"marks_restore_upload_{school_id}"
        )

        if uploaded_backup:
            if st.button(
                "🔍 Validate Backup",
                use_container_width=True,
                key=f"validate_marks_backup_{school_id}"
            ):
                try:
                    sheets = pd.read_excel(
                        uploaded_backup,
                        sheet_name=None,
                        engine="openpyxl"
                    )
                    summary = []
                    for name, df in sheets.items():
                        if name not in {"Backup_Info", "Students", "Subjects"}:
                            summary.append({
                                "Exam / Sheet": name,
                                "Rows": int(len(df))
                            })
                    st.session_state["_validated_backup_name"] = uploaded_backup.name
                    st.session_state["_validated_backup_summary"] = summary
                    st.success("Backup validated. Review the rows below before restoring.")
                except Exception as e:
                    st.error("This Excel file could not be validated.")
                    st.code(str(e))

        summary = st.session_state.get("_validated_backup_summary")
        if summary:
            st.dataframe(
                pd.DataFrame(summary),
                hide_index=True,
                use_container_width=True
            )
            if st.button(
                "♻️ Restore Marks From This Backup",
                type="primary",
                use_container_width=True,
                key=f"restore_marks_backup_{school_id}"
            ):
                try:
                    restored, inserted, updated, skipped = restore_marks_from_backup(
                        uploaded_backup,
                        school_id
                    )
                    st.success(
                        f"Restored {restored} mark rows "
                        f"({inserted} new, {updated} updated)."
                    )
                    if skipped:
                        st.warning(
                            f"{len(skipped)} rows were skipped. Check the details below."
                        )
                        for item in skipped[:30]:
                            st.caption(item)
                    st.session_state.pop("_validated_backup_summary", None)
                    st.rerun()
                except Exception as e:
                    st.error("Could not restore the backup.")
                    st.code(str(e))

    with c2:
        st.markdown("### ⚖️ Exam Result Weightage")

        exams = get_exam_assessments(school_id, active_only=True)
        academic_year = get_school_academic_year(school_id)

        if not exams:
            st.info("Create exams first in Exam / Assessment.")
        elif not academic_year:
            st.warning("Academic Session is not available in the school's active classes.")
        else:
            current_weights = get_exam_result_weights(school_id, academic_year)
            weight_table = []
            for exam in exams:
                weight_table.append({
                    "Exam": exam.get("name") or "",
                    "Exam ID": str(exam.get("id")),
                    "Weight %": current_weights.get(str(exam.get("id")), 0.0)
                })

            weight_df = pd.DataFrame(weight_table)
            edited_weights = st.data_editor(
                weight_df,
                hide_index=True,
                use_container_width=True,
                disabled=["Exam", "Exam ID"],
                column_config={
                    "Weight %": st.column_config.NumberColumn(
                        "Weight %",
                        min_value=0.0,
                        max_value=100.0,
                        step=1.0,
                        format="%.2f"
                    )
                },
                key=f"exam_weight_editor_{school_id}_{academic_year}"
            )

            total_weight = float(
                pd.to_numeric(
                    edited_weights["Weight %"],
                    errors="coerce"
                ).fillna(0).sum()
            )
            if abs(total_weight - 100.0) > 0.01:
                st.warning(
                    f"Current weight total is {total_weight:g}%. "
                    "Use 100% when these exams together make the final result."
                )
            else:
                st.success("✅ Weight total is 100%.")

            if st.button(
                "💾 Save Exam Weightage",
                type="primary",
                use_container_width=True,
                key=f"save_exam_weights_{school_id}"
            ):
                try:
                    for _, row in edited_weights.iterrows():
                        exam_id = str(row["Exam ID"])
                        weight = float(row["Weight %"] or 0)
                        sb.table("exam_result_weights").upsert({
                            "school_id": school_id,
                            "academic_year": academic_year,
                            "exam_id": exam_id,
                            "weight_percent": weight,
                            "updated_at": datetime.datetime.now(
                                datetime.timezone.utc
                            ).isoformat()
                        }).execute()

                    mark_saved(f"save_exam_weights_{school_id}")
                    st.success("✅ Exam weightage saved successfully.")
                    st.rerun()
                except Exception as e:
                    st.error(
                        "Could not save exam weightage. "
                        "Run the exam_result_weights SQL setup first if this is the first time."
                    )
                    st.code(str(e))

            st.caption(
                "Example: PT-1 10%, PT-2 10%, Half Yearly 30%, Annual 50%. "
                "Raw exam marks are never changed; weightage is used only for the final result."
            )

def get_google_services():
    """Return Google Sheets and Drive clients when configured in Streamlit secrets."""
    if service_account is None or google_build is None:
        raise RuntimeError(
            "Google API packages are not installed. Add the Google packages to requirements.txt."
        )

    raw = st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not configured in Streamlit Secrets."
        )

    if isinstance(raw, str):
        info = json.loads(raw)
    else:
        info = dict(raw)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=scopes
    )

    return (
        google_build("sheets", "v4", credentials=creds),
        google_build("drive", "v3", credentials=creds)
    )


def _google_drive_download_bytes(drive_service, file_id, mime_type=None):
    """Download an XLSX or export a Google Sheet as XLSX."""
    buffer = io.BytesIO()
    if mime_type:
        request = drive_service.files().export_media(
            fileId=file_id,
            mimeType=mime_type
        )
    else:
        request = drive_service.files().get_media(fileId=file_id)

    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.getvalue()


def _google_school_name(school_id):
    row = (
        sb.table("schools")
        .select("id,name,code")
        .eq("id", school_id)
        .maybe_single()
        .execute()
        .data
    ) or {}
    return str(row.get("name") or "School").strip()


def _share_drive_file(drive_service, file_id, email, role="reader"):
    try:
        drive_service.permissions().create(
            fileId=file_id,
            body={
                "type": "user",
                "role": role,
                "emailAddress": email
            },
            sendNotificationEmail=False
        ).execute()
    except Exception:
        # Existing permission / non-Google account should not stop backup.
        pass


def _google_target_emails(school_id):
    """Return only users who are allowed to access this school's files."""
    role = st.session_state.profile.get("role")
    current_email = str(
        st.session_state.profile.get("email") or ""
    ).strip()

    profiles = (
        sb.table("profiles")
        .select("email,role,school_id,active")
        .execute()
        .data or []
    )

    emails = set()
    for profile in profiles:
        if not bool(profile.get("active", True)):
            continue
        email = str(profile.get("email") or "").strip()
        p_role = profile.get("role")
        same_school = str(profile.get("school_id")) == str(school_id)

        if not email:
            continue

        if p_role == "SuperAdmin":
            emails.add(email)
        elif same_school and p_role in ["Admin", "Admin+Teacher"]:
            emails.add(email)

    # Always include the current user when they are an allowed school role.
    if current_email and role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        if role == "SuperAdmin" or str(
            st.session_state.profile.get("school_id")
        ) == str(school_id):
            emails.add(current_email)

    return emails


def backup_report_cards_excel_to_google(school_id, filename, excel_bytes):
    """Upload the exact Report Card Excel bytes to Google Drive and share view-only.
    Older backups are never deleted or replaced.
    """
    _, drive_service = get_google_services()

    school_name = _google_school_name(school_id)
    safe_name = (
        school_name.replace("'", "")
        .replace("/", "_")
        .replace("\\", "_")
    )

    media = MediaIoBaseUpload(
        io.BytesIO(excel_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=False
    )

    drive_file = (
        drive_service.files()
        .create(
            body={
                "name": filename,
                "description": (
                    f"Report Card Excel backup for school {school_id}. "
                    "Permanent backup; created by the school management app."
                ),
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            },
            media_body=media,
            fields="id,name,webViewLink,createdTime"
        )
        .execute()
    )

    # Report Card backups are VIEW-ONLY for SuperAdmins and the
    # active Admin/Admin+Teacher users of the same school.
    for email in sorted(_google_target_emails(school_id)):
        _share_drive_file(
            drive_service,
            drive_file.get("id"),
            email,
            "reader"
        )

    return drive_file


def sync_school_marks_to_google(school_id):
    """Create/update a school Google Sheet and dated XLSX backup in Drive."""
    sheets_service, drive_service = get_google_services()

    school_name = _google_school_name(school_id)
    safe_name = (
        school_name.replace("'", "")
        .replace("/", "_")
        .replace("\\", "_")
    )

    spreadsheet_title = f"{safe_name} - Marks Backup"
    query_name = spreadsheet_title.replace("\\", "\\\\").replace("'", "\\'")

    found = (
        drive_service.files()
        .list(
            q=(
                f"name = '{query_name}' and "
                "mimeType = 'application/vnd.google-apps.spreadsheet' and "
                "trashed = false"
            ),
            spaces="drive",
            fields="files(id,name,webViewLink)",
            pageSize=10
        )
        .execute()
        .get("files", [])
    )

    if found:
        spreadsheet_id = found[0]["id"]
    else:
        created = (
            sheets_service.spreadsheets()
            .create(
                body={"properties": {"title": spreadsheet_title}},
                fields="spreadsheetId,spreadsheetUrl"
            )
            .execute()
        )
        spreadsheet_id = created["spreadsheetId"]

    backup_bytes = build_marks_backup_workbook(school_id)
    workbook = pd.read_excel(
        io.BytesIO(backup_bytes),
        sheet_name=None,
        engine="openpyxl"
    )

    metadata = (
        sheets_service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id)
        .execute()
    )
    existing_sheets = {
        x.get("properties", {}).get("title")
        for x in metadata.get("sheets", [])
    }

    requests_body = []
    for sheet_name in workbook.keys():
        if sheet_name not in existing_sheets:
            requests_body.append({
                "addSheet": {
                    "properties": {"title": sheet_name[:100]}
                }
            })

    if requests_body:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests_body}
        ).execute()

    for sheet_name, dataframe in workbook.items():
        values = [list(dataframe.columns)]
        for row in dataframe.itertuples(index=False, name=None):
            clean = []
            for value in row:
                if pd.isna(value):
                    clean.append("")
                elif isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
                    clean.append(str(value))
                else:
                    clean.append(value)
            values.append(clean)

        if sheet_name == "Backup_Info":
            values = [
                [str(x) if not pd.isna(x) else "" for x in row]
                for row in dataframe.astype(object).values.tolist()
            ]

        safe_sheet = sheet_name.replace("'", "''")
        (
            sheets_service.spreadsheets()
            .values()
            .clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{safe_sheet}'"
            )
            .execute()
        )
        (
            sheets_service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=f"'{safe_sheet}'!A1",
                valueInputOption="RAW",
                body={"values": values}
            )
            .execute()
        )

    log_name = "Backup_Log"
    if log_name not in existing_sheets:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [{
                    "addSheet": {
                        "properties": {
                            "title": log_name
                        }
                    }
                }]
            }
        ).execute()

    log_values = [
        datetime.datetime.now(datetime.timezone.utc).isoformat(),
        str(st.session_state.profile.get("email") or ""),
        "Marks backup sync",
        str(school_id),
        str(len(workbook)),
    ]
    (
        sheets_service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range="'Backup_Log'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [log_values]}
        )
        .execute()
    )

    backup_stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    xlsx_name = f"{safe_name}_Marks_Backup_{backup_stamp}.xlsx"

    media = MediaIoBaseUpload(
        io.BytesIO(backup_bytes),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        resumable=False
    )
    drive_file = (
        drive_service.files()
        .create(
            body={"name": xlsx_name},
            media_body=media,
            fields="id,name,webViewLink"
        )
        .execute()
    )

    # School Admin/Admin+Teacher = VIEW ONLY.
    # SuperAdmin = VIEW ONLY across all schools.
    target_emails = _google_target_emails(school_id)
    for email in sorted(target_emails):
        _share_drive_file(drive_service, spreadsheet_id, email, "reader")
        _share_drive_file(drive_service, drive_file.get("id"), email, "reader")

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "xlsx_file_id": drive_file.get("id"),
        "xlsx_name": xlsx_name
    }


def list_google_school_backups():
    """List Google Sheets and XLSX backups visible to the current role."""
    _, drive_service = get_google_services()
    role = st.session_state.profile.get("role")
    current_school_id = st.session_state.profile.get("school_id")

    if role == "SuperAdmin":
        school_rows = (
            sb.table("schools")
            .select("id,name,code")
            .order("name")
            .execute()
            .data or []
        )
    elif role in ["Admin", "Admin+Teacher"]:
        school_rows = (
            sb.table("schools")
            .select("id,name,code")
            .eq("id", current_school_id)
            .execute()
            .data or []
        )
    else:
        return []

    results = []
    for school in school_rows:
        school_id = str(school.get("id"))
        school_name = str(school.get("name") or "School").strip()
        safe_name = (
            school_name.replace("'", "")
            .replace("/", "_")
            .replace("\\", "_")
        )
        spreadsheet_title = f"{safe_name} - Marks Backup"
        q_name = spreadsheet_title.replace("\\", "\\\\").replace("'", "\\'")

        spreadsheets = (
            drive_service.files()
            .list(
                q=(
                    f"name = '{q_name}' and "
                    "mimeType = 'application/vnd.google-apps.spreadsheet' and "
                    "trashed = false"
                ),
                spaces="drive",
                fields="files(id,name,webViewLink,modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=10
            )
            .execute()
            .get("files", [])
        )

        xlsx_files = (
            drive_service.files()
            .list(
                q=(
                    f"name contains '{safe_name}_Marks_Backup_' and "
                    "mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' and "
                    "trashed = false"
                ),
                spaces="drive",
                fields="files(id,name,webViewLink,modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=50
            )
            .execute()
            .get("files", [])
        )

        report_card_xlsx_files = (
            drive_service.files()
            .list(
                q=(
                    f"name contains '{safe_name}_Report_Cards_Backup_' and "
                    "mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' and "
                    "trashed = false"
                ),
                spaces="drive",
                fields="files(id,name,webViewLink,modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=50
            )
            .execute()
            .get("files", [])
        )

        results.append({
            "school_id": school_id,
            "school_name": school_name,
            "school_code": school.get("code") or "",
            "sheet": spreadsheets[0] if spreadsheets else None,
            "xlsx": xlsx_files,
            "report_card_xlsx": report_card_xlsx_files
        })

    return results


def google_marks_backup_section(school_id):
    role = st.session_state.profile.get("role")
    if role not in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        return

    st.markdown("### ☁️ Google Sheets / Google Drive Backup")
    if role == "SuperAdmin":
        st.caption(
            "SuperAdmin can view and download Google Excel backups for every school."
        )
    else:
        st.caption(
            "You can view and download only your own school's Google Excel backups. "
            "Google files are view-only from the school account."
        )

    if not st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        st.info(
            "Add GOOGLE_SERVICE_ACCOUNT_JSON to Streamlit Secrets to enable Google Drive."
        )
        return

    # Sync only the currently selected school. The created Google files are
    # immediately shared as VIEW-ONLY with the correct school users and all SuperAdmins.
    if st.button(
        "☁️ Sync This School to Google Sheets + Drive",
        use_container_width=True,
        key=f"sync_google_marks_{school_id}"
    ):
        try:
            result = sync_school_marks_to_google(school_id)
            st.success("✅ Google Excel backup updated and shared.")
            st.markdown(
                f"[👁️ View Google Sheet]({result['spreadsheet_url']})"
            )
        except Exception as e:
            st.error("Google backup could not be completed.")
            st.code(str(e))

    try:
        backup_groups = list_google_school_backups()
    except Exception as e:
        st.error("Google Drive files could not be loaded.")
        st.code(str(e))
        return

    if not backup_groups:
        st.info("No Google Excel backup is available yet.")
        return

    for group in backup_groups:
        st.markdown(f"#### 🏫 {group['school_name']}")
        sheet = group.get("sheet")
        if sheet:
            sheet_id = sheet.get("id")
            st.markdown(
                f"[👁️ View Google Excel]({sheet.get('webViewLink') or ('https://docs.google.com/spreadsheets/d/' + sheet_id + '/edit')})"
            )
            try:
                sheet_bytes = _google_drive_download_bytes(
                    get_google_services()[1],
                    sheet_id,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.download_button(
                    "⬇️ Download Current Google Excel",
                    data=sheet_bytes,
                    file_name=f"{group['school_name']}_Marks_Backup.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_google_sheet_{group['school_id']}"
                )
            except Exception as e:
                st.warning(f"Current Google Excel download unavailable: {e}")

        for file_info in group.get("report_card_xlsx", [])[:20]:
            file_id = file_info.get("id")
            st.markdown(
                f"[📄 View Report Card Backup: {file_info.get('name')}]({file_info.get('webViewLink') or ('https://drive.google.com/file/d/' + file_id + '/view')})"
            )
            try:
                report_bytes = _google_drive_download_bytes(
                    get_google_services()[1],
                    file_id
                )
                st.download_button(
                    "⬇️ Download Report Card Backup",
                    data=report_bytes,
                    file_name=file_info.get("name") or "Report_Cards_Backup.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_google_report_card_xlsx_{file_id}"
                )
            except Exception as e:
                st.warning(f"Report Card backup download unavailable: {e}")

        for file_info in group.get("xlsx", [])[:10]:
            file_id = file_info.get("id")
            st.markdown(
                f"[📁 View Drive XLSX: {file_info.get('name')}]({file_info.get('webViewLink') or ('https://drive.google.com/file/d/' + file_id + '/view')})"
            )
            try:
                xlsx_bytes = _google_drive_download_bytes(
                    get_google_services()[1],
                    file_id
                )
                st.download_button(
                    "⬇️ Download dated XLSX",
                    data=xlsx_bytes,
                    file_name=file_info.get("name") or "Marks_Backup.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"download_google_xlsx_{file_id}"
                )
            except Exception as e:
                st.warning(f"Download unavailable: {e}")


# =========================================================
# REPORT CARD GENERATOR
# =========================================================



# =========================================================
# REPORT CARD HELPERS
# =========================================================

# =========================================================
# REPORT CARD HELPERS
# =========================================================

def get_template_config(template):

    try:
        value = template.get("config_json")

        if isinstance(value, dict):
            return dict(value)

        if isinstance(value, str) and value.strip():
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed

    except Exception:
        pass

    return {}


def grade_from_percentage(percentage):
    try:
        p = float(percentage)
    except Exception:
        p = 0

    if p >= 91: return "A1"
    if p >= 81: return "A2"
    if p >= 71: return "B1"
    if p >= 61: return "B2"
    if p >= 51: return "C1"
    if p >= 41: return "C2"
    if p >= 33: return "D"
    return "E"


def download_storage_file(path):
    if not path:
        return None

    path = str(path).strip()

    if path.startswith("http://") or path.startswith("https://"):
        try:
            response = requests.get(path, timeout=20)
            if response.ok:
                return response.content
        except Exception:
            pass

    for bucket in ["school-assets", "student-photos"]:
        try:
            data = sb.storage.from_(bucket).download(path)
            if data:
                return data
        except Exception:
            pass

    return None


def attendance_summary(student_id, school_id):
    try:
        rows = (
            sb.table("attendance")
            .select("id,attendance_date,present")
            .eq("school_id", school_id)
            .eq("student_id", student_id)
            .execute()
            .data or []
        )
    except Exception:
        return 0, 0

    total_days = len(rows)
    present_days = sum(
        1 for row in rows
        if bool(row.get("present"))
    )
    return total_days, present_days


def school_logo_from_template(template):
    config = get_template_config(template)

    for key in [
        "school_logo_path",
        "logo_path",
        "school_logo",
        "logo"
    ]:
        value = config.get(key)
        if value:
            return str(value).strip()

    return None


def school_logo_size_from_template(template):
    config = get_template_config(template)

    try:
        size = int(config.get("school_logo_size", 52))
    except Exception:
        size = 52

    # 52 pt is the normal/original display size.
    # The slider can make the logo smaller or larger.
    return max(30, min(80, size))


def pdf_page_size(orientation):

    if orientation == "Landscape":
        return landscape(A4)

    return A4


def draw_wrapped_text(
    pdf,
    text,
    x,
    y,
    width,
    font="Helvetica",
    size=10,
    leading=13
):

    if not text:
        return y

    lines = simpleSplit(
        str(text),
        font,
        size,
        width
    )

    pdf.setFont(font, size)

    for line in lines:

        pdf.drawString(
            x,
            y,
            line
        )

        y -= leading

    return y


def create_report_overlay(
    student,
    school_info,
    subjects,
    marks_rows,
    exam_name,
    orientation,
    total_attendance=0,
    present_days=0,
    school_logo_path=None,
    school_logo_size=52
):

    width, height = pdf_page_size(
        orientation
    )

    buffer = io.BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=(width, height)
    )

    # -----------------------------------------------------
    # Standard A4 positions
    # -----------------------------------------------------

    portrait = orientation != "Landscape"

    if portrait:

        left = 45
        right = width - 45

        photo_x = width - 125
        photo_y = height - 175
        photo_w = 75
        photo_h = 95

        info_y = height - 75

        table_x = 45
        table_y = height - 250
        table_width = width - 90

        remarks_y = 120

        teacher_x = 100
        principal_x = width - 180

    else:

        left = 45
        right = width - 45

        photo_x = width - 145
        photo_y = height - 145
        photo_w = 85
        photo_h = 105

        info_y = height - 65

        table_x = 45
        table_y = height - 190
        table_width = width - 90

        remarks_y = 75

        teacher_x = width * 0.25
        principal_x = width * 0.70

    # -----------------------------------------------------
    # School information
    # -----------------------------------------------------

    school_name = (
        school_info.get("name")
        or "School"
    )

    school_address = (
        school_info.get("address")
        or ""
    )

    pdf.setFont(
        "Helvetica-Bold",
        19
    )

    pdf.drawCentredString(
        width / 2,
        height - 38,
        school_name
    )

    if school_address:

        pdf.setFont(
            "Helvetica",
            8
        )

        pdf.drawCentredString(
            width / 2,
            height - 49,
            school_address
        )

    # School logo on the LEFT side
    if school_logo_path:
        try:
            logo_bytes = download_storage_file(
                school_logo_path
            )

            if logo_bytes:
                logo_image = Image.open(
                    io.BytesIO(logo_bytes)
                ).convert("RGBA")

                from PIL import ImageOps

                # Keep 52 pt as the normal/original logo size.
                # The saved slider value can make it smaller or larger.
                logo_size = max(
                    30,
                    min(80, int(school_logo_size or 52))
                )

                logo_image.thumbnail(
                    (logo_size - 4, logo_size - 4),
                    Image.Resampling.LANCZOS
                )

                logo_buffer = io.BytesIO()
                logo_image.save(
                    logo_buffer,
                    format="PNG"
                )
                logo_buffer.seek(0)

                # Keep the same left margin and align the logo
                # vertically with the lowered School Name.
                logo_box_x = left
                logo_box_w = logo_size
                logo_box_h = logo_size
                # Keep the logo fully inside the School Name
                # header row. Its top edge must not rise above
                # the School Name row.
                logo_top_y = height - 24
                logo_box_y = (
                    logo_top_y
                    - logo_box_h
                )

                pdf.setStrokeColorRGB(
                    0.75, 0.75, 0.75
                )
                pdf.rect(
                    logo_box_x,
                    logo_box_y,
                    logo_box_w,
                    logo_box_h,
                    stroke=1,
                    fill=0
                )

                pdf.drawImage(
                    ImageReader(logo_buffer),
                    logo_box_x + 2,
                    logo_box_y + 2,
                    width=logo_box_w - 4,
                    height=logo_box_h - 4,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto"
                )

        except Exception:
            # Never let a missing logo prevent report generation.
            pass

    pdf.setFont(
        "Helvetica-Bold",
        13
    )

    pdf.drawCentredString(
        width / 2,
        height - 68,
        "REPORT CARD"
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    pdf.drawCentredString(
        width / 2,
        height - 82,
        str(exam_name)    )

    # -----------------------------------------------------
    # Student details
    # -----------------------------------------------------

    detail_y = info_y - 35
    details = [

        (
            "Student Name",
            student.get("name") or "-"        ),

        (
            "Father Name",
            student.get("father_name")
            or student.get("parent_name")
            or "-"
        ),

        (
            "Class",
            student.get("class_name") or "-"
        ),

        (
            "Section",
            student.get("section") or "-"
        ),

        (
            "Admission No.",
            student.get("admission_no") or "-"
        ),

        (
            "Date of Birth",
            student.get("date_of_birth") or "-"
        )
    ]

    pdf.setFont(
        "Helvetica",
        9
    )

    col1_x = left
    col2_x = left + 255

    for index, item in enumerate(details):

        col = index % 2
        row = index // 2

        x = (
            col1_x
            if col == 0
            else col2_x
        )

        y = detail_y - (row * 20)

        label, value = item

        pdf.setFont(
            "Helvetica-Bold",
            9
        )

        pdf.drawString(
            x,
            y,
            f"{label}:"
        )

        pdf.setFont(
            "Helvetica",
            9
        )

        pdf.drawString(
            x + 78,
            y,
            str(value)
        )

    # -----------------------------------------------------
    # Student photo
    # -----------------------------------------------------

    photo_path = student.get("photo_path")

    if photo_path:
        try:
            photo_bytes = download_storage_file(photo_path)

            if photo_bytes:
                from PIL import ImageOps

                image = Image.open(
                    io.BytesIO(photo_bytes)
                ).convert("RGB")

                image = ImageOps.fit(
                    image,
                    (
                        max(1, int(photo_w * 3)),
                        max(1, int(photo_h * 3))
                    ),
                    method=Image.Resampling.LANCZOS
                )

                img_buffer = io.BytesIO()
                image.save(
                    img_buffer,
                    format="PNG"
                )
                img_buffer.seek(0)

                pdf.drawImage(
                    ImageReader(img_buffer),
                    photo_x,
                    photo_y,
                    width=photo_w,
                    height=photo_h,
                    preserveAspectRatio=False,
                    mask="auto"
                )

                pdf.setStrokeColorRGB(
                    0.45, 0.45, 0.45
                )
                pdf.rect(
                    photo_x,
                    photo_y,
                    photo_w,
                    photo_h,
                    stroke=1,
                    fill=0
                )

        except Exception:
            pass

    # -----------------------------------------------------
    # Marks table
    # -----------------------------------------------------

    table_top = table_y

    # Keep every marks-related column comfortably visible.
    subject_col = table_width * 0.38
    max_col = table_width * 0.15
    marks_col = table_width * 0.17
    result_col = table_width * 0.15
    grade_col = table_width * 0.15

    headers = [
        "Subject",
        "Max Marks",
        "Marks Obtained",
        "Result",
        "Grade"
    ]

    x_positions = [
        table_x,
        table_x + subject_col,
        table_x + subject_col + max_col,
        table_x + subject_col + max_col + marks_col,
        table_x + subject_col + max_col + marks_col + result_col
    ]

    subject_count = max(1, len(marks_rows))

    # A4-safe dynamic row height. Do not make rows so small that
    # marks/result/grade become unreadable.
    available_height = max(
        300,
        table_top - (remarks_y + 95)
    )

    row_height = min(
        20,
        max(
            13,
            available_height / (subject_count + 1)
        )
    )

    header_font = 8 if row_height < 16 else 8.5
    body_font = 7.5 if row_height < 16 else 8.5

    pdf.setFont(
        "Helvetica-Bold",
        header_font
    )

    pdf.rect(
        table_x,
        table_top - row_height,
        table_width,
        row_height
    )

    for i in range(1, 5):
        pdf.line(
            x_positions[i],
            table_top,
            x_positions[i],
            table_top - row_height
        )

    # Header alignment
    header_centers = [
        table_x + subject_col / 2,
        x_positions[1] + max_col / 2,
        x_positions[2] + marks_col / 2,
        x_positions[3] + result_col / 2,
        x_positions[4] + grade_col / 2
    ]

    for i, header in enumerate(headers):
        if i == 0:
            pdf.drawString(
                table_x + 4,
                table_top - row_height + max(3, row_height / 2 - 3),
                header
            )
        else:
            pdf.drawCentredString(
                header_centers[i],
                table_top - row_height + max(3, row_height / 2 - 3),
                header
            )

    y = table_top - row_height

    total_marks = 0
    total_max = 0

    pdf.setFont(
        "Helvetica",
        body_font
    )

    for row in marks_rows:

        y -= row_height

        subject_name = (
            row.get("subject_name")
            or row.get("name")
            or "Subject"
        )

        mark_value = row.get("marks")
        max_value = row.get("max_marks")

        try:
            mark_number = float(mark_value)
            mark_display = format_mark(mark_number)
        except Exception:
            mark_number = 0
            mark_display = "-"

        try:
            max_number = float(max_value)
        except Exception:
            max_number = 100

        total_marks += mark_number
        total_max += max_number

        passing = row.get("passing_marks")

        try:
            passing_number = float(passing)
        except Exception:
            passing_number = 0

        if mark_value is None:
            result = "-"
            grade = "-"
        else:
            result = (
                "PASS"
                if mark_number >= passing_number
                else "FAIL"
            )

            row_percentage = (
                (mark_number / max_number) * 100
                if max_number
                else 0
            )

            grade = grade_from_percentage(
                row_percentage
            )

        pdf.rect(
            table_x,
            y,
            table_width,
            row_height
        )

        for i in range(1, 5):
            pdf.line(
                x_positions[i],
                y,
                x_positions[i],
                y + row_height
            )

        baseline = y + max(
            3,
            (row_height - body_font) / 2
        )

        subject_text = str(subject_name)
        if len(subject_text) > 31:
            subject_text = subject_text[:30] + "…"

        # Subject
        pdf.drawString(
            table_x + 4,
            baseline,
            subject_text
        )

        # All numeric/result/grade values are centered in their columns.
        pdf.drawCentredString(
            header_centers[1],
            baseline,
            format_mark(max_number)
        )

        pdf.drawCentredString(
            header_centers[2],
            baseline,
            mark_display
        )

        pdf.drawCentredString(
            header_centers[3],
            baseline,
            result
        )

        pdf.drawCentredString(
            header_centers[4],
            baseline,
            grade
        )

    # -----------------------------------------------------
    # Total / percentage / attendance
    # -----------------------------------------------------

    percentage = (
        (total_marks / total_max) * 100
        if total_max
        else 0
    )

    summary_y = y - 22

    pdf.setFont(
        "Helvetica-Bold",
        9.5
    )

    total_x = table_x
    percentage_x = table_x + table_width * 0.43
    grade_x = table_x + table_width * 0.76

    pdf.drawString(
        total_x,
        summary_y,
        f"Total Marks: {format_mark(total_marks)} / {format_mark(total_max)}"
    )

    pdf.drawString(
        percentage_x,
        summary_y,
        f"Percentage: {percentage:.2f}%"
    )

    overall_grade = grade_from_percentage(
        percentage
    )

    pdf.drawString(
        grade_x,
        summary_y,
        f"Grade: {overall_grade}"
    )

    attendance_y = summary_y - 19

    pdf.setFont(
        "Helvetica-Bold",
        9
    )

    # Present Days is directly below the Percentage column.
    pdf.drawString(
        total_x,
        attendance_y,
        f"Total Attendance: {int(total_attendance)}"
    )

    pdf.drawString(
        percentage_x,
        attendance_y,
        f"Present Days: {int(present_days)}"
    )

    # -----------------------------------------------------
    # Remarks
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawString(
        table_x,
        remarks_y + 35,
        "Remarks:"
    )

    pdf.setFont(
        "Helvetica",
        9
    )

    draw_wrapped_text(
        pdf,
        student.get("remarks") or "",
        table_x,
        remarks_y + 20,
        table_width,
        "Helvetica",
        9,
        12
    )

    # -----------------------------------------------------
    # Signature labels ONLY
    # -----------------------------------------------------

    pdf.setFont(
        "Helvetica-Bold",
        10
    )

    pdf.drawCentredString(
        teacher_x,
        45,
        "Teacher Signature"
    )

    pdf.drawCentredString(
        principal_x,
        45,
        "Principal Signature"
    )

    pdf.save()

    buffer.seek(0)

    return buffer.getvalue()


def make_report_card_pdf(
    template_bytes,
    template_type,
    orientation,
    student,
    school_info,
    subjects,
    marks_rows,
    exam_name,
    file_type,
    total_attendance=0,
    present_days=0,
    school_logo_path=None,
    school_logo_size=52
):

    overlay_bytes = create_report_overlay(
        student=student,
        school_info=school_info,
        subjects=subjects,        marks_rows=marks_rows,
        exam_name=exam_name,
        orientation=orientation,
        total_attendance=total_attendance,
        present_days=present_days,
        school_logo_path=school_logo_path,
        school_logo_size=school_logo_size
    )
    overlay_doc = fitz.open(
        stream=overlay_bytes,
        filetype="pdf"
    )

    # -----------------------------------------------------
    # PDF template    # -----------------------------------------------------

    if file_type.lower() == "pdf":

        template_doc = fitz.open(
            stream=template_bytes,
            filetype="pdf"
        )

        if len(template_doc) == 0:

            raise Exception(
                "The PDF template has no pages."
            )

        page = template_doc[0]

        page.show_pdf_page(
            page.rect,
            overlay_doc,
            0,
            overlay=True
        )

        output = template_doc.tobytes(
            garbage=4,
            deflate=True
        )

        template_doc.close()
        overlay_doc.close()

        return output

    # -----------------------------------------------------
    # Image template
    # -----------------------------------------------------

    image = Image.open(
        io.BytesIO(template_bytes)
    ).convert("RGB")

    width, height = pdf_page_size(
        orientation
    )

    base_buffer = io.BytesIO()

    base_pdf = canvas.Canvas(
        base_buffer,
        pagesize=(width, height)
    )

    base_pdf.drawImage(
        ImageReader(image),
        0,
        0,
        width=width,
        height=height,
        preserveAspectRatio=False
    )

    base_pdf.save()

    base_buffer.seek(0)

    base_doc = fitz.open(
        stream=base_buffer.getvalue(),
        filetype="pdf"
    )

    page = base_doc[0]

    page.show_pdf_page(
        page.rect,
        overlay_doc,
        0,
        overlay=True
    )

    output = base_doc.tobytes(
        garbage=4,
        deflate=True
    )

    base_doc.close()
    overlay_doc.close()

    return output



# =========================================================
# REPORT CARD EXCEL EXPORT / IMPORT
# =========================================================

def _report_excel_safe_number(value):
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _report_excel_write_df(ws, df):
    if df is None or df.empty:
        ws.append(["No data"])
        return

    ws.append(list(df.columns))
    for row in df.itertuples(index=False, name=None):
        ws.append([
            "" if value is None or (isinstance(value, float) and pd.isna(value))
            else value
            for value in row
        ])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.fill = PatternFill("solid", fgColor="D9EAF7")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    for column in ws.columns:
        max_len = 0
        col_letter = column[0].column_letter
        for cell in column[:1500]:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(value))
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 35)


def build_report_cards_excel(school_id):
    """
    Create a self-contained Report Card Backup/Import workbook.
    Report_Card_Data is the authoritative import sheet.
    """
    school = (
        sb.table("schools")
        .select("id,name,code,address")
        .eq("id", school_id)
        .maybe_single()
        .execute()
        .data
    ) or {}

    students = (
        sb.table("students")
        .select(
            "id,school_id,name,admission_no,class_name,section,"
            "date_of_birth,parent_name"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    subjects = (
        sb.table("subjects")
        .select(
            "id,school_id,class_id,name,subject_name,code,"
            "max_marks,passing_marks,active"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    marks = (
        sb.table("marks")
        .select(
            "id,school_id,student_id,subject_id,exam_name,"
            "marks,max_marks,class_id"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    try:
        attendance = (
            sb.table("attendance")
            .select(
                "id,school_id,student_id,attendance_date,present"
            )
            .eq("school_id", school_id)
            .execute()
            .data or []
        )
    except Exception:
        attendance = []

    student_map = {str(x["id"]): x for x in students}
    subject_map = {str(x["id"]): x for x in subjects}

    attendance_summary_map = {}
    for row in attendance:
        sid = str(row.get("student_id") or "")
        total, present = attendance_summary_map.get(sid, (0, 0))
        attendance_summary_map[sid] = (
            total + 1,
            present + (1 if bool(row.get("present")) else 0)
        )

    detail_rows = []
    for mark in marks:
        student = student_map.get(str(mark.get("student_id")), {})
        subject = subject_map.get(str(mark.get("subject_id")), {})
        exam = str(mark.get("exam_name") or "").strip()
        if not exam:
            continue

        total_att, present_days = attendance_summary_map.get(
            str(mark.get("student_id")), (0, 0)
        )

        maximum = (
            mark.get("max_marks")
            if mark.get("max_marks") is not None
            else subject.get("max_marks")
        )

        detail_rows.append({
            "School ID": str(school_id),
            "School Name": school.get("name") or "",
            "Exam Name": exam,
            "Student ID": str(mark.get("student_id") or ""),
            "Student Name": student.get("name") or "",
            "Admission No.": student.get("admission_no") or "",
            "Parent Name": student.get("parent_name") or "",
            "Class": student.get("class_name") or "",
            "Section": student.get("section") or "",
            "Class ID": str(
                mark.get("class_id")
                or subject.get("class_id")
                or ""
            ),
            "Subject ID": str(mark.get("subject_id") or ""),
            "Subject Name": (
                subject.get("subject_name")
                or subject.get("name")
                or ""
            ),
            "Subject Code": subject.get("code") or "",
            "Marks Obtained": mark.get("marks"),
            "Maximum Marks": maximum,
            "Passing Marks": subject.get("passing_marks"),
            "Total Attendance": total_att,
            "Present Days": present_days,
            "Percentage": round(
                (
                    _report_excel_safe_number(mark.get("marks"))
                    / _report_excel_safe_number(maximum)
                    * 100
                ),
                2
            ) if _report_excel_safe_number(maximum) else 0,
            "Grade": grade_from_percentage(
                (
                    _report_excel_safe_number(mark.get("marks"))
                    / _report_excel_safe_number(maximum)
                    * 100
                )
                if _report_excel_safe_number(maximum)
                else 0
            ),
        })

    detail_df = pd.DataFrame(detail_rows)

    exam_rows = []
    class_rows = []
    student_exam_rows = []

    if not detail_df.empty:
        for (
            exam, student_id, student_name, admission, class_name, section
        ), group in detail_df.groupby(
            [
                "Exam Name", "Student ID", "Student Name",
                "Admission No.", "Class", "Section"
            ],
            dropna=False
        ):
            obtained = float(
                pd.to_numeric(group["Marks Obtained"], errors="coerce")
                .fillna(0).sum()
            )
            maximum = float(
                pd.to_numeric(group["Maximum Marks"], errors="coerce")
                .fillna(0).sum()
            )
            percentage = round(
                obtained / maximum * 100, 2
            ) if maximum else 0

            row = {
                "Exam Name": exam,
                "Class": class_name,
                "Section": section,
                "Student ID": student_id,
                "Student Name": student_name,
                "Admission No.": admission,
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": percentage,
                "Grade": grade_from_percentage(percentage),
                "Subjects": int(group["Subject ID"].nunique()),
            }
            exam_rows.append(row)
            student_exam_rows.append(dict(row))

        for (
            exam, class_name, section
        ), group in detail_df.groupby(
            ["Exam Name", "Class", "Section"],
            dropna=False
        ):
            obtained = float(
                pd.to_numeric(group["Marks Obtained"], errors="coerce")
                .fillna(0).sum()
            )
            maximum = float(
                pd.to_numeric(group["Maximum Marks"], errors="coerce")
                .fillna(0).sum()
            )
            student_percentages = []
            for _, sg in group.groupby("Student ID"):
                sg_obtained = float(
                    pd.to_numeric(
                        sg["Marks Obtained"], errors="coerce"
                    ).fillna(0).sum()
                )
                sg_max = float(
                    pd.to_numeric(
                        sg["Maximum Marks"], errors="coerce"
                    ).fillna(0).sum()
                )
                student_percentages.append(
                    sg_obtained / sg_max * 100 if sg_max else 0
                )

            class_rows.append({
                "Exam Name": exam,
                "Class": class_name,
                "Section": section,
                "Students": int(group["Student ID"].nunique()),
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": round(
                    obtained / maximum * 100, 2
                ) if maximum else 0,
                "Average Student %": round(
                    sum(student_percentages) / len(student_percentages), 2
                ) if student_percentages else 0,
            })

    exam_df = pd.DataFrame(exam_rows)
    class_df = pd.DataFrame(class_rows)
    students_wise_df = pd.DataFrame(student_exam_rows)

    if not exam_df.empty:
        exam_df = exam_df.sort_values(
            ["Exam Name", "Class", "Section", "Percentage", "Student Name"],
            ascending=[True, True, True, False, True]
        )
        students_wise_df = exam_df.copy()

    subject_rows = []
    if not detail_df.empty:
        for (
            exam, class_name, section, subject_id, subject_name
        ), group in detail_df.groupby(
            [
                "Exam Name", "Class", "Section",
                "Subject ID", "Subject Name"
            ],
            dropna=False
        ):
            marks_series = pd.to_numeric(
                group["Marks Obtained"], errors="coerce"
            ).fillna(0)
            max_series = pd.to_numeric(
                group["Maximum Marks"], errors="coerce"
            ).fillna(0)
            pass_series = pd.to_numeric(
                group["Passing Marks"], errors="coerce"
            ).fillna(0)

            subject_rows.append({
                "Exam Name": exam,
                "Class": class_name,
                "Section": section,
                "Subject ID": subject_id,
                "Subject Name": subject_name,
                "Students": int(group["Student ID"].nunique()),
                "Total Obtained Marks": round(float(marks_series.sum()), 2),
                "Total Marks": round(float(max_series.sum()), 2),
                "Percentage": round(
                    float(marks_series.sum())
                    / float(max_series.sum()) * 100,
                    2
                ) if float(max_series.sum()) else 0,
                "Average Marks": round(float(marks_series.mean()), 2),
                "Highest Marks": round(float(marks_series.max()), 2),
                "Lowest Marks": round(float(marks_series.min()), 2),
                "Pass Count": int((marks_series >= pass_series).sum()),
                "Fail Count": int((marks_series < pass_series).sum()),
            })

    subjects_wise_df = pd.DataFrame(subject_rows)

    total_rows = []
    if not detail_df.empty:
        for (
            student_id, student_name, admission, class_name, section
        ), group in detail_df.groupby(
            [
                "Student ID", "Student Name", "Admission No.",
                "Class", "Section"
            ],
            dropna=False
        ):
            obtained = float(
                pd.to_numeric(group["Marks Obtained"], errors="coerce")
                .fillna(0).sum()
            )
            maximum = float(
                pd.to_numeric(group["Maximum Marks"], errors="coerce")
                .fillna(0).sum()
            )
            percentage = round(
                obtained / maximum * 100, 2
            ) if maximum else 0

            total_rows.append({
                "Class": class_name,
                "Section": section,
                "Student ID": student_id,
                "Student Name": student_name,
                "Admission No.": admission,
                "Exams": int(group["Exam Name"].nunique()),
                "Subjects": int(group["Subject ID"].nunique()),
                "Total Obtained Marks": round(obtained, 2),
                "Total Marks": round(maximum, 2),
                "Percentage": percentage,
                "Grade": grade_from_percentage(percentage),
            })

    total_df = pd.DataFrame(total_rows)
    if not total_df.empty:
        total_df = total_df.sort_values(
            ["Class", "Section", "Percentage", "Student Name"],
            ascending=[True, True, False, True]
        )

    wb = Workbook()
    info_ws = wb.active
    info_ws.title = "School_Info"
    info_ws.append(["Field", "Value"])
    for key, value in [
        ["School ID", str(school_id)],
        ["School Name", school.get("name") or ""],
        ["School Code", school.get("code") or ""],
        ["School Address", school.get("address") or ""],
        [
            "Created At",
            datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat()
        ],
        [
            "Purpose",
            "Report Card export that can be uploaded later to restore marks and attendance."
        ],
        [
            "Import Source",
            "Report_Card_Data"
        ],
    ]:
        info_ws.append([key, value])
    for cell in info_ws[1]:
        cell.font = Font(bold=True)

    _report_excel_write_df(
        wb.create_sheet("Report_Card_Data"),
        detail_df
    )
    _report_excel_write_df(
        wb.create_sheet("Exam_Wise"),
        exam_df
    )
    _report_excel_write_df(
        wb.create_sheet("Class_Wise"),
        class_df
    )
    _report_excel_write_df(
        wb.create_sheet("Students_Wise"),
        students_wise_df
    )
    _report_excel_write_df(
        wb.create_sheet("Subjects_Wise"),
        subjects_wise_df
    )
    _report_excel_write_df(
        wb.create_sheet("Total_All"),
        total_df
    )

    attendance_df = pd.DataFrame([
        {
            "School ID": str(school_id),
            "Student ID": str(x.get("student_id") or ""),
            "Student Name": student_map.get(
                str(x.get("student_id")), {}
            ).get("name") or "",
            "Class": student_map.get(
                str(x.get("student_id")), {}
            ).get("class_name") or "",
            "Section": student_map.get(
                str(x.get("student_id")), {}
            ).get("section") or "",
            "Attendance Date": x.get("attendance_date"),
            "Present": bool(x.get("present")),
        }
        for x in attendance
    ])
    _report_excel_write_df(
        wb.create_sheet("Attendance"),
        attendance_df
    )

    students_df = pd.DataFrame([
        {
            "Student ID": str(x.get("id") or ""),
            "Name": x.get("name") or "",
            "Admission No.": x.get("admission_no") or "",
            "Class": x.get("class_name") or "",
            "Section": x.get("section") or "",
            "Date of Birth": x.get("date_of_birth") or "",
            "Father Name": x.get("father_name") or "",
            "Parent Name": x.get("parent_name") or "",
            "Remarks": x.get("remarks") or "",
            "Active": x.get("active"),
        }
        for x in students
    ])
    _report_excel_write_df(
        wb.create_sheet("Students"),
        students_df
    )

    subjects_df = pd.DataFrame([
        {
            "Subject ID": str(x.get("id") or ""),
            "Subject Name": x.get("subject_name") or x.get("name") or "",
            "Code": x.get("code") or "",
            "Class ID": str(x.get("class_id") or ""),
            "Maximum Marks": x.get("max_marks"),
            "Passing Marks": x.get("passing_marks"),
            "Active": x.get("active"),
        }
        for x in subjects
    ])
    _report_excel_write_df(
        wb.create_sheet("Subjects"),
        subjects_df
    )

    # Highlight class toppers in Total_All.
    if not total_df.empty:
        total_ws = wb["Total_All"]
        for (class_name, section), group in total_df.groupby(
            ["Class", "Section"], dropna=False
        ):
            highest = float(group["Percentage"].max())
            for _, student_row in group.iterrows():
                if float(student_row["Percentage"]) != highest:
                    continue
                for excel_row in range(2, total_ws.max_row + 1):
                    if (
                        str(total_ws.cell(excel_row, 1).value)
                        == str(class_name)
                        and str(total_ws.cell(excel_row, 2).value)
                        == str(section)
                        and str(total_ws.cell(excel_row, 3).value)
                        == str(student_row["Student ID"])
                    ):
                        for cell in total_ws[excel_row]:
                            cell.fill = PatternFill(
                                "solid",
                                fgColor="90EE90"
                            )
                            cell.font = Font(bold=True)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()


def restore_report_cards_from_excel(uploaded_file, school_id):
    """
    Restore a Report Card export. It updates/inserts marks and, when present,
    attendance. It never deletes existing records and never creates students
    or subjects automatically.
    """
    workbook = pd.read_excel(
        uploaded_file,
        sheet_name=None,
        engine="openpyxl"
    )

    info = workbook.get("School_Info")
    if info is None or info.empty:
        raise ValueError(
            "This is not a valid Report Card Excel file. "
            "The School_Info sheet is missing."
        )

    info_map = {}
    for _, row in info.iterrows():
        if len(row) >= 2:
            info_map[str(row.iloc[0]).strip()] = row.iloc[1]

    backup_school_id = str(
        info_map.get("School ID") or ""
    ).strip()

    if backup_school_id and backup_school_id != str(school_id):
        raise ValueError(
            "This Excel belongs to another school. "
            "Import was stopped for safety."
        )

    data = workbook.get("Report_Card_Data")
    if data is None or data.empty:
        raise ValueError(
            "Report_Card_Data sheet is missing or empty."
        )

    normalized = {
        str(c).strip().lower(): c
        for c in data.columns
    }

    required = [
        "student id",
        "subject id",
        "exam name",
        "marks obtained"
    ]
    missing = [
        x for x in required
        if x not in normalized
    ]
    if missing:
        raise ValueError(
            "Report_Card_Data is missing: "
            + ", ".join(missing)
        )

    students = (
        sb.table("students")
        .select("id,school_id")
        .eq("school_id", school_id)
        .execute()
        .data or []
    )
    subjects = (
        sb.table("subjects")
        .select("id,school_id,class_id,max_marks")
        .eq("school_id", school_id)
        .execute()
        .data or []
    )
    existing_marks = (
        sb.table("marks")
        .select(
            "id,student_id,subject_id,exam_name,"
            "marks,max_marks,class_id"
        )
        .eq("school_id", school_id)
        .execute()
        .data or []
    )

    valid_students = {
        str(x["id"]) for x in students
    }
    valid_subjects = {
        str(x["id"]): x for x in subjects
    }
    existing_map = {
        (
            str(x.get("student_id")),
            str(x.get("subject_id")),
            str(x.get("exam_name") or "").strip()
        ): x
        for x in existing_marks
    }

    marks_inserted = 0
    marks_updated = 0
    skipped = []

    class_id_col = normalized.get("class id")
    max_col = normalized.get("maximum marks")

    for _, row in data.iterrows():
        student_id = str(
            row.get(normalized["student id"]) or ""
        ).strip()
        subject_id = str(
            row.get(normalized["subject id"]) or ""
        ).strip()
        exam_name = str(
            row.get(normalized["exam name"]) or ""
        ).strip()
        raw_marks = row.get(
            normalized["marks obtained"]
        )

        if not student_id or not subject_id or not exam_name:
            continue

        if student_id not in valid_students:
            skipped.append(
                f"Unknown Student ID: {student_id}"
            )
            continue

        if subject_id not in valid_subjects:
            skipped.append(
                f"Unknown Subject ID: {subject_id}"
            )
            continue

        if (
            raw_marks is None
            or pd.isna(raw_marks)
            or str(raw_marks).strip() == ""
        ):
            continue

        try:
            mark_value = round(float(raw_marks), 2)
        except Exception:
            skipped.append(
                f"Invalid marks: {student_id}/{subject_id}/{exam_name}"
            )
            continue

        subject_info = valid_subjects[subject_id]
        max_marks = subject_info.get("max_marks")

        if max_col:
            try:
                if not pd.isna(row.get(max_col)):
                    max_marks = float(row.get(max_col))
            except Exception:
                pass

        if max_marks is not None:
            try:
                if mark_value > float(max_marks):
                    skipped.append(
                        f"Marks exceed maximum: "
                        f"{student_id}/{subject_id}/{exam_name}"
                    )
                    continue
            except Exception:
                pass

        if mark_value < 0:
            skipped.append(
                f"Negative marks: {student_id}/{subject_id}/{exam_name}"
            )
            continue

        class_id = None
        if class_id_col:
            raw_class_id = row.get(class_id_col)
            if (
                raw_class_id is not None
                and not pd.isna(raw_class_id)
            ):
                class_id = str(raw_class_id).strip() or None

        if not class_id:
            class_id = str(
                subject_info.get("class_id") or ""
            ).strip() or None

        key = (
            student_id,
            subject_id,
            exam_name
        )
        old = existing_map.get(key)

        if old:
            sb.table("marks").update({
                "marks": mark_value,
                "max_marks": max_marks,
                "class_id": class_id or old.get("class_id")
            }).eq(
                "id",
                old["id"]
            ).execute()
            marks_updated += 1
        else:
            sb.table("marks").insert({
                "school_id": school_id,
                "student_id": student_id,
                "subject_id": subject_id,
                "exam_name": exam_name,
                "marks": mark_value,
                "max_marks": max_marks,
                "class_id": class_id
            }).execute()
            marks_inserted += 1

    attendance_inserted = 0
    attendance_updated = 0

    attendance_df = workbook.get("Attendance")
    if attendance_df is not None and not attendance_df.empty:
        att_norm = {
            str(c).strip().lower(): c
            for c in attendance_df.columns
        }
        if (
            "student id" in att_norm
            and "attendance date" in att_norm
            and "present" in att_norm
        ):
            try:
                existing_attendance = (
                    sb.table("attendance")
                    .select(
                        "id,student_id,attendance_date,present"
                    )
                    .eq("school_id", school_id)
                    .execute()
                    .data or []
                )
            except Exception:
                existing_attendance = []

            attendance_map = {
                (
                    str(x.get("student_id")),
                    str(x.get("attendance_date"))
                ): x
                for x in existing_attendance
            }

            for _, row in attendance_df.iterrows():
                sid = str(
                    row.get(att_norm["student id"]) or ""
                ).strip()
                raw_date = row.get(
                    att_norm["attendance date"]
                )

                if not sid or sid not in valid_students:
                    continue
                if raw_date is None or pd.isna(raw_date):
                    continue

                try:
                    date_value = pd.to_datetime(
                        raw_date
                    ).date().isoformat()
                except Exception:
                    date_value = str(raw_date).split(" ")[0]

                raw_present = row.get(
                    att_norm["present"]
                )
                present_text = str(
                    raw_present
                ).strip().lower()
                present = (
                    raw_present is True
                    or present_text in {
                        "true", "1", "yes", "present"
                    }
                )

                key = (sid, date_value)
                old = attendance_map.get(key)

                if old:
                    sb.table("attendance").update({
                        "present": present
                    }).eq(
                        "id",
                        old["id"]
                    ).execute()
                    attendance_updated += 1
                else:
                    sb.table("attendance").insert({
                        "school_id": school_id,
                        "student_id": sid,
                        "attendance_date": date_value,
                        "present": present
                    }).execute()
                    attendance_inserted += 1

    return {
        "marks_inserted": marks_inserted,
        "marks_updated": marks_updated,
        "attendance_inserted": attendance_inserted,
        "attendance_updated": attendance_updated,
        "skipped": skipped,
    }


# =========================================================
# REPORT CARD GENERATOR
# =========================================================

def report_cards():

    st.header("📄 Report Card Generator")

    role = st.session_state.profile.get("role")

    if role not in [
        "SuperAdmin",
        "Admin",
        "Admin+Teacher",
        "Teacher"
    ]:

        st.error(
            "You do not have permission to generate report cards."
        )

        return

    school_id = get_selected_school(
        "report_school"
    )

    if not school_id:
        return

    # -----------------------------------------------------
    # REPORT CARD EXCEL EXPORT / IMPORT
    # -----------------------------------------------------
    st.subheader("📦 Report Card Excel — Export & Import")
    st.caption(
        "Download a complete Report Card Excel and upload the same file later "
        "to restore marks and attendance. The raw Report_Card_Data sheet is "
        "used for safe re-import."
    )

    try:
        report_excel_bytes = build_report_cards_excel(school_id)
        report_school_name = (
            str(school_info.get("name") if "school_info" in locals() else "School")
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )
        report_excel_stamp = datetime.datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )
        report_excel_name = (
            f"{report_school_name}_Report_Cards_Backup_"
            f"{report_excel_stamp}.xlsx"
        )

        st.download_button(
            "⬇️ Download Report Cards Excel",
            data=report_excel_bytes,
            file_name=report_excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"download_report_cards_excel_{school_id}"
        )
        # Google Drive backup: upload the EXACT same Excel bytes.
        # Every backup is kept permanently; nothing is automatically deleted.
        if st.secrets.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
            if st.button(
                "☁️ Backup this exact Excel to Google Drive",
                use_container_width=True,
                key=f"backup_report_cards_google_{school_id}"
            ):
                try:
                    drive_file = backup_report_cards_excel_to_google(
                        school_id,
                        report_excel_name,
                        report_excel_bytes
                    )
                    view_url = (
                        drive_file.get("webViewLink")
                        or f"https://drive.google.com/file/d/{drive_file.get('id')}/view"
                    )
                    st.success(
                        f"✅ Exact Report Card Excel backed up permanently: "
                        f"{drive_file.get('name', report_excel_name)}"
                    )
                    st.markdown(f"[👁️ View this backup in Google Drive]({view_url})")
                except Exception as e:
                    st.error("Google Drive Report Card backup failed.")
                    st.code(str(e))
        else:
            st.info(
                "Google Drive backup is ready. Add GOOGLE_SERVICE_ACCOUNT_JSON "
                "to Streamlit Secrets to enable it."
            )

        st.success(
            "✅ Excel includes Exam_Wise, Class_Wise, Students_Wise, "
            "Subjects_Wise, Total_All, Attendance and the full "
            "Report_Card_Data import sheet."
        )
    except Exception as e:
        st.error("Could not create the Report Cards Excel.")
        st.code(str(e))

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        uploaded_report_excel = st.file_uploader(
            "📤 Upload a previously downloaded Report Cards Excel",
            type=["xlsx"],
            key=f"report_cards_excel_import_{school_id}"
        )

        if uploaded_report_excel:
            try:
                import_preview = pd.read_excel(
                    uploaded_report_excel,
                    sheet_name=None,
                    engine="openpyxl"
                )
                preview_rows = []
                for sheet_name, sheet_df in import_preview.items():
                    preview_rows.append({
                        "Sheet": sheet_name,
                        "Rows": int(len(sheet_df)),
                        "Columns": int(len(sheet_df.columns))
                    })
                st.dataframe(
                    pd.DataFrame(preview_rows),
                    hide_index=True,
                    use_container_width=True
                )

                if st.button(
                    "♻️ Import Report Cards Excel",
                    type="primary",
                    use_container_width=True,
                    key=f"import_report_cards_excel_{school_id}"
                ):
                    result = restore_report_cards_from_excel(
                        uploaded_report_excel,
                        school_id
                    )
                    st.success(
                        "✅ Report Card Excel imported successfully. "
                        f"Marks: {result['marks_inserted']} inserted, "
                        f"{result['marks_updated']} updated. "
                        f"Attendance: {result['attendance_inserted']} inserted, "
                        f"{result['attendance_updated']} updated."
                    )
                    if result["skipped"]:
                        st.warning(
                            f"{len(result['skipped'])} rows were skipped. "
                            "The existing school records were not deleted."
                        )
                        for item in result["skipped"][:30]:
                            st.caption(item)
                    st.rerun()
            except Exception as e:
                st.error("This Report Cards Excel could not be read.")
                st.code(str(e))

    st.divider()

    # -----------------------------------------------------
    # MARKS BACKUP / RECOVERY / WEIGHTAGE
    # -----------------------------------------------------
    marks_backup_and_result_tools(school_id)

    st.divider()

    # -----------------------------------------------------
    # SCHOOL
    # -----------------------------------------------------

    try:

        school_info = (
            sb.table("schools")
            .select(
                "id,name,code,address"
            )
            .eq("id", school_id)
            .maybe_single()
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            "Could not load school information."
        )

        st.code(str(e))
        return

    if not school_info:
        st.error("School information not found.")
        return

    # -----------------------------------------------------
    # ACTIVE REPORT CARD TEMPLATES
    # -----------------------------------------------------

    try:

        template_data = (
            sb.table("print_templates")
            .select(
                "id,name,template_name,page_size,"
                "orientation,storage_path,file_path,"
                "file_type,config_json,active,created_at"
            )
            .eq("school_id", school_id)
            .eq("active", True)
            .order("created_at", desc=True)
            .execute()
            .data or []
        )

    except Exception as e:

        st.error(
            "Could not load report card templates."
        )

        st.code(str(e))
        return

    report_templates = []

    for template in template_data:

        config = get_template_config(template)

        template_type = config.get(
            "template_type"
        )

        if template_type == "Report Card":
            report_templates.append(template)

    if not report_templates:

        st.warning(
            "No ACTIVE Report Card template found."
        )

        st.info(
            "Go to 🖨️ Print Templates, upload a "
            "Report Card template and keep it ACTIVE."
        )

        return

    template_map = {}

    for template in report_templates:

        name = (
            template.get("template_name")
            or template.get("name")
            or "Report Card"
        )

        label = (
            f"{name} | "
            f"{template.get('orientation') or 'Portrait'}"
        )

        template_map[label] = template

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        selected_template_label = st.selectbox(
            "🖨️ Select Active Report Card Template",
            list(template_map.keys()),
            key="report_template_select"
        )

        selected_template = template_map[
            selected_template_label
        ]
    else:
        # Teachers use the school's active Report Card template automatically.
        # They do not get access to template selection or template management.
        selected_template_label = next(iter(template_map.keys()))
        selected_template = template_map[selected_template_label]

    current_logo_path = school_logo_from_template(
        selected_template
    )

    logo_size = school_logo_size_from_template(
        selected_template
    )

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        with st.expander(
            "🏫 School Logo (Left Side)",
            expanded=False
            ):
            if current_logo_path:
                st.success("A school logo is currently saved.")

                current_logo_bytes = download_storage_file(
                    current_logo_path
                )

                if current_logo_bytes:
                    st.image(
                        current_logo_bytes,
                        width=110,
                        caption="Current School Logo"
                    )

                st.caption(
                    "The logo is aligned with the School Name row."
                )

                logo_size = st.slider(
                    "Logo Size",
                    min_value=30,
                    max_value=80,
                    value=logo_size,
                    step=2,
                    help="52 is the normal/original size. Move left for smaller or right for larger."
                )

                save_key = f"save_report_school_logo_size_{selected_template['id']}"
                show_save_message(save_key)
                if st.button(
                    "💾 Save Logo Size",
                    use_container_width=True,
                    key=save_key,
                ):
                    try:
                        logo_config = get_template_config(
                            selected_template
                        )
                        logo_config["school_logo_size"] = int(logo_size)

                        (
                            sb.table("print_templates")
                            .update({
                                "config_json": json.dumps(
                                    logo_config
                                ),
                                "updated_at":
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                            })
                            .eq(
                                "id",
                                selected_template["id"]
                            )
                            .execute()
                        )

                        mark_saved(save_key)
                        st.success("Logo size saved successfully.")
                        st.rerun()

                    except Exception as e:
                        st.error("Could not save logo size.")
                        st.code(str(e))

            else:
                st.info(
                    "No school logo is currently saved."
                )

            uploaded_logo = st.file_uploader(
                "Upload School Logo",
                type=["png", "jpg", "jpeg"],
                key="report_school_logo"
            )

            replace_label = (
                "🔄 Replace School Logo"
                if current_logo_path
                else "💾 Save School Logo"
            )

            save_key = "save_report_school_logo"
            show_save_message(save_key)
            if uploaded_logo and st.button(
                replace_label,
                use_container_width=True,
                type="primary",
                key=save_key,
            ):
                try:
                    ext = uploaded_logo.name.split(".")[-1].lower()
                    logo_path = (
                        f"{school_id}/school-logo/"
                        f"{uuid.uuid4().hex}.{ext}"
                    )
                    old_logo_path = current_logo_path

                    sb.storage.from_(
                        "school-assets"
                    ).upload(
                        logo_path,
                        uploaded_logo.getvalue(),
                        file_options={
                            "content-type": uploaded_logo.type,
                            "upsert": "false"
                        }
                    )

                    logo_config = get_template_config(
                        selected_template
                    )
                    logo_config["school_logo_path"] = logo_path

                    (
                        sb.table("print_templates")
                        .update({
                            "config_json": json.dumps(
                                logo_config
                            ),
                            "updated_at":
                                datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat()
                        })
                        .eq(
                            "id",
                            selected_template["id"]
                        )
                        .execute()
                    )

                    if old_logo_path and old_logo_path != logo_path:
                        try:
                            (
                                sb.storage
                                .from_("school-assets")
                                .remove([old_logo_path])
                            )
                        except Exception:
                            pass

                    st.success(
                        "School logo replaced successfully."
                        if old_logo_path
                        else "School logo saved successfully."
                    )
                    st.rerun()

                except Exception as e:
                    st.error("Could not save/replace school logo.")
                    st.code(str(e))

            if current_logo_path and st.button(
                "🗑️ Delete School Logo",
                use_container_width=True,
                key=f"delete_report_school_logo_{selected_template['id']}"
            ):
                try:
                    try:
                        (
                            sb.storage
                            .from_("school-assets")
                            .remove([current_logo_path])
                        )
                    except Exception:
                        pass

                    logo_config = get_template_config(
                        selected_template
                    )

                    for logo_key in [
                        "school_logo_path",
                        "logo_path",
                        "school_logo",
                        "logo"
                    ]:
                        logo_config.pop(logo_key, None)

                    (
                        sb.table("print_templates")
                        .update({
                            "config_json": json.dumps(
                                logo_config
                            ),
                            "updated_at":
                                datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat()
                        })
                        .eq(
                            "id",
                            selected_template["id"]
                        )
                        .execute()
                    )

                    st.success("School logo deleted successfully.")
                    st.rerun()

                except Exception as e:
                    st.error("Could not delete school logo.")
                    st.code(str(e))

    orientation = (
        selected_template.get("orientation")
        or "Portrait"
    )

    file_type = (
        selected_template.get("file_type")
        or ""
    ).lower()

    template_path = (
        selected_template.get("file_path")
        or selected_template.get("storage_path")
    )

    if not template_path:

        st.error(
            "Selected template has no storage path."
        )

        return

    # -----------------------------------------------------
    # DOWNLOAD TEMPLATE
    # -----------------------------------------------------

    try:

        template_bytes = (
            sb.storage
            .from_("school-assets")
            .download(template_path)
        )

    except Exception as e:

        st.error(
            "Could not download the selected template."
        )

        st.code(str(e))
        return

    if role in ["SuperAdmin", "Admin", "Admin+Teacher"]:
        st.success(
            f"Active template: "
            f"{selected_template.get('template_name') or selected_template.get('name')}"
        )
        st.caption(
            "The template is used as the A4 background. "
            "Student information and marks are placed over it."
        )
    else:
        st.info(
            "Report cards use the school's active Report Card template."
        )

    st.divider()

    # -----------------------------------------------------
    # STUDENTS
    # -----------------------------------------------------

    try:

        student_data = (
            sb.table("students")
            .select(
                "id,school_id,user_id,name,"
                "admission_no,class_name,section,"
                "date_of_birth,gender,father_name,"
                "parent_name,parent_phone,remarks,"
                "photo_path,active"
            )
            .eq("school_id", school_id)
            .eq("active", True)
            .order("name")
            .execute()
            .data or []
        )

    except Exception as e:

        st.error(
            "Could not load students."
        )

        st.code(str(e))
        return

    if role == "Teacher":
        try:
            teacher_report_classes = (
                sb.table("classes")
                .select("class_name,section,academic_year")
                .eq("school_id", school_id)
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .order("class_name")
                .order("section")
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load your Class Teacher classes.")
            st.code(str(e))
            return

        assigned_pairs = {
            (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            )
            for x in teacher_report_classes
        }

        student_data = [
            student for student in student_data
            if (
                str(student.get("class_name") or "").strip().lower(),
                str(student.get("section") or "").strip().lower()
            ) in assigned_pairs
        ]

        if teacher_report_classes:
            class_labels = [
                f"{x.get('class_name') or '-'} - Section {x.get('section') or '-'}"
                for x in teacher_report_classes
            ]
            st.info(
                "🏫 **Class Teacher Report Cards:** "
                + "  |  ".join(class_labels)
            )
        else:
            st.warning(
                "You are not assigned as Class Teacher to any class."
            )
            return

    if not student_data:

        st.warning(
            "No active students found in your assigned Class Teacher class(es)."
            if role == "Teacher"
            else "No active students found."
        )

        return

    # -----------------------------------------------------
    # EXAM / ASSESSMENT
    # -----------------------------------------------------

    exam_options = get_exam_assessments(school_id)
    if not exam_options:
        st.warning("No Exam / Assessment has been created by Admin yet.")
        return

    exam_names = [
        str(x.get("name") or "").strip()
        for x in exam_options if x.get("name")
    ]
    exam_name = st.selectbox(
        "📝 Exam / Assessment",
        exam_names,
        key="report_exam"
    )

    # -----------------------------------------------------
    # STUDENT SELECTION
    # -----------------------------------------------------

    student_options = {
        "📚 ALL STUDENTS": None
    }

    for student in student_data:

        label = (
            f"{student.get('name') or 'Student'} "
            f"| Class {student.get('class_name') or '-'} "
            f"| Section {student.get('section') or '-'} "
            f"| Admission "
            f"{student.get('admission_no') or '-'}"
        )

        student_options[label] = student

    selected_student_label = st.selectbox(
        "🎓 Student",
        list(student_options.keys()),
        key="report_student"
    )

    selected_student = student_options[
        selected_student_label
    ]

    # -----------------------------------------------------
    # SUBJECTS
    # -----------------------------------------------------

    try:

        subject_data = (            sb.table("subjects")
            .select(
                "id,school_id,class_id,name,subject_name,"
                "code,max_marks,passing_marks,active"
            )
            .eq("school_id", school_id)
            .eq("active", True)
            .order("subject_name")
            .execute()
            .data or []
        )

    except Exception as e:

        st.error(
            "Could not load subjects."
        )

        st.code(str(e))
        return

    subject_by_id = {
        str(x["id"]): x
        for x in subject_data
    }

    # -----------------------------------------------------
    # LOAD MARKS FOR ONE STUDENT
    # -----------------------------------------------------

    def get_student_marks(student):

        try:

            rows = (
                sb.table("marks")
                .select(
                    "id,student_id,subject_id,"
                    "exam_name,marks,max_marks,class_id"
                )
                .eq(
                    "school_id",
                    school_id
                )
                .eq(
                    "student_id",
                    student["id"]
                )
                .eq(
                    "exam_name",
                    exam_name
                )
                .execute()
                .data or []
            )

        except Exception:

            rows = []

        marks_by_subject = {}

        for row in rows:
            subject_id = row.get("subject_id")
            if subject_id is not None:
                marks_by_subject[str(subject_id)] = row

        # Determine the student's class from the class_id used in their marks.
        marked_class_ids = {
            str(row.get("class_id"))
            for row in rows
            if row.get("class_id") is not None
        }

        result = []

        for subject in subject_data:

            subject_id = str(subject.get("id"))

            # If marks contain a class_id, show all active subjects
            # belonging to that class. Otherwise use only subjects
            # that actually have a mark for this student.
            if marked_class_ids:
                if str(subject.get("class_id")) not in marked_class_ids:
                    continue
            elif subject_id not in marks_by_subject:
                continue

            row = marks_by_subject.get(subject_id)

            if row:
                combined = dict(row)
            else:
                combined = {
                    "id": None,
                    "student_id": student["id"],
                    "subject_id": subject.get("id"),
                    "exam_name": exam_name,
                    "marks": None,
                    "max_marks": subject.get("max_marks"),
                    "class_id": subject.get("class_id")
                }

            combined["subject_name"] = (
                subject.get("subject_name")
                or subject.get("name")
                or "Subject"
            )

            combined["passing_marks"] = (
                subject.get("passing_marks")
                if subject.get("passing_marks") is not None
                else 33
            )

            if combined.get("max_marks") is None:
                combined["max_marks"] = (
                    subject.get("max_marks")
                    if subject.get("max_marks") is not None
                    else 100
                )

            result.append(combined)

        result.sort(
            key=lambda x: str(
                x.get("subject_name") or ""
            ).lower()
        )

        return result

    # -----------------------------------------------------
    # GENERATE SINGLE
    # -----------------------------------------------------

    if selected_student:

        marks_rows = get_student_marks(
            selected_student
        )

        if not marks_rows:

            st.warning(
                f"No marks found for "
                f"{selected_student.get('name')} "
                f"for {exam_name}."
            )

        else:

            st.info(
                f"Subjects found: {len(marks_rows)}"
            )

            if st.button(
                "📄 Generate Report Card",
                type="primary",
                use_container_width=True
            ):

                try:

                    pdf_bytes = make_report_card_pdf(
                        template_bytes=
                            template_bytes,

                        template_type=
                            "Report Card",

                        orientation=
                            orientation,

                        student=
                            selected_student,

                        school_info=
                            school_info,

                        subjects=
                            subject_data,

                        marks_rows=
                            marks_rows,

                        exam_name=
                            exam_name,

                        file_type=
                            file_type,

                        total_attendance=
                            attendance_summary(
                                selected_student["id"],
                                school_id
                            )[0],

                        present_days=
                            attendance_summary(
                                selected_student["id"],
                                school_id
                            )[1],

                        school_logo_path=
                            school_logo_from_template(
                                selected_template
                            ),

                        school_logo_size=
                            logo_size
                    )

                    safe_name = (
                        str(
                            selected_student.get(
                                "name"
                            )
                            or "Student"
                        )
                        .replace("/", "_")
                        .replace("\\", "_")
                        .replace(" ", "_")
                    )

                    safe_exam = (
                        str(exam_name)
                        .replace("/", "_")
                        .replace("\\", "_")
                        .replace(" ", "_")
                    )

                    file_name = (
                        f"{safe_name}_"
                        f"{safe_exam}_"
                        f"ReportCard.pdf"
                    )

                    st.success(
                        "✅ Report card generated successfully."
                    )

                    st.download_button(
                        "⬇️ Download Report Card PDF",
                        data=pdf_bytes,
                        file_name=file_name,
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

                except Exception as e:

                    st.error(
                        "Could not generate report card."
                    )

                    st.code(str(e))

    # -----------------------------------------------------
    # GENERATE ALL
    # -----------------------------------------------------

    else:

        st.info(
            f"Ready to generate report cards for "
            f"{len(student_data)} active students."
        )

        if st.button(
            "📦 Generate ALL Report Cards",
            type="primary",
            use_container_width=True
        ):

            zip_buffer = io.BytesIO()

            generated_count = 0
            skipped_count = 0

            with zipfile.ZipFile(
                zip_buffer,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zip_file:

                progress = st.progress(0)

                for index, student in enumerate(
                    student_data
                ):

                    marks_rows = get_student_marks(
                        student
                    )

                    if not marks_rows:

                        skipped_count += 1

                        progress.progress(
                            (index + 1)
                            / len(student_data)
                        )

                        continue

                    try:

                        pdf_bytes = make_report_card_pdf(
                            template_bytes=
                                template_bytes,

                            template_type=
                                "Report Card",

                            orientation=
                                orientation,

                            student=
                                student,

                            school_info=
                                school_info,

                            subjects=
                                subject_data,

                            marks_rows=
                                marks_rows,

                            exam_name=
                                exam_name,

                            file_type=
                                file_type,

                            total_attendance=
                                attendance_summary(
                                    student["id"],
                                    school_id
                                )[0],

                            present_days=
                                attendance_summary(
                                    student["id"],
                                    school_id
                                )[1],

                            school_logo_path=
                                school_logo_from_template(
                                    selected_template
                                ),

                            school_logo_size=
                                logo_size
                        )

                        safe_name = (
                            str(
                                student.get(
                                    "name"
                                )
                                or "Student"
                            )
                            .replace("/", "_")
                            .replace("\\", "_")
                            .replace(" ", "_")
                        )

                        safe_exam = (
                            str(exam_name)
                            .replace("/", "_")
                            .replace("\\", "_")
                            .replace(" ", "_")
                        )

                        pdf_name = (
                            f"{safe_name}_"
                            f"{safe_exam}_"
                            f"ReportCard.pdf"
                        )

                        zip_file.writestr(
                            pdf_name,
                            pdf_bytes
                        )

                        generated_count += 1

                    except Exception:
                        skipped_count += 1

                    progress.progress(
                        (index + 1)
                        / len(student_data)
                    )

            zip_buffer.seek(0)

            st.success(
                f"✅ Generated: {generated_count} report cards"
            )

            if skipped_count:
                st.warning(
                    f"Skipped: {skipped_count} students "
                    f"(usually because marks were not entered)."
                )

            st.download_button(
                "⬇️ Download ALL Report Cards ZIP",
                data=zip_buffer.getvalue(),
                file_name=(
                    f"{school_info.get('name', 'School')}_"
                    f"{exam_name}_ReportCards.zip"
                    .replace("/", "_")
                    .replace("\\", "_")
                ),
                mime="application/zip",
                type="primary",
                use_container_width=True
            )


# =========================================================
# REPORTS
# =========================================================


def premium_feature_enabled(school_id, admin_id, feature_key):
    # SuperAdmin has unrestricted access to every feature.
    try:
        if st.session_state.get("profile", {}).get("role") == "SuperAdmin":
            return True
    except Exception:
        pass

    if not school_id or not admin_id:
        return False
    try:
        row = (
            sb.table("premium_feature_access")
            .select("active")
            .eq("school_id", school_id)
            .eq("admin_id", admin_id)
            .eq("feature_key", feature_key)
            .maybe_single().execute().data
        )
        return bool(row and row.get("active") is True)
    except Exception:
        return False


def premium_feature_management():
    """Manage Premium access hierarchy.

    SuperAdmin -> controls Admin Premium access.
    Admin -> when its own Premium access is active, can allow the
    complete Subject-wise Premium feature for Parents and Students.
    Parents/Students never receive the general Marks Percentage Premium
    analysis (<30/<40/<50 or full percentage analysis).
    """
    role = st.session_state.profile.get("role")
    school_id = st.session_state.profile.get("school_id")

    if role == "SuperAdmin":
        st.header("💎 Premium Feature Management")
        st.caption(
            "SuperAdmin controls Premium access for Admin users. "
            "Parents/Students can never receive the general Marks Percentage Premium analysis."
        )

        try:
            schools_data = (
                sb.table("schools")
                .select("id,name,code,active")
                .order("name")
                .execute()
                .data or []
            )
            admin_data = (
                sb.table("profiles")
                .select("id,email,full_name,school_id,role,active")
                .eq("role", "Admin")
                .order("full_name")
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load premium feature settings.")
            st.code(str(e))
            return

        schools_map = {
            f"{x.get('name') or '-'} ({x.get('code') or '-'})": x
            for x in schools_data
            if x.get("active", True)
        }
        if not schools_map:
            st.warning("No active schools available.")
            return

        selected_school_label = st.selectbox(
            "🏫 School",
            list(schools_map.keys()),
            key="premium_school"
        )
        school_id = schools_map[selected_school_label]["id"]

        school_admins = [
            x for x in admin_data
            if str(x.get("school_id")) == str(school_id)
            and x.get("active", True)
        ]

        if not school_admins:
            st.info("No active Admin users are assigned to this school.")
            return

        st.subheader("💎 Admin Premium Access")
        st.caption(
            "An Admin can use the complete Premium feature only when "
            "SuperAdmin has activated it for that Admin."
        )

        for admin in school_admins:
            admin_id = admin["id"]
            try:
                existing = (
                    sb.table("premium_feature_access")
                    .select("id,active")
                    .eq("school_id", school_id)
                    .eq("admin_id", admin_id)
                    .eq("feature_key", "school_academic_status")
                    .maybe_single()
                    .execute()
                    .data
                )
            except Exception:
                existing = None

            active = bool(existing and existing.get("active") is True)
            label = admin.get("full_name") or admin.get("email") or "Admin"

            try:
                parent_permission = (
                    sb.table("premium_feature_access")
                    .select("active")
                    .eq("school_id", school_id)
                    .eq("admin_id", admin_id)
                    .eq("feature_key", "subject_wise_premium_parent_student")
                    .maybe_single()
                    .execute()
                    .data
                )
                parent_permission_active = bool(
                    parent_permission
                    and parent_permission.get("active") is True
                )
            except Exception:
                parent_permission_active = False

            with st.container(border=True):
                st.write(f"**{label}**")
                st.caption(admin.get("email") or "")

                c1, c2 = st.columns(2)
                with c1:
                    st.write(
                        "🟢 Premium Active"
                        if active
                        else "🔴 Premium Not Allowed"
                    )
                with c2:
                    st.write(
                        "👨‍👩‍👧 Subject-wise Parent/Student: "
                        + ("ALLOWED" if parent_permission_active else "NOT ALLOWED")
                    )

                if st.button(
                    "Deactivate Premium" if active else "Activate Premium",
                    key=f"premium_toggle_{school_id}_{admin_id}",
                    use_container_width=True
                ):
                    try:
                        if existing:
                            (
                                sb.table("premium_feature_access")
                                .update({"active": not active})
                                .eq("id", existing["id"])
                                .execute()
                            )
                        else:
                            (
                                sb.table("premium_feature_access")
                                .insert({
                                    "school_id": school_id,
                                    "admin_id": admin_id,
                                    "feature_key": "school_academic_status",
                                    "active": True
                                })
                                .execute()
                            )

                        # If SuperAdmin removes the Admin's Premium access,
                        # the downstream Parent/Student permission is also
                        # disabled so it cannot remain active without an
                        # active Admin Premium subscription.
                        if active:
                            (
                                sb.table("premium_feature_access")
                                .update({"active": False})
                                .eq("school_id", school_id)
                                .eq("admin_id", admin_id)
                                .eq(
                                    "feature_key",
                                    "subject_wise_premium_parent_student"
                                )
                                .execute()
                            )

                        mark_saved("premium_feature_setting")
                        st.success("✅ Saved successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error("Could not save premium feature setting.")
                        st.code(str(e))

        st.info(
            "Parents/Students can receive only the Subject-wise Premium feature "
            "after the Admin's own Premium access is active and the Admin permits it."
        )
        return

    if role == "Admin":
        if not school_id:
            st.error("Your account is not assigned to a school.")
            return

        if not premium_feature_enabled(
            school_id,
            st.session_state.user.id,
            "school_academic_status"
        ):
            st.error(
                "Your Admin account does not currently have Premium access. "
                "Only SuperAdmin can activate it."
            )
            return

        st.header("💎 Premium Features")
        st.subheader("👨‍👩‍👧 Parent / Student Access")
        st.caption(
            "Because your Admin Premium access is active, you can permit "
            "Parents and Students to use the complete Subject-wise Premium feature."
        )

        feature_key = "subject_wise_premium_parent_student"
        try:
            existing = (
                sb.table("premium_feature_access")
                .select("id,active")
                .eq("school_id", school_id)
                .eq("admin_id", st.session_state.user.id)
                .eq("feature_key", feature_key)
                .maybe_single()
                .execute()
                .data
            )
        except Exception:
            existing = None

        current_active = bool(existing and existing.get("active") is True)

        st.write(
            "### 📚 Subject-wise Premium"
        )
        st.caption(
            "Includes full Subject-wise Premium access: Topper, "
            ">70%, >80% and >90% subject-wise analysis."
        )
        st.caption(
            "Parents/Students will NOT receive the general Marks Percentage "
            "Premium analysis such as <30%, <40%, <50%, or full percentage analysis."
        )

        new_active = st.toggle(
            "Allow Parents and Students to view Subject-wise Premium",
            value=current_active,
            key=f"allow_parent_student_subjectwise_{school_id}"
        )

        if st.button(
            "💾 Save Parent/Student Premium Permission",
            type="primary",
            use_container_width=True,
            key=f"save_parent_student_premium_{school_id}"
        ):
            try:
                if existing:
                    (
                        sb.table("premium_feature_access")
                        .update({"active": bool(new_active)})
                        .eq("id", existing["id"])
                        .execute()
                    )
                else:
                    (
                        sb.table("premium_feature_access")
                        .insert({
                            "school_id": school_id,
                            "admin_id": st.session_state.user.id,
                            "feature_key": feature_key,
                            "active": bool(new_active)
                        })
                        .execute()
                    )

                mark_saved(f"save_parent_student_premium_{school_id}")
                st.success("✅ Saved successfully.")
                st.rerun()
            except Exception as e:
                st.error(
                    "Could not save Parent/Student Premium permission."
                )
                st.code(str(e))
        return

    st.error("Only SuperAdmin or Admin can manage Premium permissions.")


def subject_wise_parent_student_premium_enabled(school_id):
    """Check Parent/Student Subject-wise Premium through a secure Supabase RPC.

    Parents/Students do not have direct SELECT permission on
    premium_feature_access, so this check must not query that table from
    the Parent/Student session. The database function performs the full
    Admin Premium + downstream permission check securely.
    """
    if not school_id:
        return False

    try:
        result = (
            sb.rpc(
                "parent_student_subject_wise_premium_enabled",
                {"p_school_id": school_id}
            )
            .execute()
        )
        data = result.data
        if isinstance(data, bool):
            return data
        if isinstance(data, list) and data:
            return bool(data[0])
        if isinstance(data, dict):
            return bool(
                data.get("parent_student_subject_wise_premium_enabled")
                or data.get("enabled")
                or data.get("result")
            )
    except Exception:
        return False

    return False

def subject_wise_premium_view(school_id, student_ids, viewer_label):
    """Full Subject-wise Premium view for permitted Parent/Student accounts.

    This intentionally exposes only Subject-wise Premium:
    - Subject toppers
    - Students above 70%
    - Students above 80%
    - Students above 90%

    It never exposes the general <30/<40/<50 or full Marks Percentage Premium analysis.
    """
    st.header("💎 Subject-wise Premium")
    st.caption(
        "Full Subject-wise Premium access: Topper, >70%, >80% and >90%."
    )

    if not school_id or not student_ids:
        st.info(
            f"No linked student record is available for this {viewer_label} account."
        )
        return

    try:
        students = (
            sb.table("students")
            .select(
                "id,name,admission_no,class_name,section,school_id,active"
            )
            .eq("school_id", school_id)
            .eq("active", True)
            .execute()
            .data or []
        )
        allowed_students = [
            x for x in students
            if str(x.get("id")) in {str(v) for v in student_ids}
        ]
    except Exception as e:
        st.error("Could not load linked student records.")
        st.code(str(e))
        return

    if not allowed_students:
        st.info("No active linked student records were found.")
        return

    class_pairs = {
        (
            str(x.get("class_name") or "").strip().lower(),
            str(x.get("section") or "").strip().lower()
        )
        for x in allowed_students
    }

    try:
        classes = (
            sb.table("classes")
            .select("id,class_name,section,academic_year,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .execute()
            .data or []
        )
        class_rows = [
            x for x in classes
            if (
                str(x.get("class_name") or "").strip().lower(),
                str(x.get("section") or "").strip().lower()
            ) in class_pairs
        ]
    except Exception as e:
        st.error("Could not load class information.")
        st.code(str(e))
        return

    if not class_rows:
        st.info("No active class is available for the linked student.")
        return

    sessions = sorted({
        str(x.get("academic_year") or "").strip()
        for x in class_rows
        if str(x.get("academic_year") or "").strip()
    })
    if not sessions:
        st.warning("No Academic Session is available.")
        return

    session = st.selectbox(
        "📅 Academic Session",
        sessions,
        key=f"subject_premium_session_{viewer_label}"
    )
    session_class_rows = [
        x for x in class_rows
        if str(x.get("academic_year") or "").strip() == session
    ]
    class_ids = {str(x["id"]) for x in session_class_rows}

    exam_names = [
        str(x.get("name") or "").strip()
        for x in get_exam_assessments(school_id)
        if x.get("name")
    ]
    if not exam_names:
        st.info("No Exam / Assessment is available yet.")
        return

    exam_name = st.selectbox(
        "📝 Exam / Assessment",
        exam_names,
        key=f"subject_premium_exam_{viewer_label}"
    )

    try:
        subjects = (
            sb.table("subjects")
            .select("id,class_id,subject_name,name,max_marks,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .execute()
            .data or []
        )
        all_students = (
            sb.table("students")
            .select("id,name,admission_no,class_name,section,father_name,parent_name,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .execute()
            .data or []
        )
        marks = (
            sb.table("marks")
            .select(
                "student_id,subject_id,marks,max_marks,class_id"
            )
            .eq("school_id", school_id)
            .eq("exam_name", exam_name)
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load Subject-wise Premium data.")
        st.code(str(e))
        return

    # Subject-wise Premium is shown for the linked student's class/section(s),
    # so the feature is useful for class-level comparison without exposing
    # other classes.
    visible_students = [
        x for x in all_students
        if (
            str(x.get("class_name") or "").strip().lower(),
            str(x.get("section") or "").strip().lower()
        ) in {
            (
                str(cl.get("class_name") or "").strip().lower(),
                str(cl.get("section") or "").strip().lower()
            )
            for cl in session_class_rows
        }
    ]
    visible_subjects = [
        x for x in subjects
        if str(x.get("class_id")) in class_ids
    ]
    subject_ids = {str(x["id"]) for x in visible_subjects}
    visible_marks = [
        x for x in marks
        if str(x.get("class_id")) in class_ids
        and str(x.get("subject_id")) in subject_ids
    ]

    student_map = {str(x["id"]): x for x in visible_students}

    subject_rows = {}
    for subject in visible_subjects:
        sid = str(subject["id"])
        rows = []
        for mark in visible_marks:
            if str(mark.get("subject_id")) != sid:
                continue

            student = student_map.get(str(mark.get("student_id")))
            if not student:
                continue

            maximum = float(
                mark.get("max_marks")
                or subject.get("max_marks")
                or 100
            )
            obtained = float(mark.get("marks") or 0)
            percentage = obtained * 100 / maximum if maximum else 0

            rows.append({
                "Student Name": student.get("name") or "",
                "Admission No.": student.get("admission_no") or "",
                "Class": student.get("class_name") or "",
                "Section": student.get("section") or "",
                "Father Name": (
                    student.get("father_name")
                    or student.get("parent_name")
                    or ""
                ),
                "Marks": round(obtained, 2),
                "Maximum": round(maximum, 2),
                "Percentage": round(percentage, 2)
            })

        if rows:
            subject_rows[
                subject.get("subject_name")
                or subject.get("name")
                or "Subject"
            ] = sorted(
                rows,
                key=lambda x: (
                    float(x["Percentage"]),
                    float(x["Marks"])
                ),
                reverse=True
            )

    if not subject_rows:
        st.info("No Subject-wise marks are available for the selected exam.")
        return

    tab_topper, tab_70, tab_80, tab_90 = st.tabs(
        [
            "🏆 Top 10",
            "📈 >70%",
            "📈 >80%",
            "📈 >90%"
        ]
    )

    for tab, threshold in [
        (tab_70, 70),
        (tab_80, 80),
        (tab_90, 90)
    ]:
        with tab:
            shown = False
            for subject_name, rows in subject_rows.items():
                filtered = [
                    row for row in rows
                    if float(row["Percentage"]) > threshold
                ]
                if not filtered:
                    continue
                shown = True
                st.markdown(f"#### 📚 {subject_name}")
                st.dataframe(
                    pd.DataFrame(filtered),
                    hide_index=True,
                    use_container_width=True
                )
            if not shown:
                st.info(f"No students are above {threshold}% in the selected subjects.")

    with tab_topper:
        for subject_name, rows in subject_rows.items():
            if not rows:
                continue

            # Always start ranking at position 1. Even when there is only
            # one student, that student is Rank 1 and receives 🥇.
            # Positions 2 and 3 receive 🥈 and 🥉 respectively.
            top_rows = rows[:10]
            ranking_rows = []

            for index, row in enumerate(top_rows, start=1):
                medal = {
                    1: "\\U0001F947",
                    2: "\\U0001F948",
                    3: "\\U0001F949"
                }.get(index, "")

                ranking_rows.append({
                    "Rank": f"{medal} {index}".strip(),
                    "Student Name": row["Student Name"],
                    "Class": row["Class"],
                    "Section": row["Section"],
                    "Father Name": row["Father Name"],
                    "Marks": (
                        f'{format_mark(row["Marks"])}/{format_mark(row["Maximum"])}'
                    ),
                    "Percentage": f'{format_mark(row["Percentage"])}%'
                })

            st.markdown(f"#### 📚 {subject_name}")

            # Top 10 leaderboard with a simple Rank column.
            # No medal images or emoji processing.
            display_rows = []
            for item in ranking_rows:
                rank_number = str(item["Rank"]).split()[-1]
                display_rows.append({
                    "Rank": rank_number,
                    "Student Name": item["Student Name"],
                    "Class": item["Class"],
                    "Section": item["Section"],
                    "Father Name": item["Father Name"],
                    "Marks": item["Marks"],
                    "Percentage": item["Percentage"],
                })

            st.dataframe(
                pd.DataFrame(display_rows),
                hide_index=True,
                use_container_width=True,
            )

def school_academic_status(school_id):
    st.subheader("💎 School Academic Status")
    st.caption("Premium academic performance analysis. SuperAdmin has full access.")

    role = st.session_state.profile.get("role")

    # SuperAdmin can select any school.
    if role == "SuperAdmin":
        try:
            school_rows = (
                sb.table("schools")
                .select("id,name,code,active")
                .eq("active", True)
                .order("name")
                .execute().data or []
            )
        except Exception as e:
            st.error("Could not load schools.")
            st.code(str(e))
            return

        school_map = {
            f"{x.get('name') or '-'} ({x.get('code') or '-'})": x["id"]
            for x in school_rows
        }
        if not school_map:
            st.warning("No active schools are available.")
            return

        selected_school_label = st.selectbox(
            "🏫 School", list(school_map.keys()), key="academic_status_school"
        )
        school_id = school_map[selected_school_label]

    try:
        class_data = (
            sb.table("classes")
            .select("id,class_name,section,academic_year,active")
            .eq("school_id", school_id).eq("active", True)
            .order("class_name").order("section").execute().data or []
        )
    except Exception as e:
        st.error("Could not load classes.")
        st.code(str(e))
        return

    if not class_data:
        st.info("No active classes are available.")
        return

    sessions = sorted({
        str(x.get("academic_year") or "").strip()
        for x in class_data if str(x.get("academic_year") or "").strip()
    })
    if not sessions:
        st.warning("No Academic Session is available in the active classes.")
        return

    session = st.selectbox("📅 Session", sessions, key="academic_status_session")
    session_classes = [
        x for x in class_data
        if str(x.get("academic_year") or "").strip() == session
    ]

    # Class selection can be mixed.
    mix_classes = st.checkbox(
        "☑️ Mix Classes",
        value=False,
        key="academic_status_mix_classes",
        help="Select multiple classes/sections and combine their students and marks."
    )

    class_options = [
        f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}"
        for x in session_classes
    ]
    class_lookup = {
        f"{x.get('class_name') or '-'} | Section: {x.get('section') or '-'}": x
        for x in session_classes
    }

    if mix_classes:
        selected_classes = st.multiselect(
            "🏫 Select Classes to Mix",
            class_options,
            default=class_options,
            key="academic_status_mix_class_selection"
        )
        selected_class_ids = {
            str(class_lookup[x]["id"]) for x in selected_classes
        }
    else:
        selected_class = st.selectbox(
            "🏫 Class", ["All Classes"] + class_options,
            key="academic_status_class"
        )
        if selected_class == "All Classes":
            selected_class_ids = {str(x["id"]) for x in session_classes}
        else:
            selected_class_ids = {str(class_lookup[selected_class]["id"])}

    if not selected_class_ids:
        st.warning("Select at least one class.")
        return

    exam_names = [
        str(x.get("name") or "").strip()
        for x in get_exam_assessments(school_id) if x.get("name")
    ]
    if not exam_names:
        st.warning("No Exam / Assessment has been created by Admin yet.")
        return

    exam_name = st.selectbox(
        "📝 Exam / Assessment", exam_names, key="academic_status_exam"
    )

    def make_excel_bytes(sheets):
        wb = Workbook()
        first = True

        for sheet_name, dataframe, fills in sheets:
            if first:
                ws = wb.active
                ws.title = sheet_name[:31]
                first = False
            else:
                ws = wb.create_sheet(sheet_name[:31])

            for col_idx, col_name in enumerate(dataframe.columns, 1):
                cell = ws.cell(1, col_idx, str(col_name))
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")

            for row_idx, row in enumerate(
                dataframe.itertuples(index=False, name=None), 2
            ):
                for col_idx, value in enumerate(row, 1):
                    cell = ws.cell(row_idx, col_idx, value)
                    cell.alignment = Alignment(vertical="center")

                fill_value = fills.get(row_idx - 2)
                if fill_value:
                    fill = PatternFill(
                        fill_type="solid",
                        fgColor=fill_value.replace("#", "")
                    )
                    for col_idx in range(1, len(dataframe.columns) + 1):
                        ws.cell(row_idx, col_idx).fill = fill

            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions

            for col_cells in ws.columns:
                max_len = 0
                letter = col_cells[0].column_letter
                for cell in col_cells:
                    max_len = max(max_len, len(str(cell.value or "")))
                ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 28)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    tab_marks, tab_subject = st.tabs(
        ["📊 Marks Percentage", "📚 Subject Wise"]
    )

    with tab_marks:
        st.markdown("### Marks Percentage")

        c1, c2 = st.columns(2)
        with c1:
            direction = st.radio(
                "Students to show",
                ["Below selected percentage", "Above selected percentage"],
                horizontal=True, key="academic_status_direction"
            )
        with c2:
            threshold = st.selectbox(
                "Percentage", [30, 40, 50, 70, 80, 90],
                format_func=lambda x: f"{x}%",
                key="academic_status_threshold"
            )

        try:
            subjects_data = (
                sb.table("subjects")
                .select("id,class_id,subject_name,name,max_marks,active")
                .eq("school_id", school_id).eq("active", True)
                .execute().data or []
            )
            students_data = (
                sb.table("students")
                .select("id,name,admission_no,class_name,section,active")
                .eq("school_id", school_id).eq("active", True)
                .order("name").execute().data or []
            )
            marks_data = (
                sb.table("marks")
                .select("student_id,subject_id,marks,max_marks,class_id")
                .eq("school_id", school_id).eq("exam_name", exam_name)
                .execute().data or []
            )
        except Exception as e:
            st.error("Could not load academic status data.")
            st.code(str(e))
            return

        students_data = [
            s for s in students_data
            if any(
                str(s.get("class_name") or "").strip().lower()
                == str(cl.get("class_name") or "").strip().lower()
                and str(s.get("section") or "").strip().lower()
                == str(cl.get("section") or "").strip().lower()
                for cl in session_classes
                if str(cl["id"]) in selected_class_ids
            )
        ]

        subjects_data = [
            x for x in subjects_data
            if str(x.get("class_id")) in selected_class_ids
        ]
        subject_ids = {str(x["id"]) for x in subjects_data}
        marks_data = [
            x for x in marks_data
            if str(x.get("class_id")) in selected_class_ids
            and str(x.get("subject_id")) in subject_ids
        ]

        marks_by_student = {}
        for m in marks_data:
            marks_by_student.setdefault(str(m["student_id"]), []).append(m)

        rows = []
        for s in students_data:
            records = marks_by_student.get(str(s["id"]), [])
            total = sum(float(x.get("marks") or 0) for x in records)
            maximum = sum(float(x.get("max_marks") or 0) for x in records)
            pct = total * 100 / maximum if maximum else 0
            match = (
                pct < threshold
                if direction == "Below selected percentage"
                else pct > threshold
            )
            if match:
                rows.append({
                    "Student Name": s.get("name") or "",
                    "Admission No.": s.get("admission_no") or "",
                    "Class": s.get("class_name") or "",
                    "Section": s.get("section") or "",
                    "Total Marks": round(total, 2),
                    "Maximum Marks": round(maximum, 2),
                    "Percentage": round(pct, 2)
                })

        if rows:
            df = pd.DataFrame(rows).sort_values(
                "Percentage",
                ascending=(direction == "Below selected percentage")
            ).reset_index(drop=True)

            bg = "#FCE4EC" if direction == "Below selected percentage" else "#E8F5E9"
            st.dataframe(
                df.style.map(lambda _: f"background-color: {bg}"),
                hide_index=True, use_container_width=True
            )

            excel_bytes = make_excel_bytes([
                ("Marks Percentage", df, {
                    i: bg for i in range(len(df))
                })
            ])

            st.download_button(
                "⬇️ Download Coloured Excel",
                data=excel_bytes,
                file_name=(
                    f"School_Academic_Status_{session}_{exam_name}.xlsx"
                    .replace("/", "_").replace(chr(92), "_")
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

            st.download_button(
                "⬇️ Download CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"School_Academic_Status_{session}_{exam_name}.csv".replace("/", "_"),
                mime="text/csv", use_container_width=True
            )
        else:
            st.info("No students match the selected percentage condition.")

    with tab_subject:
        st.markdown("### Subject Wise Top Students")

        top_n = st.selectbox(
            "🏆 Show Top", [10, 20, 30, 50, 100],
            key="academic_status_top_n"
        )

        try:
            subjects_data = (
                sb.table("subjects")
                .select("id,class_id,subject_name,name,max_marks,active")
                .eq("school_id", school_id).eq("active", True)
                .order("subject_name").execute().data or []
            )
            students_data = (
                sb.table("students")
                .select("id,name,admission_no,class_name,section,active")
                .eq("school_id", school_id).eq("active", True)
                .execute().data or []
            )
            marks_data = (
                sb.table("marks")
                .select("student_id,subject_id,marks,max_marks,class_id")
                .eq("school_id", school_id).eq("exam_name", exam_name)
                .execute().data or []
            )
        except Exception as e:
            st.error("Could not load subject-wise data.")
            st.code(str(e))
            return

        students_data = [
            s for s in students_data
            if any(
                str(s.get("class_name") or "").strip().lower()
                == str(cl.get("class_name") or "").strip().lower()
                and str(s.get("section") or "").strip().lower()
                == str(cl.get("section") or "").strip().lower()
                for cl in session_classes
                if str(cl["id"]) in selected_class_ids
            )
        ]

        subjects_data = [
            x for x in subjects_data
            if str(x.get("class_id")) in selected_class_ids
        ]
        subject_ids = {str(x["id"]) for x in subjects_data}
        marks_data = [
            x for x in marks_data
            if str(x.get("class_id")) in selected_class_ids
            and str(x.get("subject_id")) in subject_ids
        ]

        student_map = {str(x["id"]): x for x in students_data}

        subject_palette = [
            "#E3F2FD", "#E8F5E9", "#FFF3E0", "#F3E5F5", "#FFFDE7",
            "#E0F7FA", "#FBE9E7", "#E8EAF6", "#F1F8E9", "#FCE4EC"
        ]

        subject_groups = {}
        for subject in subjects_data:
            sid = str(subject["id"])
            rows = []
            for m in marks_data:
                if str(m.get("subject_id")) != sid:
                    continue
                student = student_map.get(str(m.get("student_id")))
                if not student:
                    continue
                rows.append({
                    "Student Name": student.get("name") or "",
                    "Admission No.": student.get("admission_no") or "",
                    "Class": student.get("class_name") or "",
                    "Section": student.get("section") or "",
                    "Marks": float(m.get("marks") or 0),
                    "Maximum": float(
                        m.get("max_marks") or subject.get("max_marks") or 100
                    )
                })
            rows.sort(key=lambda x: x["Marks"], reverse=True)
            subject_groups[
                subject.get("subject_name") or subject.get("name") or "Subject"
            ] = rows[:top_n]

        if not any(subject_groups.values()):
            st.info(
                "No subject marks are available for the selected Session/Class/Exam."
            )
            return

        excel_sheets = []

        for idx, (subject_name, rows) in enumerate(subject_groups.items()):
            if not rows:
                continue

            st.markdown(f"#### 📚 {subject_name}")
            df = pd.DataFrame(rows)
            bg = subject_palette[idx % len(subject_palette)]

            st.dataframe(
                df.style.map(lambda _: f"background-color: {bg}"),
                hide_index=True, use_container_width=True
            )

            excel_sheets.append((
                subject_name,
                df,
                {i: bg for i in range(len(df))}
            ))

        if excel_sheets:
            excel_bytes = make_excel_bytes(excel_sheets)
            st.download_button(
                "⬇️ Download Coloured Excel",
                data=excel_bytes,
                file_name=(
                    f"School_Academic_Status_SubjectWise_{session}_{exam_name}.xlsx"
                    .replace("/", "_").replace(chr(92), "_")
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        return

def reports():
    st.header("📊 Reports")

    role = st.session_state.profile.get("role")
    if role not in ["SuperAdmin", "Admin", "Admin+Teacher", "Teacher"]:
        st.error("You do not have permission to view reports.")
        return

    school_id = get_selected_school("reports_school")
    if not school_id:
        return

    report_options = [
        "Student Records (Excel)",
        "Student Performance",
        "Class Summary",
        "Subject Summary",
        "Attendance Summary"
    ]
    if role in ["Admin", "Admin+Teacher"] and premium_feature_enabled(
        school_id,
        st.session_state.user.id,
        "school_academic_status"
    ):
        report_options.append("💎 School Academic Status")

    report_type = st.selectbox(
        "📊 Report Type",
        report_options,
        key="reports_type"
    )

    if report_type == "💎 School Academic Status":
        school_academic_status(school_id)
        return

    # -----------------------------------------------------
    # STUDENT RECORDS EXCEL
    # -----------------------------------------------------
    if report_type == "Student Records (Excel)":
        st.subheader("📥 Student Records Excel")
        st.caption(
            "Choose exactly which student information you want in Excel. "
            "Teacher access is limited to their Class Teacher class(es)."
        )

        try:
            students_query = (
                sb.table("students")
                .select(
                    "id,school_id,user_id,name,admission_no,class_name,section,"
                    "date_of_birth,gender,father_name,mother_name,parent_name,parent_phone,address,"
                    "remarks,photo_path,teacher_signature_path,"
                    "principal_signature_path,active,created_at,updated_at"
                )
                .eq("school_id", school_id)
                .eq("active", True)
                .order("name")
            )
            students_data = students_query.execute().data or []
        except Exception as e:
            st.error("Could not load student records.")
            st.code(str(e))
            return

        # Class Teacher sees only students from classes assigned to them.
        if role == "Teacher":
            try:
                teacher_classes = (
                    sb.table("classes")
                    .select("class_name,section")
                    .eq("school_id", school_id)
                    .eq("class_teacher_id", st.session_state.user.id)
                    .eq("active", True)
                    .execute()
                    .data or []
                )
            except Exception as e:
                st.error("Could not load your Class Teacher classes.")
                st.code(str(e))
                return

            allowed_pairs = {
                (
                    str(x.get("class_name") or "").strip().lower(),
                    str(x.get("section") or "").strip().lower()
                )
                for x in teacher_classes
            }
            students_data = [
                s for s in students_data
                if (
                    str(s.get("class_name") or "").strip().lower(),
                    str(s.get("section") or "").strip().lower()
                ) in allowed_pairs
            ]

        # Teacher: only the Class Teacher's assigned class(es).
        # Admin: all active classes from this Admin's own school, with
        # a class dropdown. SuperAdmin keeps access to the school selected
        # above and can also use the class dropdown.
        filtered_students = students_data

        if role == "Teacher":
            teacher_class_options = sorted({
                (
                    f"{x.get('class_name') or '-'}"
                    f" | Section: {x.get('section') or '-'}"
                )
                for x in teacher_classes
            })

            if not teacher_class_options:
                st.info("No class has been assigned to you as Class Teacher.")
                return

            selected_teacher_class = st.selectbox(
                "🏫 My Class",
                teacher_class_options,
                key="reports_teacher_student_class"
            )

            selected_teacher_class_name = selected_teacher_class.split(" | Section: ", 1)[0]
            selected_teacher_section = (
                selected_teacher_class.split(" | Section: ", 1)[1]
                if " | Section: " in selected_teacher_class
                else "-"
            )

            filtered_students = [
                s for s in filtered_students
                if str(s.get("class_name") or "").strip() == selected_teacher_class_name
                and str(s.get("section") or "").strip() == selected_teacher_section
            ]

        else:
            # Admin/SuperAdmin: build the dropdown from the Classes table so
            # every active class in the school is available even if it has
            # no students yet.
            try:
                school_classes = (
                    sb.table("classes")
                    .select("id,class_name,section,academic_year,active")
                    .eq("school_id", school_id)
                    .eq("active", True)
                    .order("class_name")
                    .order("section")
                    .execute()
                    .data or []
                )
            except Exception as e:
                st.error("Could not load school classes.")
                st.code(str(e))
                return

            class_options = [
                (
                    f"{x.get('class_name') or '-'}"
                    f" | Section: {x.get('section') or '-'}"
                    f" | {x.get('academic_year') or '-'}"
                )
                for x in school_classes
            ]

            if not class_options:
                st.info("No active classes are available in this school.")
                return

            class_filter = st.selectbox(
                "🏫 Class",
                ["All Classes"] + class_options,
                key="reports_admin_student_records_class"
            )

            if class_filter != "All Classes":
                selected_class_name = class_filter.split(" | Section: ", 1)[0]
                remaining = class_filter.split(" | Section: ", 1)
                selected_section = (
                    remaining[1].split(" | ", 1)[0]
                    if len(remaining) > 1
                    else ""
                )
                filtered_students = [
                    s for s in filtered_students
                    if str(s.get("class_name") or "").strip() == selected_class_name
                    and str(s.get("section") or "").strip() == selected_section
                ]

        # Optional section filter remains available for Admin/SuperAdmin
        # after selecting a class, while Teacher access stays limited above.
        if role not in ["Teacher", "Admin+Teacher"]:
            filtered_section_options = sorted({
                str(s.get("section") or "").strip()
                for s in filtered_students
                if str(s.get("section") or "").strip()
            })
            section_filter = st.selectbox(
                "📚 Section",
                ["All Sections"] + filtered_section_options,
                key="reports_admin_student_records_section"
            )
            if section_filter != "All Sections":
                filtered_students = [
                    s for s in filtered_students
                    if str(s.get("section") or "").strip() == section_filter
                ]

        search = st.text_input(
            "🔍 Search Student",
            placeholder="Student name or admission number",
            key="reports_student_records_search"
        ).strip().lower()
        if search:
            filtered_students = [
                s for s in filtered_students
                if search in str(s.get("name") or "").lower()
                or search in str(s.get("admission_no") or "").lower()
            ]

        st.info(f"👥 {len(filtered_students)} student(s) available for export.")

        export_fields = [
            "Student Name",
            "Admission No.",
            "Class",
            "Section",
            "Date of Birth",
            "Gender",
            "Father Name",
            "Mother Name",
            "Parent Phone",
            "Address",
        ]

        if not filtered_students:
            st.warning("No student records match the selected filters.")
            return

        excel_bytes = make_student_records_excel(
            filtered_students,
            export_fields
        )
        st.download_button(
            "⬇️ Download Student Records Excel",
            data=excel_bytes,
            file_name="Student_Records.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"reports_student_records_download_{role}_{school_id}"
        )

        return

    try:
        class_data = (
            sb.table("classes")
            .select("id,class_name,section,academic_year,active")
            .eq("school_id", school_id)
            .eq("active", True)
            .order("class_name")
            .order("section")
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load classes.")
        st.code(str(e))
        return

    teacher_assignments = []
    if role == "Teacher":
        try:
            teacher_assignments = (
                sb.table("teacher_subject_assignments")
                .select("class_id,subject_id")
                .eq("school_id", school_id)
                .eq("teacher_id", st.session_state.user.id)
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load teacher assignments.")
            st.code(str(e))
            return

        assigned_class_ids = {
            str(x.get("class_id")) for x in teacher_assignments
        }
        class_data = [
            x for x in class_data
            if str(x.get("id")) in assigned_class_ids
        ]

    if not class_data:
        st.info("No classes are available for your report access.")
        return

    class_map = {
        (
            f"{x.get('class_name') or '-'}"
            f" | Section: {x.get('section') or '-'}"
            f" | {x.get('academic_year') or '-'}"
        ): x
        for x in class_data
    }

    if report_type != "Attendance Summary":
        exam_options = get_exam_assessments(school_id)
        exam_names = [
            str(x.get("name") or "").strip()
            for x in exam_options
            if x.get("name")
        ]
        if not exam_names:
            st.warning("No Exam / Assessment has been created by Admin yet.")
            return
        exam_name = st.selectbox(
            "📝 Exam / Assessment",
            exam_names,
            key="reports_exam"
        )
    else:
        exam_name = None

    # -----------------------------------------------------
    # STUDENT PERFORMANCE
    # -----------------------------------------------------
    if report_type == "Student Performance":
        selected_label = st.selectbox(
            "📚 Class",
            list(class_map.keys()),
            key="reports_student_class"
        )
        selected_class = class_map[selected_label]

        try:
            students_data = (
                sb.table("students")
                .select("id,name,admission_no,class_name,section")
                .eq("school_id", school_id)
                .eq("class_name", selected_class.get("class_name") or "")
                .eq("section", selected_class.get("section") or "")
                .eq("active", True)
                .order("name")
                .execute()
                .data or []
            )

            subjects_data = (
                sb.table("subjects")
                .select("id,subject_name,name,max_marks")
                .eq("school_id", school_id)
                .eq("class_id", selected_class["id"])
                .eq("active", True)
                .order("subject_name")
                .execute()
                .data or []
            )

            marks_data = (
                sb.table("marks")
                .select("student_id,subject_id,marks,max_marks")
                .eq("school_id", school_id)
                .eq("class_id", selected_class["id"])
                .eq("exam_name", exam_name)
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load performance data.")
            st.code(str(e))
            return

        if role == "Teacher":
            allowed = {
                str(x.get("subject_id"))
                for x in teacher_assignments
                if str(x.get("class_id")) == str(selected_class["id"])
            }
            subjects_data = [
                x for x in subjects_data if str(x.get("id")) in allowed
            ]
            marks_data = [
                x for x in marks_data if str(x.get("subject_id")) in allowed
            ]

        subject_names = {
            str(x["id"]): (
                x.get("subject_name") or x.get("name") or "Subject"
            )
            for x in subjects_data
        }
        subject_max = {
            str(x["id"]): float(x.get("max_marks") or 100)
            for x in subjects_data
        }
        marks_by_student = {}
        for m in marks_data:
            marks_by_student.setdefault(str(m["student_id"]), {})[
                str(m["subject_id"])
            ] = float(m.get("marks") or 0)

        rows = []
        for student in students_data:
            sid = str(student["id"])
            row = {
                "Student Name": student.get("name") or "",
                "Admission No.": student.get("admission_no") or ""
            }
            total = 0.0
            maximum = 0.0
            for subject_id, subject_name in subject_names.items():
                value = marks_by_student.get(sid, {}).get(subject_id)
                row[subject_name] = value if value is not None else ""
                if value is not None:
                    total += value
                    maximum += subject_max.get(subject_id, 100)
            row["Total Marks"] = round(total, 2)
            row["Maximum Marks"] = round(maximum, 2)
            row["Percentage"] = round(total * 100 / maximum, 2) if maximum else 0
            row["Grade"] = grade_from_percentage(row["Percentage"])
            rows.append(row)

        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button(
            "⬇️ Download Student Performance CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"Student_Performance_{exam_name}.csv".replace("/", "_"),
            mime="text/csv",
            use_container_width=True
        )
        return

    # -----------------------------------------------------
    # CLASS SUMMARY
    # -----------------------------------------------------
    if report_type == "Class Summary":
        try:
            students_data = (
                sb.table("students")
                .select("id,name,class_name,section")
                .eq("school_id", school_id)
                .eq("active", True)
                .execute()
                .data or []
            )
            marks_data = (
                sb.table("marks")
                .select("student_id,marks,max_marks,class_id")
                .eq("school_id", school_id)
                .eq("exam_name", exam_name)
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load class summary.")
            st.code(str(e))
            return

        allowed_class_ids = {str(x["id"]) for x in class_data}
        by_student = {}
        for m in marks_data:
            if str(m.get("class_id")) not in allowed_class_ids:
                continue
            sid = str(m["student_id"])
            total, maximum = by_student.get(sid, (0.0, 0.0))
            by_student[sid] = (
                total + float(m.get("marks") or 0),
                maximum + float(m.get("max_marks") or 0)
            )

        rows = []
        for cl in class_data:
            class_students = [
                s for s in students_data
                if str(s.get("class_name") or "").strip().lower()
                == str(cl.get("class_name") or "").strip().lower()
                and str(s.get("section") or "").strip().lower()
                == str(cl.get("section") or "").strip().lower()
            ]
            percentages = []
            for s in class_students:
                total, maximum = by_student.get(str(s["id"]), (0, 0))
                if maximum:
                    percentages.append(total * 100 / maximum)

            rows.append({
                "Class": cl.get("class_name") or "-",
                "Section": cl.get("section") or "-",
                "Students": len(class_students),
                "Students With Marks": len(percentages),
                "Average %": round(sum(percentages) / len(percentages), 2) if percentages else 0,
                "Highest %": round(max(percentages), 2) if percentages else 0,
                "Lowest %": round(min(percentages), 2) if percentages else 0
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button(
            "⬇️ Download Class Summary CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"Class_Summary_{exam_name}.csv".replace("/", "_"),
            mime="text/csv",
            use_container_width=True
        )
        return

    # -----------------------------------------------------
    # SUBJECT SUMMARY
    # -----------------------------------------------------
    if report_type == "Subject Summary":
        selected_label = st.selectbox(
            "📚 Class",
            list(class_map.keys()),
            key="reports_subject_class"
        )
        selected_class = class_map[selected_label]

        try:
            subjects_data = (
                sb.table("subjects")
                .select("id,subject_name,name,max_marks,passing_marks")
                .eq("school_id", school_id)
                .eq("class_id", selected_class["id"])
                .eq("active", True)
                .order("subject_name")
                .execute()
                .data or []
            )
            marks_data = (
                sb.table("marks")
                .select("student_id,subject_id,marks")
                .eq("school_id", school_id)
                .eq("class_id", selected_class["id"])
                .eq("exam_name", exam_name)
                .execute()
                .data or []
            )
        except Exception as e:
            st.error("Could not load subject summary.")
            st.code(str(e))
            return

        if role == "Teacher":
            allowed = {
                str(x.get("subject_id"))
                for x in teacher_assignments
                if str(x.get("class_id")) == str(selected_class["id"])
            }
            subjects_data = [
                x for x in subjects_data if str(x.get("id")) in allowed
            ]
            marks_data = [
                x for x in marks_data if str(x.get("subject_id")) in allowed
            ]

        rows = []
        for subject in subjects_data:
            sid = str(subject["id"])
            values = [
                float(m.get("marks") or 0)
                for m in marks_data
                if str(m.get("subject_id")) == sid
            ]
            passing = float(subject.get("passing_marks") or 0)
            rows.append({
                "Subject": subject.get("subject_name") or subject.get("name") or "-",
                "Students With Marks": len(values),
                "Average Marks": round(sum(values) / len(values), 2) if values else 0,
                "Highest Marks": round(max(values), 2) if values else 0,
                "Lowest Marks": round(min(values), 2) if values else 0,
                "Pass Count": sum(1 for v in values if v >= passing),
                "Maximum Marks": float(subject.get("max_marks") or 100),
                "Passing Marks": passing
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button(
            "⬇️ Download Subject Summary CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"Subject_Summary_{exam_name}.csv".replace("/", "_"),
            mime="text/csv",
            use_container_width=True
        )
        return

    # -----------------------------------------------------
    # ATTENDANCE SUMMARY
    # -----------------------------------------------------
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input(
            "From Date",
            value=datetime.date.today().replace(day=1),
            key="reports_att_from"
        )
    with c2:
        end_date = st.date_input(
            "To Date",
            value=datetime.date.today(),
            key="reports_att_to"
        )

    if start_date > end_date:
        st.error("From Date cannot be after To Date.")
        return

    selected_label = st.selectbox(
        "📚 Class",
        ["All Classes"] + list(class_map.keys()),
        key="reports_att_class"
    )

    try:
        students_query = (
            sb.table("students")
            .select("id,name,admission_no,class_name,section")
            .eq("school_id", school_id)
            .eq("active", True)
        )

        if selected_label != "All Classes":
            selected_report_class = class_map[selected_label]
            students_query = (
                students_query
                .eq("class_name", selected_report_class.get("class_name") or "")
                .eq("section", selected_report_class.get("section") or "")
            )

        students_data = (
            students_query
            .order("name")
            .execute()
            .data or []
        )
        attendance_data = (
            sb.table("attendance")
            .select("student_id,attendance_date,present")
            .eq("school_id", school_id)
            .gte("attendance_date", str(start_date))
            .lte("attendance_date", str(end_date))
            .execute()
            .data or []
        )
    except Exception as e:
        st.error("Could not load attendance report.")
        st.code(str(e))
        return

    allowed_pairs = {
        (
            str(x.get("class_name") or "").strip().lower(),
            str(x.get("section") or "").strip().lower()
        )
        for x in class_data
    }
    if role == "Teacher":
        students_data = [
            s for s in students_data
            if (
                str(s.get("class_name") or "").strip().lower(),
                str(s.get("section") or "").strip().lower()
            ) in allowed_pairs
        ]

    by_student = {}
    for a in attendance_data:
        sid = str(a["student_id"])
        total, present = by_student.get(sid, (0, 0))
        by_student[sid] = (total + 1, present + (1 if a.get("present") else 0))

    rows = []
    for s in students_data:
        total, present = by_student.get(str(s["id"]), (0, 0))
        rows.append({
            "Student Name": s.get("name") or "",
            "Admission No.": s.get("admission_no") or "",
            "Class": s.get("class_name") or "",
            "Section": s.get("section") or "",
            "Total Days": total,
            "Present Days": present,
            "Absent Days": total - present,
            "Attendance %": round(present * 100 / total, 2) if total else 0
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, use_container_width=True)
    st.download_button(
        "⬇️ Download Attendance Summary CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"Attendance_Summary_{start_date}_{end_date}.csv",
        mime="text/csv",
        use_container_width=True
    )



# =========================================================
# DASHBOARD# =========================================================

def dashboard():

    profile = st.session_state.profile
    role = profile.get("role")

    # -----------------------------------------------------
    # TEACHER CLASS CONTEXT
    # -----------------------------------------------------
    # Keep the Class Teacher's assigned class name(s) visible
    # at every Teacher working place because all Teacher modules
    # are rendered from this dashboard.
    if role == "Teacher":
        try:
            teacher_working_classes = (
                sb.table("classes")
                .select("class_name,section,academic_year")
                .eq("school_id", profile.get("school_id"))
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .order("class_name")
                .order("section")
                .execute()
                .data or []
            )
        except Exception:
            teacher_working_classes = []

        if teacher_working_classes:
            class_names = [
                (
                    f"{x.get('class_name') or '-'}"
                    f" - Section {x.get('section') or '-'}"
                )
                for x in teacher_working_classes
            ]
            st.info(
                "🏫 **My Class Teacher Class(es):** "
                + "  |  ".join(class_names)
            )
        else:
            st.warning(
                "🏫 **My Class Teacher Class(es):** "
                "No class assigned yet."
            )

    top1, top2 = st.columns([5, 1])
    with top1:

        st.caption(
            f"Role: {role} | "
            f"{profile.get('email', '')}"
        )

    with top2:

        if st.button(
            "Logout",
            use_container_width=True
        ):

            logout()

    # =====================================================
    # SUPERADMIN
    # =====================================================

    if role == "SuperAdmin":

        st.title("👑 SuperAdmin Dashboard")

        try:

            school_count = (
                sb.table("schools")
                .select("id", count="exact")
                .execute()
                .count
                or 0
            )

            user_count = (
                sb.table("profiles")
                .select("id", count="exact")
                .execute()
                .count
                or 0
            )

            student_count = (
                sb.table("students")
                .select("id", count="exact")
                .execute()
                .count
                or 0
            )

        except Exception:

            school_count = 0
            user_count = 0
            student_count = 0

        a, b, c = st.columns(3)

        a.metric("🏫 Schools", school_count)
        b.metric("👥 Users", user_count)
        c.metric("🎓 Students", student_count)

        menu = st.radio(
            "Management",
            [
                "🏫 Schools",
                "👥 Users",
                "🎓 Students",
                "📚 Classes & Subjects",
                "📝 Exam / Assessment",
                "📝 Marks",
                "📅 Attendance",
                "🖨️ Print Templates",
                "📄 Report Cards",
                "📊 Reports",
                "💎 Premium Features",
                "💎 School Academic Status"
            ],
            horizontal=True
        )

        if menu == "🏫 Schools":
            schools()

        elif menu == "👥 Users":
            users()

        elif menu == "🎓 Students":
            students()

        elif menu == "📚 Classes & Subjects":
            classes_subjects()

        elif menu == "📝 Exam / Assessment":
            exam_assessment_settings()

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "🖨️ Print Templates":
            print_templates()

        elif menu == "📄 Report Cards":
            report_cards()

        elif menu == "📊 Reports":
            reports()

        elif menu == "💎 Premium Features":
            premium_feature_management()

        elif menu == "💎 School Academic Status":
            # SuperAdmin can use every premium feature directly.
            school_academic_status(profile.get("school_id"))

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # ADMIN
    # =====================================================

    elif role in ["Admin", "Admin+Teacher"]:

        if role == "Admin+Teacher":
            teacher_mode_items = {
                "🎓 Students",
                "📝 Marks",
                "📅 Attendance",
                "📄 Report Cards",
                "📊 Reports",
            }
            current_menu = st.session_state.get("admin_dashboard_menu")
            if current_menu in teacher_mode_items:
                st.title("👨‍🏫 Teacher Dashboard")
            else:
                st.title("🛠️ Admin Dashboard")
        else:
            st.title("🛠️ Admin Dashboard")

        # Admin has full access to every Teacher module and
        # also retains all Admin-only management functions.
        admin_menu_items = [
            "👥 Users",
            "🎓 Students",
            "📚 Classes & Subjects",
            "📝 Exam / Assessment",
            "📝 Marks",
            "📅 Attendance",
            "🖨️ Print Templates",
            "📄 Report Cards",
            "📊 Reports"
        ]

        # Premium Features is visible to Admin only when SuperAdmin
        # has activated Premium access for this Admin.
        if role == "Admin" and premium_feature_enabled(
            profile.get("school_id"),
            st.session_state.user.id,
            "school_academic_status"
        ):
            admin_menu_items.append("💎 Premium Features")

        menu = st.radio(
            "Management",
            admin_menu_items,
            horizontal=True,
            key="admin_dashboard_menu"
        )

        # Admin+Teacher automatically switches visual mode according
        # to the work being performed. Admin-only modules use the
        # Admin theme; Teacher modules use the Teacher theme.
        if role == "Admin+Teacher":
            active_mode = (
                "Teacher"
                if menu in {
                    "🎓 Students",
                    "📝 Marks",
                    "📅 Attendance",
                    "📄 Report Cards",
                    "📊 Reports",
                }
                else "Admin"
            )
            if active_mode == "Teacher":
                st.caption("👨‍🏫 Teacher Mode")
            else:
                st.caption("🛠️ Admin Mode")

            apply_role_theme()

        if menu == "👥 Users":
            users()

        elif menu == "🎓 Students":
            students()

        elif menu == "📚 Classes & Subjects":
            classes_subjects()

        elif menu == "📝 Exam / Assessment":
            exam_assessment_settings()

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "🖨️ Print Templates":
            print_templates()

        elif menu == "📄 Report Cards":
            report_cards()

        elif menu == "📊 Reports":
            reports()

        elif menu == "💎 Premium Features":
            premium_feature_management()

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # TEACHER
    # =====================================================

    elif role == "Teacher":

        st.title("👨‍🏫 Teacher Dashboard")

        # Show the classes for which this teacher is the Class Teacher.
        # Class Teachers can manage students and attendance only for
        # these assigned classes. Subject-teaching assignments remain
        # separate and continue to control Marks access.
        try:
            teacher_class_rows = (
                sb.table("classes")
                .select("id,class_name,section,academic_year,active")
                .eq("school_id", profile.get("school_id"))
                .eq("class_teacher_id", st.session_state.user.id)
                .eq("active", True)
                .order("class_name")
                .order("section")
                .execute()
                .data or []
            )
        except Exception:
            teacher_class_rows = []

        if teacher_class_rows:
            st.subheader("🏫 My Class Teacher Classes")
            class_cols = st.columns(min(3, len(teacher_class_rows)))
            for i, teacher_class in enumerate(teacher_class_rows):
                with class_cols[i % len(class_cols)]:
                    st.info(
                        f"**{teacher_class.get('class_name') or '-'}**"
                        f" — Section {teacher_class.get('section') or '-'}"
                        f"\n\nAcademic Year: "
                        f"{teacher_class.get('academic_year') or '-'}"
                    )
            st.caption(
                "As Class Teacher, you can see and manage students and attendance "
                "only in your assigned class(es)."
            )
        else:
            st.warning(
                "No class has been assigned to you as Class Teacher yet."
            )

        menu = st.radio(
            "Teacher Menu",
            [
                "🎓 Students",
                "📝 Marks",
                "📅 Attendance",
                "📄 Report Cards",
                "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🎓 Students":
            students()

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "📄 Report Cards":
            report_cards()

        elif menu == "📊 Reports":
            reports()

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # STUDENT
    # =====================================================

    elif role == "Student":

        st.title("🎓 Student Dashboard")

        student = None

        try:

            student = (
                sb.table("students")
                .select(
                    "id,school_id,user_id,name,"
                    "admission_no,class_name,section,"
                    "date_of_birth,gender,father_name,"
                    "parent_name,parent_phone,photo_path,"
                    "remarks,active"
                )
                .eq(
                    "user_id",
                    st.session_state.user.id
                )
                .maybe_single()
                .execute()
                .data
            )

            if student:

                photo_path = student.get(
                    "photo_path"
                )

                if photo_path:

                    try:

                        photo_bytes = (
                            sb.storage
                            .from_("school-assets")
                            .download(photo_path)
                        )

                        st.image(
                            photo_bytes,
                            width=140
                        )

                    except Exception:
                        pass

                st.subheader(
                    student.get(
                        "name",
                        "Student"
                    )
                )

                a, b, c = st.columns(3)

                a.metric(
                    "Class",
                    student.get(
                        "class_name",
                        "-"
                    )
                )

                b.metric(
                    "Section",
                    student.get(
                        "section",
                        "-"
                    )
                )

                c.metric(
                    "Admission No.",
                    student.get(
                        "admission_no",
                        "-"
                    )
                )

                st.write(
                    "**Father Name:** "
                    f"{student.get('father_name') or student.get('parent_name') or '-'}"
                )

                if student.get("remarks"):

                    st.write(
                        "**Remarks:** "
                        f"{student.get('remarks')}"
                    )

            else:

                st.info(
                    "Your student record is not linked yet."
                )

        except Exception as e:

            st.error(
                "Could not load student information."
            )

            st.code(str(e))

        # Student can see Subject-wise Premium only when an active
        # Admin has explicitly permitted it.
        if student and subject_wise_parent_student_premium_enabled(
            student.get("school_id")
        ):
            subject_wise_premium_view(
                student.get("school_id"),
                [student.get("id")],
                "Student"
            )
        elif student:
            st.info(
                "💎 Subject-wise Premium is not enabled for Students by Admin."
            )

    # =====================================================
    # PARENT
    # =====================================================

    elif role == "Parent":

        st.title("👨‍👩‍👧 Parent Dashboard")

        # Parent receives only the Subject-wise Premium feature when an
        # Admin with active Premium access has explicitly permitted it.
        # The general <30/<40/<50 and full Marks Percentage Premium
        # analysis is never exposed to Parent.
        school_id = profile.get("school_id")

        if school_id and subject_wise_parent_student_premium_enabled(school_id):
            current_user_id = str(st.session_state.user.id)
            current_email = str(profile.get("email") or "").strip().lower()

            linked_ids = []
            try:
                # Parent ↔ Student relationships are stored separately from
                # students.user_id. A parent can therefore be linked to one
                # or multiple children without affecting Student login.
                parent_links = (
                    sb.table("parent_student_links")
                    .select("student_id")
                    .eq("parent_id", current_user_id)
                    .execute()
                    .data or []
                )
                linked_ids = [
                    row.get("student_id")
                    for row in parent_links
                    if row.get("student_id")
                ]
            except Exception:
                linked_ids = []

            if linked_ids:
                subject_wise_premium_view(
                    school_id,
                    linked_ids,
                    "Parent"
                )
            else:
                st.info(
                    "Your Parent account is not linked to a student record yet."
                )
        else:
            st.info(
                "💎 Subject-wise Premium has not been enabled for Parents by Admin."
            )

    else:

        st.error(
            f"Unknown role: {role}"
        )


# =========================================================
# START
# =========================================================

if st.session_state.logged_in:

    apply_role_theme()
    dashboard()

else:

    login()
