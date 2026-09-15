# ============================================================
# 6THSENSE SCHOOL MANAGEMENT SYSTEM
# Streamlit + Supabase
# Complete app.py
# ============================================================

import io
import os
import uuid
import urllib.request
from datetime import datetime, date

import pandas as pd
import streamlit as st

from supabase import create_client, Client

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    KeepTogether,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="6thSense School Management",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONSTANTS
# ============================================================

ROLES = [
    "Admin",
    "Teacher",
    "Student",
    "Parent",
    "Staff",
]

ACADEMIC_SESSIONS = [
    "2026-27",
    "2025-26",
    "2027-28",
    "2028-29",
]

GRADES = [
    "A+",
    "A",
    "B+",
    "B",
    "C+",
    "C",
    "D",
    "E",
    "F",
]


# ============================================================
# SUPABASE CONNECTION
# ============================================================

def get_secret(name, default=None):
    """
    Read Streamlit secrets first, then environment variables.
    """
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.getenv(name, default)


SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = get_secret(
    "SUPABASE_SERVICE_ROLE_KEY"
)


if not SUPABASE_URL or not SUPABASE_KEY:

    st.error(
        "Supabase configuration is missing."
    )

    st.info(
        "Add SUPABASE_URL and SUPABASE_KEY "
        "under Streamlit Cloud → Settings → Secrets."
    )

    st.stop()


@st.cache_resource
def create_supabase_client():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
    )


supabase: Client = create_supabase_client()


@st.cache_resource
def create_admin_client():
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None

    return create_client(
        SUPABASE_URL,
        SUPABASE_SERVICE_ROLE_KEY,
    )


supabase_admin = create_admin_client()


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_SESSION_STATE = {
    "user": None,
    "profile": None,
    "session_token": None,
    "login_message": None,
}


for key, value in DEFAULT_SESSION_STATE.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_value(value, default=""):
    if value is None:
        return default
    return value


def normalize_rpc_data(data, default=None):
    """
    Supabase RPC scalar responses can sometimes arrive in
    different shapes depending on the client/PostgREST response.
    """
    if data is None:
        return default

    if isinstance(data, list):

        if len(data) == 0:
            return default

        if len(data) == 1:
            return data[0]

    if isinstance(data, dict):

        if len(data) == 1:
            return next(iter(data.values()))

    return data


def clear_local_session():

    st.session_state.user = None
    st.session_state.profile = None
    st.session_state.session_token = None


def logout_user():

    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    clear_local_session()

    st.rerun()


def get_current_user():

    try:
        response = supabase.auth.get_user()

        if response and response.user:
            return response.user

    except Exception:
        pass

    return None


def get_profile(user_id):

    try:

        response = (
            supabase
            .table("profiles")
            .select("*")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )

        return response.data

    except Exception as e:

        st.error(
            f"Unable to load user profile: {e}"
        )

        return None


# ============================================================
# ONE ACTIVE SESSION PER USER
# ============================================================

def start_server_session():
    result = supabase.rpc(
        "start_user_session",
        {}
    ).execute()

    st.write("DEBUG — RPC DATA:", result.data)

    if not result.data:
        raise RuntimeError(
            "start_user_session returned no session token"
        )

    token = str(result.data)

    st.session_state.session_token = token

    return token


def check_server_session():

    """
    Checks the current session token against the server-side
    active_session stored for the logged-in user.
    """

    token = st.session_state.get(
        "session_token"
    )

    if not token:
        return False

    try:

        response = supabase.rpc(
            "check_user_session",
            {
                "supplied_token": token
            }
        ).execute()

        result = normalize_rpc_data(
            response.data,
            False
        )

        return bool(result)

    except Exception:

        return False


def enforce_server_session():

    """
    If another device has logged in, the previous browser
    becomes invalid on its next interaction/rerun.
    """

    if st.session_state.user is None:
        return True

    if not check_server_session():

        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        clear_local_session()

        st.warning(
            "Your session is no longer active. "
            "This usually happens because this User ID "
            "was logged in on another device."
        )

        st.stop()

    return True


# ============================================================
# AUTHENTICATION
# ============================================================

def login_user(email, password):

    try:

        response = supabase.auth.sign_in_with_password(
            {
                "email": email.strip(),
                "password": password,
            }
        )

        if not response or not response.user:

            return False, "Login failed."

        user = response.user

        profile = get_profile(
            user.id
        )

        if not profile:

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            return (
                False,
                "User profile was not found."
            )

        if not profile.get("active", True):

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            return (
                False,
                "This account is inactive. "
                "Please contact the administrator."
            )

        st.session_state.user = user
        st.session_state.profile = profile

        # ----------------------------------------------------
        # Start new server-side session.
        # This invalidates any previous device/session.
        # ----------------------------------------------------

        if not start_server_session():

            try:
                supabase.auth.sign_out()
            except Exception:
                pass

            clear_local_session()

            return (
                False,
                "Secure session could not be started."
            )

        # Refresh profile after session creation.
        refreshed_profile = get_profile(
            user.id
        )

        if refreshed_profile:
            st.session_state.profile = refreshed_profile

        return True, "Login successful."

    except Exception as e:

        return False, str(e)


# ============================================================
# REPORT CARD HELPERS
# ============================================================

def calculate_grade(percentage):

    try:
        percentage = float(percentage)
    except Exception:
        return "F"

    if percentage >= 90:
        return "A+"

    if percentage >= 80:
        return "A"

    if percentage >= 70:
        return "B+"

    if percentage >= 60:
        return "B"

    if percentage >= 50:
        return "C+"

    if percentage >= 40:
        return "C"

    if percentage >= 33:
        return "D"

    if percentage >= 25:
        return "E"

    return "F"


