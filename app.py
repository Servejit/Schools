import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="School Management System",
    page_icon="🏫",
    layout="wide"
)

# --------------------------------------------------
# SUPABASE CONNECTION
# --------------------------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_PUBLISHABLE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------
# SESSION
# --------------------------------------------------

if "user" not in st.session_state:
    st.session_state.user = None

if "profile" not in st.session_state:
    st.session_state.profile = None


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

def login():
    st.title("🏫 School Management System")
    st.subheader("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):

        if not email or not password:
            st.error("Please enter email and password.")
            return

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if not result.user:
                st.error("Login failed.")
                return

            st.session_state.user = result.user

            profile = (
                supabase
                .table("profiles")
                .select("*")
                .eq("id", result.user.id)
                .single()
                .execute()
            )

            if not profile.data:
                st.error("Profile not found.")
                return

            if not profile.data["active"]:
                st.error("Your account is inactive.")
                supabase.auth.sign_out()
                st.session_state.user = None
                return

            st.session_state.profile = profile.data

            st.success("Login successful!")
            st.rerun()

        except Exception as e:
            st.error(f"Login failed: {e}")


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

def dashboard():

    profile = st.session_state.profile

    st.sidebar.title("🏫 School System")

    st.sidebar.write(
        f"**{profile.get('full_name') or profile.get('email')}**"
    )

    st.sidebar.write(
        f"Role: **{profile.get('role')}**"
    )

    if st.sidebar.button("Logout"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.session_state.profile = None
        st.rerun()

    st.title("🏫 School Management Dashboard")

    role = profile.get("role")

    if role == "SuperAdmin":
        superadmin_dashboard()

    elif role == "Admin":
        admin_dashboard()

    elif role == "Teacher":
        teacher_dashboard()

    elif role == "Student":
        student_dashboard()

    elif role == "Parent":
        parent_dashboard()

    else:
        st.error("Unknown user role.")


# --------------------------------------------------
# SUPER ADMIN
# --------------------------------------------------

def superadmin_dashboard():

    st.header("👑 SuperAdmin")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Schools",
            get_count("schools")
        )

    with col2:
        st.metric(
            "Students",
            get_count("students")
        )

    with col3:
        st.metric(
            "Users",
            get_count("profiles")
        )

    st.divider()

    st.subheader("🏫 Schools")

    try:
        schools = (
            supabase
            .table("schools")
            .select("*")
            .order("name")
            .execute()
        )

        if schools.data:
            st.dataframe(
                schools.data,
                use_container_width=True
            )
        else:
            st.info("No schools found.")

    except Exception as e:
        st.error(str(e))


# --------------------------------------------------
# ADMIN
# --------------------------------------------------

def admin_dashboard():

    st.header("👨‍💼 Admin")

    school_id = st.session_state.profile.get("school_id")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Students",
            get_count("students", school_id)
        )

    with col2:
        st.metric(
            "Classes",
            get_count("classes", school_id)
        )

    with col3:
        st.metric(
            "Subjects",
            get_count("subjects", school_id)
        )

    with col4:
        st.metric(
            "Teachers",
            get_role_count("Teacher", school_id)
        )

    st.divider()

    st.info(
        "Admin modules will be added next: "
        "Students, Teachers, Classes, Subjects, "
        "Marks, Attendance, Fees and Report Cards."
    )


# --------------------------------------------------
# TEACHER
# --------------------------------------------------

def teacher_dashboard():

    st.header("👩‍🏫 Teacher")

    st.info(
        "Teacher modules will include bulk marks entry, "
        "bulk attendance and student records."
    )


# --------------------------------------------------
# STUDENT
# --------------------------------------------------

def student_dashboard():

    st.header("👨‍🎓 Student")

    user_id = st.session_state.user.id

    try:
        result = (
            supabase
            .table("students")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if result.data:

            student = result.data

            st.subheader(student.get("name", ""))

            col1, col2, col3 = st.columns(3)

            with col1:
                st.write(
                    f"**Class:** {student.get('class_name', '-')}"
                )

            with col2:
                st.write(
                    f"**Section:** {student.get('section', '-')}"
                )

            with col3:
                st.write(
                    f"**Roll No.:** {student.get('roll_no', '-')}"
                )

        else:
            st.warning(
                "Your student record has not been linked yet."
            )

    except Exception as e:
        st.error(str(e))


# --------------------------------------------------
# PARENT
# --------------------------------------------------

def parent_dashboard():

    st.header("👨‍👩‍👧 Parent")

    st.info(
        "Parent dashboard will show linked children's "
        "marks, attendance, fees and report cards."
    )


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def get_count(table, school_id=None):

    try:

        query = (
            supabase
            .table(table)
            .select("id", count="exact")
        )

        if school_id:
            query = query.eq("school_id", school_id)

        result = query.execute()

        return result.count or 0

    except Exception:
        return 0


def get_role_count(role, school_id=None):

    try:

        query = (
            supabase
            .table("profiles")
            .select("id", count="exact")
            .eq("role", role)
        )

        if school_id:
            query = query.eq("school_id", school_id)

        result = query.execute()

        return result.count or 0

    except Exception:
        return 0


# --------------------------------------------------
# APP
# --------------------------------------------------

if st.session_state.user is None:
    login()
else:
    dashboard()