def get_school_settings():

    try:

        response = (
            supabase
            .table("school_settings")
            .select("*")
            .limit(1)
            .execute()
        )

        if response.data:

            return response.data[0]

    except Exception:
        pass

    return {
        "school_name": "My School",
        "school_address": "",
        "phone": "",
        "email": "",
        "academic_session": "2026-27",
        "logo_url": "",
        "principal_name": "",
        "principal_remarks": "",
    }


def download_logo(logo_url):

    if not logo_url:
        return None

    try:

        with urllib.request.urlopen(
            logo_url,
            timeout=8
        ) as response:

            return io.BytesIO(
                response.read()
            )

    except Exception:
        return None


def create_report_card(
    student,
    marks,
    school,
):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=18,
        leading=22,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=12,
    )

    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=12,
        leading=15,
        spaceBefore=8,
        spaceAfter=5,
    )

    normal_style = ParagraphStyle(
        "Normal2",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
    )

    story = []

    # --------------------------------------------------------
    # LOGO
    # --------------------------------------------------------

    logo_url = school.get(
        "logo_url",
        ""
    )

    logo_data = download_logo(
        logo_url
    )

    if logo_data:

        try:

            logo = Image(
                logo_data,
                width=25 * mm,
                height=25 * mm,
            )

            logo.hAlign = "CENTER"

            story.append(logo)
            story.append(
                Spacer(1, 3 * mm)
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # SCHOOL HEADER
    # --------------------------------------------------------

    school_name = safe_value(
        school.get("school_name"),
        "My School"
    )

    story.append(
        Paragraph(
            school_name,
            title_style
        )
    )

    address = safe_value(
        school.get("school_address")
    )

    phone = safe_value(
        school.get("phone")
    )

    email = safe_value(
        school.get("email")
    )

    contact_parts = [
        x for x in [
            address,
            phone,
            email
        ]
        if x
    ]

    if contact_parts:

        story.append(
            Paragraph(
                " | ".join(contact_parts),
                subtitle_style
            )
        )

    story.append(
        Spacer(1, 5 * mm)
    )

    story.append(
        Paragraph(
            "STUDENT REPORT CARD",
            title_style
        )
    )

    session = safe_value(
        school.get("academic_session"),
        "2026-27"
    )

    story.append(
        Paragraph(
            f"Academic Session: {session}",
            subtitle_style
        )
    )

    story.append(
        Spacer(1, 6 * mm)
    )

    # --------------------------------------------------------
    # STUDENT DETAILS
    # --------------------------------------------------------

    student_name = safe_value(
        student.get("name")
    )

    class_name = safe_value(
        student.get("class_name")
    )

    section = safe_value(
        student.get("section")
    )

    roll_no = safe_value(
        student.get("roll_no")
    )

    dob = safe_value(
        student.get("dob")
    )

    admission_no = safe_value(
        student.get("admission_no")
    )

    details = [
        [
            Paragraph(
                "<b>Student Name</b>",
                normal_style
            ),
            student_name,
            Paragraph(
                "<b>Class</b>",
                normal_style
            ),
            class_name,
        ],
        [
            Paragraph(
                "<b>Section</b>",
                normal_style
            ),
            section,
            Paragraph(
                "<b>Roll No.</b>",
                normal_style
            ),
            roll_no,
        ],
        [
            Paragraph(
                "<b>Date of Birth</b>",
                normal_style
            ),
            str(dob),
            Paragraph(
                "<b>Admission No.</b>",
                normal_style
            ),
            admission_no,
        ],
    ]

    detail_table = Table(
        details,
        colWidths=[
            30 * mm,
            65 * mm,
            30 * mm,
            45 * mm,
        ],
    )

    detail_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.whitesmoke,
                ),
                (
                    "BACKGROUND",
                    (2, 0),
                    (2, -1),
                    colors.whitesmoke,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, -1),
                    "Helvetica",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(detail_table)

    story.append(
        Spacer(1, 7 * mm)
    )

    # --------------------------------------------------------
    # MARKS
    # --------------------------------------------------------

    story.append(
        Paragraph(
            "Academic Performance",
            heading_style
        )
    )

    rows = [
        [
            "Subject",
            "Maximum",
            "Obtained",
            "%",
            "Grade",
        ]
    ]

    total_max = 0
    total_obtained = 0

    strong_subjects = []
    improvement_subjects = []

    for mark in marks:

        subject = safe_value(
            mark.get("subject"),
            "Subject"
        )

        maximum = mark.get(
            "max_marks",
            100
        )

        obtained = mark.get(
            "obtained_marks",
            0
        )

        try:
            maximum = float(maximum)
        except Exception:
            maximum = 100

        try:
            obtained = float(obtained)
        except Exception:
            obtained = 0

        percentage = (
            obtained / maximum * 100
            if maximum > 0
            else 0
        )

        grade = calculate_grade(
            percentage
        )

        total_max += maximum
        total_obtained += obtained

        if percentage >= 75:
            strong_subjects.append(
                str(subject)
            )

        if percentage < 40:
            improvement_subjects.append(
                str(subject)
            )

        rows.append(
            [
                str(subject),
                f"{maximum:g}",
                f"{obtained:g}",
                f"{percentage:.1f}%",
                grade,
            ]
        )

    overall_percentage = (
        total_obtained / total_max * 100
        if total_max > 0
        else 0
    )

    overall_grade = calculate_grade(
        overall_percentage
    )

    rows.append(
        [
            "TOTAL",
            f"{total_max:g}",
            f"{total_obtained:g}",
            f"{overall_percentage:.1f}%",
            overall_grade,
        ]
    )

    marks_table = Table(
        rows,
        colWidths=[
            70 * mm,
            28 * mm,
            28 * mm,
            28 * mm,
            25 * mm,
        ],
        repeatRows=1,
    )

    marks_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.lightgrey,
                ),
                (
                    "FONTNAME",
                    (0, 0),
                    (-1, 0),
                    "Helvetica-Bold",
                ),
                (
                    "FONTNAME",
                    (0, -1),
                    (-1, -1),
                    "Helvetica-Bold",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(marks_table)

    story.append(
        Spacer(1, 6 * mm)
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary_rows = [
        [
            Paragraph(
                "<b>Total Marks</b>",
                normal_style
            ),
            f"{total_obtained:g} / {total_max:g}",
        ],
        [
            Paragraph(
                "<b>Percentage</b>",
                normal_style
            ),
            f"{overall_percentage:.2f}%",
        ],
        [
            Paragraph(
                "<b>Overall Grade</b>",
                normal_style
            ),
            overall_grade,
        ],
    ]

    summary_table = Table(
        summary_rows,
        colWidths=[
            45 * mm,
            45 * mm,
        ],
    )

    summary_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.whitesmoke,
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(summary_table)

    story.append(
        Spacer(1, 6 * mm)
    )

    # --------------------------------------------------------
    # STRONG / IMPROVEMENT
    # --------------------------------------------------------

    strong_text = (
        ", ".join(strong_subjects)
        if strong_subjects
        else "No specific subject identified."
    )

    improvement_text = (
        ", ".join(improvement_subjects)
        if improvement_subjects
        else "No major improvement area."
    )

    performance_table = Table(
        [
            [
                Paragraph(
                    "<b>Strong Subjects</b>",
                    normal_style
                ),
                strong_text,
            ],
            [
                Paragraph(
                    "<b>Needs Improvement</b>",
                    normal_style
                ),
                improvement_text,
            ],
        ],
        colWidths=[
            45 * mm,
            135 * mm,
        ],
    )

    performance_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.whitesmoke,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ]
        )
    )

    story.append(
        performance_table
    )

    story.append(
        Spacer(1, 7 * mm)
    )

    # --------------------------------------------------------
    # REMARKS
    # --------------------------------------------------------

    teacher_remarks = safe_value(
        student.get("teacher_remarks")
    )

    principal_remarks = safe_value(
        student.get("principal_remarks")
    )

    school_default_remarks = safe_value(
        school.get("principal_remarks")
    )

    story.append(
        Paragraph(
            "Remarks",
            heading_style
        )
    )

    remarks_data = [
        [
            Paragraph(
                "<b>Teacher</b>",
                normal_style
            ),
            teacher_remarks or
            "Good progress. Continue regular study.",
        ],
        [
            Paragraph(
                "<b>Principal</b>",
                normal_style
            ),
            principal_remarks or
            school_default_remarks or
            "Keep working hard and maintain good discipline.",
        ],
    ]

    remarks_table = Table(
        remarks_data,
        colWidths=[
            35 * mm,
            145 * mm,
        ],
    )

    remarks_table.setStyle(
        TableStyle(
            [
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.grey,
                ),
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.whitesmoke,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ]
        )
    )

    story.append(
        remarks_table
    )

    story.append(
        Spacer(1, 15 * mm)
    )

    # --------------------------------------------------------
    # SIGNATURES
    # --------------------------------------------------------

    signature_table = Table(
        [
            [
                "Class Teacher",
                "",
                "Principal",
            ],
            [
                "________________",
                "",
                "________________",
            ],
        ],
        colWidths=[
            55 * mm,
            70 * mm,
            55 * mm,
        ],
    )

    signature_table.setStyle(
        TableStyle(
            [
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ]
        )
    )

    story.append(
        signature_table
    )

    story.append(
        Spacer(1, 8 * mm)
    )

    story.append(
        Paragraph(
            f"Generated on {datetime.now().strftime('%d-%m-%Y %H:%M')}",
            subtitle_style
        )
    )

    document.build(story)

    buffer.seek(0)

    return buffer


# ============================================================
# ADMIN SECURITY HELPERS
# ============================================================

def require_admin():

    profile = st.session_state.get(
        "profile"
    )

    if not profile:
        return False

    return (
        profile.get("role") == "Admin"
    )


def require_service_role():

    if supabase_admin is None:

        st.error(
            "SUPABASE_SERVICE_ROLE_KEY is not configured."
        )

        st.info(
            "Add it to Streamlit Cloud Secrets. "
            "Keep this key private."
        )

        return False

    return True


# ============================================================
# ADMIN USER FUNCTIONS
# ============================================================

def admin_create_user(
    email,
    password,
    full_name,
    role,
    active=True,
):

    if not require_service_role():
        return None, "Service role key missing."

    try:

        response = (
            supabase_admin
            .auth.admin.create_user(
                {
                    "email": email.strip(),
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {
                        "full_name": full_name,
                        "role": role,
                    },
                }
            )
        )

        user = response.user

        if not user:

            return None, "Auth user was not created."

        profile_data = {
            "id": user.id,
            "email": email.strip(),
            "full_name": full_name,
            "role": role,
            "active": active,
        }

        (
            supabase_admin
            .table("profiles")
            .upsert(
                profile_data
            )
            .execute()
        )

        return user.id, None

    except Exception as e:

        return None, str(e)


def admin_update_user(
    user_id,
    email,
    full_name,
    role,
    active,
    new_password="",
):

    if not require_service_role():
        return False

    try:

        auth_update = {
            "email": email.strip()
        }

        if new_password.strip():

            auth_update["password"] = (
                new_password.strip()
            )

        (
            supabase_admin
            .auth.admin
            .update_user_by_id(
                user_id,
                auth_update
            )
        )

        (
            supabase_admin
            .table("profiles")
            .update(
                {
                    "email": email.strip(),
                    "full_name": full_name,
                    "role": role,
                    "active": active,
                }
            )
            .eq(
                "id",
                user_id
            )
            .execute()
        )

        return True

    except Exception as e:

        st.error(
            str(e)
        )

        return False


def admin_delete_user(user_id):

    if not require_service_role():
        return False

    try:

        (
            supabase_admin
            .auth.admin
            .delete_user(user_id)
        )

        return True

    except Exception as e:

        st.error(
            str(e)
        )

        return False


def admin_force_logout(user_id):

    try:

        response = supabase.rpc(
            "force_logout_user",
            {
                "target_user_id": user_id
            }
        ).execute()

        return response.data

    except Exception as e:

        st.error(
            str(e)
        )

        return False


# ============================================================
# SIDEBAR
# ============================================================

def show_sidebar():

    profile = st.session_state.profile
    user = st.session_state.user

    with st.sidebar:

        st.title(
            "🏫 6thSense School"
        )

        if profile:

            st.write(
                f"**User:** "
                f"{profile.get('full_name') or user.email}"
            )

            st.write(
                f"**Role:** "
                f"{profile.get('role', 'User')}"
            )

            st.divider()

            if st.button(
                "🚪 Logout",
                use_container_width=True
            ):

                logout_user()


# ============================================================
# LOGIN SCREEN
# ============================================================

if st.session_state.user is None:

    st.title(
        "🏫 6thSense School Management"
    )

    st.subheader(
        "Secure Login"
    )

    st.info(
        "One User ID can have only one active device/session. "
        "Logging in on another device will invalidate the "
        "previous session."
    )

    with st.form(
        "login_form",
        clear_on_submit=False
    ):

        email = st.text_input(
            "Email"
        )

        password = st.text_input(
            "Password",
            type="password"
        )

        login_button = st.form_submit_button(
            "Login",
            use_container_width=True
        )

    if login_button:

        if not email.strip():

            st.error(
                "Enter your email."
            )

        elif not password:

            st.error(
                "Enter your password."
            )

        else:

            success, message = login_user(
                email,
                password
            )

            if success:

                st.success(
                    message
                )

                st.rerun()

            else:

                st.error(
                    message
                )

    st.stop()


# ============================================================
# SERVER-SIDE SESSION CHECK
# ============================================================

enforce_server_session()


# ============================================================
# CURRENT USER DATA
# ============================================================

user = st.session_state.user
profile = st.session_state.profile

if not user or not profile:

    clear_local_session()
    st.rerun()


role = profile.get(
    "role",
    "Staff"
)


# ============================================================
# SIDEBAR
# ============================================================

show_sidebar()


# ============================================================
# ADMIN DASHBOARD
# ============================================================

def admin_dashboard():

    st.title(
        "👑 Admin Dashboard"
    )

    st.caption(
        "Full school management access"
    )

    tabs = st.tabs(
        [
            "Dashboard",
            "Users",
            "Students",
            "Marks",
            "Assignments",
            "Report Card",
            "School Settings",
        ]
    )

    # ========================================================
    # DASHBOARD
    # ========================================================

    with tabs[0]:

        st.subheader(
            "School Overview"
        )

        try:

            student_count = (
                supabase
                .table("students")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
            )

            user_count = (
                supabase
                .table("profiles")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
            )

            marks_count = (
                supabase
                .table("marks")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
            )

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "Students",
                    student_count.count or 0
                )

            with c2:
                st.metric(
                    "Users",
                    user_count.count or 0
                )

            with c3:
                st.metric(
                    "Marks Records",
                    marks_count.count or 0
                )

        except Exception as e:

            st.error(
                str(e)
            )

    # ========================================================
    # USERS
    # ========================================================

    with tabs[1]:

        st.subheader(
            "User Management"
        )

        if not require_service_role():

            st.warning(
                "Admin user creation/deletion requires "
                "SUPABASE_SERVICE_ROLE_KEY."
            )

        else:

            create_col, list_col = st.columns(
                [1, 1.5]
            )

            with create_col:

                st.markdown(
                    "### Add User"
                )

                with st.form(
                    "create_user_form"
                ):

                    new_name = st.text_input(
                        "Full Name"
                    )

                    new_email = st.text_input(
                        "Email"
                    )

                    new_password = st.text_input(
                        "Temporary Password",
                        type="password"
                    )

                    new_role = st.selectbox(
                        "Role",
                        ROLES
                    )

                    new_active = st.checkbox(
                        "Active",
                        value=True
                    )

                    create_button = (
                        st.form_submit_button(
                            "Create User",
                            use_container_width=True
                        )
                    )

                if create_button:

                    if not new_email.strip():

                        st.error(
                            "Email is required."
                        )

                    elif len(new_password) < 6:

                        st.error(
                            "Password must be at least 6 characters."
                        )

                    else:

                        new_user_id, error = (
                            admin_create_user(
                                new_email,
                                new_password,
                                new_name,
                                new_role,
                                new_active
                            )
                        )

                        if error:

                            st.error(
                                error
                            )

                        else:

                            st.success(
                                "User created successfully."
                            )

                            st.code(
                                str(new_user_id)
                            )

            with list_col:

                st.markdown(
                    "### Existing Users"
                )

                try:

                    users_response = (
                        supabase
                        .table("profiles")
                        .select("*")
                        .order(
                            "created_at",
                            desc=True
                        )
                        .execute()
                    )

                    users_data = (
                        users_response.data or []
                    )

                    if users_data:

                        users_df = pd.DataFrame(
                            users_data
                        )

                        display_columns = [
                            c for c in [
                                "id",
                                "email",
                                "full_name",
                                "role",
                                "active",
                                "created_at",
                            ]
                            if c in users_df.columns
                        ]

                        st.dataframe(
                            users_df[
                                display_columns
                            ],
                            use_container_width=True,
                            hide_index=True
                        )

                    else:

                        st.info(
                            "No users found."
                        )

                except Exception as e:

                    st.error(
                        str(e)
                    )

        # ----------------------------------------------------
        #  MODIFY USER
        # ----------------------------------------------------

        st.divider()

        st.markdown(
            "### Modify / Delete User"
        )

        try:

            users_response = (
                supabase
                .table("profiles")
                .select("*")
                .order(
                    "full_name"
                )
                .execute()
            )

            all_users = (
                users_response.data or []
            )

        except Exception as e:

            all_users = []
            st.error(str(e))

        if all_users:

            user_options = {
                (
                    f"{u.get('full_name') or 'Unnamed'} "
                    f"| {u.get('email') or ''} "
                    f"| {u.get('role') or ''}"
                ): u
                for u in all_users
            }

            selected_label = st.selectbox(
                "Select User",
                list(user_options.keys()),
                key="modify_user_select"
            )

            selected_user = user_options[
                selected_label
            ]

            with st.form(
                "modify_user_form"
            ):

                edit_name = st.text_input(
                    "Full Name",
                    value=selected_user.get(
                        "full_name"
                    ) or ""
                )

                edit_email = st.text_input(
                    "Email",
                    value=selected_user.get(
                        "email"
                    ) or ""
                )

                edit_role = st.selectbox(
                    "Role",
                    ROLES,
                    index=(
                        ROLES.index(
                            selected_user.get(
                                "role"
                            )
                        )
                        if selected_user.get("role")
                        in ROLES
                        else 0
                    )
                )

                edit_active = st.checkbox(
                    "Active",
                    value=bool(
                        selected_user.get(
                            "active",
                            True
                        )
                    )
                )

                edit_password = st.text_input(
                    "New Password "
                    "(leave blank to keep current)",
                    type="password"
                )

                update_button = (
                    st.form_submit_button(
                        "Save Changes",
                        use_container_width=True
                    )
                )

            if update_button:

                if admin_update_user(
                    selected_user["id"],
                    edit_email,
                    edit_name,
                    edit_role,
                    edit_active,
                    edit_password
                ):

                    st.success(
                        "User updated."
                    )

                    st.rerun()

            st.markdown(
                "### Session Control"
            )

            if st.button(
                "🔒 Force Logout Selected User",
                use_container_width=True
            ):

                if admin_force_logout(
                    selected_user["id"]
                ):

                    st.success(
                        "Active session invalidated."
                    )

            st.markdown(
                "### Delete User"
            )

            st.warning(
                "Deleting a user permanently removes "
                "their Supabase Auth account."
            )

            delete_confirm = st.checkbox(
                "I understand this cannot be easily undone.",
                key="delete_confirm"
            )

            if st.button(
                "🗑️ Delete Selected User",
                disabled=not delete_confirm,
                use_container_width=True
            ):

                if (
                    selected_user["id"]
                    == user.id
                ):

                    st.error(
                        "You cannot delete the currently "
                        "logged-in admin."
                    )

                elif admin_delete_user(
                    selected_user["id"]
                ):

                    st.success(
                        "User deleted."
                    )

                    st.rerun()

    # ========================================================
    # STUDENTS
    # ========================================================

    with tabs[2]:

        st.subheader(
            "Student Management"
        )

        create_student, student_list = st.columns(
            [1, 1.5]
        )

        with create_student:

            st.markdown(
                "### Add Student"
            )

            with st.form(
                "create_student_form"
            ):

                student_name = st.text_input(
                    "Student Name"
                )

                student_class = st.text_input(
                    "Class"
                )

                student_section = st.text_input(
                    "Section"
                )

                student_roll = st.text_input(
                    "Roll No."
                )

                student_dob = st.date_input(
                    "Date of Birth",
                    value=date(
                        2012,
                        1,
                        1
                    )
                )

                admission_no = st.text_input(
                    "Admission No."
                )

                student_user_id = st.text_input(
                    "Student Auth User ID "
                    "(optional)"
                )

                add_student_button = (
                    st.form_submit_button(
                        "Add Student",
                        use_container_width=True
                    )
                )

            if add_student_button:

                if not student_name.strip():

                    st.error(
                        "Student name is required."
                    )

                else:

                    try:

                        student_record = {
                            "name": student_name.strip(),
                            "class_name": student_class.strip(),
                            "section": student_section.strip(),
                            "roll_no": student_roll.strip(),
                            "dob": str(student_dob),
                            "admission_no": admission_no.strip(),
                        }

                        if student_user_id.strip():

                            student_record[
                                "user_id"
                            ] = student_user_id.strip()

                        # TEMPORARY DEBUG
                        st.write(
                            "DEBUG USER:",
                            supabase.auth.get_user()
                        )

                        response = (
                            supabase
                            .table("students")
                            .insert(
                                student_record
                            )
                            .execute()
                        )

                        st.success(
                            "Student added successfully."
                        )

                    except Exception as e:

                        st.error(
                            str(e)
                        )

        with student_list:

            st.markdown(
                "### Students"
            )

            try:

                response = (
                    supabase
                    .table("students")
                    .select("*")
                    .order(
                        "class_name"
                    )
                    .order(
                        "roll_no"
                    )
                    .execute()
                )

                students_data = (
                    response.data or []
                )

                if students_data:

                    students_df = pd.DataFrame(
                        students_data
                    )

                    st.dataframe(
                        students_df,
                        use_container_width=True,
                        hide_index=True
                    )

                else:

                    st.info(
                        "No students found."
                    )

            except Exception as e:

                st.error(
                    str(e)
                )

    # ========================================================
    # MARKS
    # ========================================================

    with tabs[3]:

        st.subheader(
            "Marks Management"
        )

        try:

            response = (
                supabase
                .table("students")
                .select("*")
                .order("name")
                .execute()
            )

            students_data = (
                response.data or []
            )

        except Exception as e:

            students_data = []
            st.error(str(e))

        if students_data:

            student_options = {
                (
                    f"{s.get('name')} | "
                    f"Class {s.get('class_name')} | "
                    f"Roll {s.get('roll_no')}"
                ): s
                for s in students_data
            }

            selected_student_label = (
                st.selectbox(
                    "Student",
                    list(
                        student_options.keys()
                    ),
                    key="admin_marks_student"
                )
            )

            selected_student = (
                student_options[
                    selected_student_label
                ]
            )

            with st.form(
                "add_marks_form"
            ):

                subject = st.text_input(
                    "Subject"
                )

                max_marks = st.number_input(
                    "Maximum Marks",
                    min_value=1.0,
                    value=100.0
                )

                obtained_marks = st.number_input(
                    "Obtained Marks",
                    min_value=0.0,
                    value=0.0,
                    max_value=max_marks
                )

                exam_name = st.text_input(
                    "Exam / Assessment",
                    value="Annual Examination"
                )

                marks_session = st.selectbox(
                    "Academic Session",
                    ACADEMIC_SESSIONS
                )

                add_marks_button = (
                    st.form_submit_button(
                        "Save Marks",
                        use_container_width=True
                    )
                )

            if add_marks_button:

                if not subject.strip():

                    st.error(
                        "Subject is required."
                    )

                else:

                    try:

                        mark_record = {
                            "student_id":
                                selected_student["id"],
                            "subject":
                                subject.strip(),
                            "max_marks":
                                max_marks,
                            "obtained_marks":
                                obtained_marks,
                            "exam_name":
                                exam_name.strip(),
                            "academic_session":
                                marks_session,
                        }

                        (
                            supabase
                            .table("marks")
                            .insert(
                                mark_record
                            )
                            .execute()
                        )

                        st.success(
                            "Marks saved."
                        )

                    except Exception as e:

                        st.error(
                            str(e)
                        )

    # ========================================================
    # ASSIGNMENTS
    # ========================================================

    with tabs[4]:

        st.subheader(
            "Teacher / Parent Assignments"
        )

        assignment_tabs = st.tabs(
            [
                "Teacher → Student",
                "Parent → Student",
            ]
        )

        # ----------------------------------------------------
        # TEACHER
        # ----------------------------------------------------

        with assignment_tabs[0]:

            try:

                teacher_response = (
                    supabase
                    .table("profiles")
                    .select("*")
                    .eq("role", "Teacher")
                    .execute()
                )

                teacher_data = (
                    teacher_response.data or []
                )

                student_response = (
                    supabase
                    .table("students")
                    .select("*")
                    .order("name")
                    .execute()
                )

                assignment_students = (
                    student_response.data or []
                )

            except Exception as e:

                teacher_data = []
                assignment_students = []

                st.error(str(e))

            if teacher_data and assignment_students:

                teacher_options = {
                    (
                        f"{x.get('full_name') or 'Teacher'} "
                        f"| {x.get('email')}"
                    ): x
                    for x in teacher_data
                }

                student_options_2 = {
                    (
                        f"{x.get('name')} "
                        f"| Class {x.get('class_name')} "
                        f"| Roll {x.get('roll_no')}"
                    ): x
                    for x in assignment_students
                }

                teacher_label = st.selectbox(
                    "Teacher",
                    list(
                        teacher_options.keys()
                    ),
                    key="assign_teacher"
                )

                student_label_2 = st.selectbox(
                    "Student",
                    list(
                        student_options_2.keys()
                    ),
                    key="assign_teacher_student"
                )

                if st.button(
                    "Assign Teacher to Student",
                    use_container_width=True
                ):

                    try:

                        (
                            supabase
                            .table("teacher_students")
                            .insert(
                                {
                                    "teacher_id":
                                        teacher_options[
                                            teacher_label
                                        ]["id"],
                                    "student_id":
                                        student_options_2[
                                            student_label_2
                                        ]["id"],
                                }
                            )
                            .execute()
                        )

                        st.success(
                            "Teacher assigned."
                        )

                    except Exception as e:

                        st.error(
                            str(e)
                        )

            else:

                st.info(
                    "Create at least one Teacher and "
                    "one Student first."
                )

        # ----------------------------------------------------
        # PARENT
        # ----------------------------------------------------

        with assignment_tabs[1]:

            try:

                parent_response = (
                    supabase
                    .table("profiles")
                    .select("*")
                    .eq("role", "Parent")
                    .execute()
                )

                parent_data = (
                    parent_response.data or []
                )

                student_response = (
                    supabase
                    .table("students")
                    .select("*")
                    .order("name")
                    .execute()
                )

                parent_students = (
                    student_response.data or []
                )

            except Exception as e:

                parent_data = []
                parent_students = []

                st.error(str(e))

            if parent_data and parent_students:

                parent_options = {
                    (
                        f"{x.get('full_name') or 'Parent'} "
                        f"| {x.get('email')}"
                    ): x
                    for x in parent_data
                }

                student_options_3 = {
                    (
                        f"{x.get('name')} "
                        f"| Class {x.get('class_name')} "
                        f"| Roll {x.get('roll_no')}"
                    ): x
                    for x in parent_students
                }

                parent_label = st.selectbox(
                    "Parent",
                    list(
                        parent_options.keys()
                    ),
                    key="assign_parent"
                )

                parent_student_label = (
                    st.selectbox(
                        "Student",
                        list(
                            student_options_3.keys()
                        ),
                        key="assign_parent_student"
                    )
                )

                if st.button(
                    "Assign Parent to Student",
                    use_container_width=True
                ):

                    try:

                        (
                            supabase
                            .table("parent_students")
                            .insert(
                                {
                                    "parent_id":
                                        parent_options[
                                            parent_label
                                        ]["id"],
                                    "student_id":
                                        student_options_3[
                                            parent_student_label
                                        ]["id"],
                                }
                            )
                            .execute()
                        )

                        st.success(
                            "Parent assigned."
                        )

                    except Exception as e:

                        st.error(
                            str(e)
                        )

            else:

                st.info(
                    "Create at least one Parent and "
                    "one Student first."
                )

    # ========================================================
    # REPORT CARD
    # ========================================================

    with tabs[5]:

        st.subheader(
            "Generate Report Card"
        )

        try:

            response = (
                supabase
                .table("students")
                .select("*")
                .order("name")
                .execute()
            )

            report_students = (
                response.data or []
            )

        except Exception as e:

            report_students = []
            st.error(str(e))

        if report_students:

            report_options = {
                (
                    f"{s.get('name')} | "
                    f"Class {s.get('class_name')} | "
                    f"Roll {s.get('roll_no')}"
                ): s
                for s in report_students
            }

            report_label = st.selectbox(
                "Select Student",
                list(
                    report_options.keys()
                ),
                key="report_student"
            )

            report_student = report_options[
                report_label
            ]

            if st.button(
                "Generate PDF Report Card",
                use_container_width=True
            ):

                try:

                    marks_response = (
                        supabase
                        .table("marks")
                        .select("*")
                        .eq(
                            "student_id",
                            report_student["id"]
                        )
                        .order("subject")
                        .execute()
                    )

                    report_marks = (
                        marks_response.data or []
                    )

                    school = get_school_settings()

                    pdf = create_report_card(
                        report_student,
                        report_marks,
                        school
                    )

                    st.download_button(
                        "⬇️ Download Report Card PDF",
                        data=pdf.getvalue(),
                        file_name=(
                            f"{report_student.get('name', 'Student')}"
                            f"_Report_Card.pdf"
                        ),
                        mime="application/pdf",
                        use_container_width=True
                    )

                except Exception as e:

                    st.error(
                        str(e)
                    )

    # ========================================================
    # SCHOOL SETTINGS
    # ========================================================

    with tabs[6]:

        st.subheader(
            "🏫 School Settings"
        )

        school = get_school_settings()

        with st.form(
            "school_settings_form"
        ):

            school_name = st.text_input(
                "School Name",
                value=school.get(
                    "school_name",
                    ""
                )
            )

            school_address = st.text_area(
                "School Address",
                value=school.get(
                    "school_address",
                    ""
                )
            )

            school_phone = st.text_input(
                "Phone",
                value=school.get(
                    "phone",
                    ""
                )
            )

            school_email = st.text_input(
                "Email",
                value=school.get(
                    "email",
                    ""
                )
            )

            academic_session = st.selectbox(
                "Academic Session",
                ACADEMIC_SESSIONS,
                index=(
                    ACADEMIC_SESSIONS.index(
                        school.get(
                            "academic_session"
                        )
                    )
                    if school.get(
                        "academic_session"
                    ) in ACADEMIC_SESSIONS
                    else 0
                )
            )

            logo_url = st.text_input(
                "School Logo URL",
                value=school.get(
                    "logo_url",
                    ""
                ),
                help=(
                    "Paste a publicly accessible "
                    "image URL. This can be replaced "
                    "later without changing app.py."
                )
            )

            principal_name = st.text_input(
                "Principal Name",
                value=school.get(
                    "principal_name",
                    ""
                )
            )

            principal_remarks = st.text_area(
                "Default Principal Remarks",
                value=school.get(
                    "principal_remarks",
                    ""
                )
            )

            save_settings_button = (
                st.form_submit_button(
                    "Save School Settings",
                    use_container_width=True
                )
            )

        if save_settings_button:

            try:

                existing_id = school.get(
                    "id"
                )

                settings_record = {
                    "school_name":
                        school_name.strip(),
                    "school_address":
                        school_address.strip(),
                    "phone":
                        school_phone.strip(),
                    "email":
                        school_email.strip(),
                    "academic_session":
                        academic_session,
                    "logo_url":
                        logo_url.strip(),
                    "principal_name":
                        principal_name.strip(),
                    "principal_remarks":
                        principal_remarks.strip(),
                }

                if existing_id:

                    (
                        supabase
                        .table("school_settings")
                        .update(
                            settings_record
                        )
                        .eq(
                            "id",
                            existing_id
                        )
                        .execute()
                    )

                else:

                    (
                        supabase
                        .table("school_settings")
                        .insert(
                            settings_record
                        )
                        .execute()
                    )

                st.success(
                    "School settings saved."
                )

            except Exception as e:

                st.error(
                    str(e)
                )


# ============================================================
# STUDENT DASHBOARD
# ============================================================

def student_dashboard():

    st.title(
        "🎓 Student Dashboard"
    )

    student_user_id = user.id

    try:

        student_response = (
            supabase
            .table("students")
            .select("*")
            .eq(
                "user_id",
                student_user_id
            )
            .maybe_single()
            .execute()
        )

        student = student_response.data

    except Exception as e:

        st.error(
            str(e)
        )

        return

    if not student:

        st.warning(
            "Your student record has not been linked "
            "to your User ID yet."
        )

        return

    st.subheader(
        f"Welcome, {student.get('name', '')}"
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "Class",
            student.get(
                "class_name",
                "-"
            )
        )

    with c2:
        st.metric(
            "Section",
            student.get(
                "section",
                "-"
            )
        )

    with c3:
        st.metric(
            "Roll No.",
            student.get(
                "roll_no",
                "-"
            )
        )

    st.divider()

    try:

        marks_response = (
            supabase
            .table("marks")
            .select("*")
            .eq(
                "student_id",
                student["id"]
            )
            .order("subject")
            .execute()
        )

        marks = (
            marks_response.data or []
        )

    except Exception as e:

        st.error(
            str(e)
        )

        marks = []

    st.subheader(
        "📚 My Marks"
    )

    if marks:

        df = pd.DataFrame(
            marks
        )

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        if st.button(
            "Generate My Report Card",
            use_container_width=True
        ):

            school = get_school_settings()

            pdf = create_report_card(
                student,
                marks,
                school
            )

            st.download_button(
                "⬇️ Download My Report Card",
                data=pdf.getvalue(),
                file_name=(
                    f"{student.get('name', 'Student')}"
                    f"_Report_Card.pdf"
                ),
                mime="application/pdf",
                use_container_width=True
            )

    else:

        st.info(
            "No marks have been entered yet."
        )


# ============================================================
# TEACHER DASHBOARD
# ============================================================

def teacher_dashboard():

    st.title(
        "👨‍🏫 Teacher Dashboard"
    )

    st.caption(
        "Only students assigned to you are visible."
    )

    try:

        response = (
            supabase
            .table("students")
            .select("*")
            .order("class_name")
            .order("roll_no")
            .execute()
        )

        students = (
            response.data or []
        )

    except Exception as e:

        st.error(
            str(e)
        )

        return

    if students:

        st.dataframe(
            pd.DataFrame(students),
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader(
            "Enter Marks"
        )

        student_options = {
            (
                f"{s.get('name')} | "
                f"Class {s.get('class_name')} | "
                f"Roll {s.get('roll_no')}"
            ): s
            for s in students
        }

        selected_label = st.selectbox(
            "Student",
            list(
                student_options.keys()
            )
        )

        selected_student = student_options[
            selected_label
        ]

        with st.form(
            "teacher_marks_form"
        ):

            subject = st.text_input(
                "Subject"
            )

            max_marks = st.number_input(
                "Maximum Marks",
                min_value=1.0,
                value=100.0
            )

            obtained_marks = st.number_input(
                "Obtained Marks",
                min_value=0.0,
                max_value=max_marks,
                value=0.0
            )

            exam_name = st.text_input(
                "Exam",
                value="Class Test"
            )

            save_button = (
                st.form_submit_button(
                    "Save Marks",
                    use_container_width=True
                )
            )

        if save_button:

            try:

                (
                    supabase
                    .table("marks")
                    .insert(
                        {
                            "student_id":
                                selected_student["id"],
                            "subject":
                                subject.strip(),
                            "max_marks":
                                max_marks,
                            "obtained_marks":
                                obtained_marks,
                            "exam_name":
                                exam_name.strip(),
                            "academic_session":
                                "2026-27",
                        }
                    )
                    .execute()
                )

                st.success(
                    "Marks saved."
                )

            except Exception as e:

                st.error(
                    str(e)
                )

    else:

        st.info(
            "No students are assigned to you."
        )


# ============================================================
# PARENT DASHBOARD
# ============================================================

def parent_dashboard():

    st.title(
        "👨‍👩‍👧 Parent Dashboard"
    )

    st.caption(
        "Only children linked to your account are visible."
    )

    try:

        relation_response = (
            supabase
            .table("parent_students")
            .select("student_id")
            .eq(
                "parent_id",
                user.id
            )
            .execute()
        )

        relations = (
            relation_response.data or []
        )

        student_ids = [
            r["student_id"]
            for r in relations
            if r.get("student_id")
        ]

        if not student_ids:

            st.info(
                "No student has been linked to your "
                "parent account yet."
            )

            return

        students_response = (
            supabase
            .table("students")
            .select("*")
            .in_(
                "id",
                student_ids
            )
            .order("name")
            .execute()
        )

        children = (
            students_response.data or []
        )

    except Exception as e:

        st.error(
            str(e)
        )

        return

    if not children:

        st.info(
            "No children found."
        )

        return

    child_options = {
        (
            f"{s.get('name')} | "
            f"Class {s.get('class_name')} | "
            f"Roll {s.get('roll_no')}"
        ): s
        for s in children
    }

    selected_child_label = st.selectbox(
        "Select Child",
        list(
            child_options.keys()
        )
    )

    child = child_options[
        selected_child_label
    ]

    st.subheader(
        child.get("name", "")
    )

    try:

        marks_response = (
            supabase
            .table("marks")
            .select("*")
            .eq(
                "student_id",
                child["id"]
            )
            .order("subject")
            .execute()
        )

        marks = (
            marks_response.data or []
        )

    except Exception as e:

        st.error(
            str(e)
        )

        marks = []

    if marks:

        st.dataframe(
            pd.DataFrame(marks),
            use_container_width=True,
            hide_index=True
        )

        if st.button(
            "Generate Report Card",
            use_container_width=True
        ):

            school = get_school_settings()

            pdf = create_report_card(
                child,
                marks,
                school
            )

            st.download_button(
                "⬇️ Download Report Card",
                data=pdf.getvalue(),
                file_name=(
                    f"{child.get('name', 'Student')}"
                    f"_Report_Card.pdf"
                ),
                mime="application/pdf",
                use_container_width=True
            )

    else:

        st.info(
            "No marks available yet."
        )


# ============================================================
# STAFF DASHBOARD
# ============================================================

def staff_dashboard():

    st.title(
        "🧑‍💼 Staff Dashboard"
    )

    st.info(
        "You are logged in as Staff."
    )

    st.write(
        "Staff access can be expanded later according "
        "to the responsibilities assigned by the Admin."
    )


# ============================================================
# ROLE ROUTER
# ============================================================

if role == "Admin":

    admin_dashboard()

elif role == "Teacher":

    teacher_dashboard()

elif role == "Student":

    student_dashboard()

elif role == "Parent":

    parent_dashboard()

elif role == "Staff":

    staff_dashboard()

else:

    st.error(
        f"Unknown role: {role}"
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "6thSense School Management System • "
    "Secure Supabase authentication • "
    "One active session per User ID"
)




          
  







             
