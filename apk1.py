import streamlit as st
from supabase import create_client, Client

# =========================================================
# PAGE
# =========================================================
st.set_page_config(
    page_title="School Management System",
    page_icon="🏫",
    layout="wide"
)

# =========================================================
# SUPABASE
# =========================================================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_PUBLISHABLE_KEY"]

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# =========================================================
# SESSION
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user" not in st.session_state:
    st.session_state.user = None

if "profile" not in st.session_state:
    st.session_state.profile = None


# =========================================================
# LOGIN
# =========================================================
def login():
    st.title("🏫 School Management System")
    st.subheader("Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("🔐 Login", use_container_width=True):

        if not email or not password:
            st.warning("Please enter email and password.")
            return

        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            user = result.user

            if not user:
                st.error("Login failed.")
                return

            profile_result = (
                supabase
                .table("profiles")
                .select("*")
                .eq("id", user.id)
                .single()
                .execute()
            )

            profile = profile_result.data

            if not profile:
                st.error("Profile not found.")
                return

            if profile.get("active") is False:
                st.error("Your account is inactive.")
                supabase.auth.sign_out()
                return

            st.session_state.logged_in = True
            st.session_state.user = user
            st.session_state.profile = profile

            st.rerun()

        except Exception as e:
            st.error("Login failed.")
            st.caption(str(e))


# =========================================================
# LOGOUT
# =========================================================
def logout():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.profile = None

    st.rerun()


# =========================================================
# SCHOOL MANAGEMENT
# =========================================================
def school_management():

    st.header("🏫 School Management")

    # -----------------------------------------------------
    # LOAD SCHOOLS
    # -----------------------------------------------------
    try:
        result = (
            supabase
            .table("schools")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        schools = result.data or []

    except Exception as e:
        st.error("Could not load schools.")
        st.code(str(e))
        return

    # -----------------------------------------------------
    # ADD SCHOOL
    # -----------------------------------------------------
    with st.expander("➕ Add New School", expanded=False):

        col1, col2 = st.columns(2)

        with col1:
            school_name = st.text_input(
                "School Name",
                key="new_school_name"
            )

        with col2:
            school_code = st.text_input(
                "School Code",
                key="new_school_code"
            )

        address = st.text_area(
            "School Address",
            key="new_school_address"
        )

        if st.button(
            "➕ Add School",
            use_container_width=True
        ):

            if not school_name.strip():
                st.warning("Enter school name.")
                return

            if not school_code.strip():
                st.warning("Enter school code.")
                return

            try:

                # Check duplicate code
                existing = (
                    supabase
                    .table("schools")
                    .select("id")
                    .eq("code", school_code.strip())
                    .execute()
                )

                if existing.data:
                    st.error("This school code already exists.")
                    return

                insert_result = (
                    supabase
                    .table("schools")
                    .insert({
                        "name": school_name.strip(),
                        "code": school_code.strip(),
                        "address": address.strip() if address else "",
                        "active": True
                    })
                    .execute()
                )

                if insert_result.data:
                    st.success("School added successfully.")
                    st.rerun()
                else:
                    st.error("School could not be added.")

            except Exception as e:
                st.error("Error adding school.")
                st.code(str(e))

    st.divider()

    # -----------------------------------------------------
    # SCHOOL LIST
    # -----------------------------------------------------
    st.subheader("📋 Schools")

    if not schools:
        st.info("No schools found.")
        return

    for school in schools:

        school_id = school.get("id")
        name = school.get("name", "")
        code = school.get("code", "")
        address = school.get("address") or ""
        active = school.get("active", True)

        with st.container(border=True):

            col1, col2, col3, col4 = st.columns(
                [3, 2, 3, 1]
            )

            with col1:
                st.markdown(f"### 🏫 {name}")
                st.caption(f"Code: {code}")

            with col2:
                if active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with col3:
                if address:
                    st.caption(address)
                else:
                    st.caption("No address added")

            with col4:
                if active:
                    button_text = "Deactivate"
                else:
                    button_text = "Activate"

                if st.button(
                    button_text,
                    key=f"status_{school_id}"
                ):

                    try:

                        supabase.table("schools").update({
                            "active": not active
                        }).eq(
                            "id", school_id
                        ).execute()

                        st.rerun()

                    except Exception as e:
                        st.error(str(e))

            # -------------------------------------------------
            # EDIT SCHOOL
            # -------------------------------------------------
            with st.expander("✏️ Edit School"):

                edit_name = st.text_input(
                    "School Name",
                    value=name,
                    key=f"name_{school_id}"
                )

                edit_code = st.text_input(
                    "School Code",
                    value=code,
                    key=f"code_{school_id}"
                )

                edit_address = st.text_area(
                    "Address",
                    value=address,
                    key=f"address_{school_id}"
                )

                if st.button(
                    "💾 Save Changes",
                    key=f"save_{school_id}",
                    use_container_width=True
                ):

                    if not edit_name.strip():
                        st.warning("School name cannot be empty.")
                        continue

                    if not edit_code.strip():
                        st.warning("School code cannot be empty.")
                        continue

                    try:

                        # Check if another school has same code
                        duplicate = (
                            supabase
                            .table("schools")
                            .select("id")
                            .eq("code", edit_code.strip())
                            .neq("id", school_id)
                            .execute()
                        )

                        if duplicate.data:
                            st.error(
                                "Another school already uses this code."
                            )
                            continue

                        (
                            supabase
                            .table("schools")
                            .update({
                                "name": edit_name.strip(),
                                "code": edit_code.strip(),
                                "address": edit_address.strip()
                            })
                            .eq("id", school_id)
                            .execute()
                        )

                        st.success("School updated.")
                        st.rerun()

                    except Exception as e:
                        st.error("Could not update school.")
                        st.code(str(e))


# =========================================================
# SUPERADMIN DASHBOARD
# =========================================================
def superadmin_dashboard():

    profile = st.session_state.profile

    school_id = profile.get("school_id")

    st.title("👑 SuperAdmin Dashboard")

    st.write(
        f"Welcome, **{profile.get('full_name') or profile.get('email')}**"
    )

    st.divider()

    # -----------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------
    try:

        schools_result = (
            supabase
            .table("schools")
            .select("id", count="exact")
            .execute()
        )

        users_result = (
            supabase
            .table("profiles")
            .select("id", count="exact")
            .execute()
        )

        students_result = (
            supabase
            .table("students")
            .select("id", count="exact")
            .execute()
        )

        school_count = schools_result.count or 0
        user_count = users_result.count or 0
        student_count = students_result.count or 0

    except Exception:
        school_count = 0
        user_count = 0
        student_count = 0

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric("🏫 Schools", school_count)

    with c2:
        st.metric("👥 Users", user_count)

    with c3:
        st.metric("🎓 Students", student_count)

    st.divider()

    # -----------------------------------------------------
    # NAVIGATION
    # -----------------------------------------------------
    menu = st.radio(
        "Management",
        [
            "🏫 Schools",
            "👥 Users",
            "🎓 Students",
            "📚 Classes & Subjects",
            "📝 Marks",
            "📅 Attendance",
            "🖨️ Print Templates",
            "📊 Reports"
        ],
        horizontal=True
    )

    st.divider()

    if menu == "🏫 Schools":
        school_management()

    elif menu == "👥 Users":
        st.info("User Management will be added next.")

    elif menu == "🎓 Students":
        st.info("Student Management will be added next.")

    elif menu == "📚 Classes & Subjects":
        st.info("Classes & Subjects will be added next.")

    elif menu == "📝 Marks":
        st.info("Bulk Marks Entry will be added next.")

    elif menu == "📅 Attendance":
        st.info("Bulk Attendance will be added next.")

    elif menu == "🖨️ Print Templates":
        st.info("A4 Print Template Management will be added next.")

    elif menu == "📊 Reports":
        st.info("Reports will be added next.")


# =========================================================
# ADMIN DASHBOARD
# =========================================================
def admin_dashboard():

    profile = st.session_state.profile

    st.title("🛠️ Admin Dashboard")

    st.write(
        f"Welcome, **{profile.get('full_name') or profile.get('email')}**"
    )

    st.info("Admin modules will be added next.")


# =========================================================
# TEACHER DASHBOARD
# =========================================================
def teacher_dashboard():

    profile = st.session_state.profile

    st.title("👨‍🏫 Teacher Dashboard")

    st.write(
        f"Welcome, **{profile.get('full_name') or profile.get('email')}**"
    )

    st.info("Teacher modules will be added next.")


# =========================================================
# STUDENT DASHBOARD
# =========================================================
def student_dashboard():

    profile = st.session_state.profile

    st.title("🎓 Student Dashboard")

    st.write(
        f"Welcome, **{profile.get('full_name') or profile.get('email')}**"
    )

    try:

        result = (
            supabase
            .table("students")
            .select("*")
            .eq("user_id", st.session_state.user.id)
            .maybe_single()
            .execute()
        )

        student = result.data

        if student:

            st.subheader(student.get("name", "Student"))

            c1, c2, c3 = st.columns(3)

            with c1:
                st.write("Class")
                st.write(student.get("class_name", "-"))

            with c2:
                st.write("Section")
                st.write(student.get("section", "-"))

            with c3:
                st.write("Roll No.")
                st.write(student.get("roll_no", "-"))

        else:
            st.info(
                "Your student record has not been linked to your User ID yet."
            )

    except Exception as e:
        st.error("Could not load student information.")
        st.code(str(e))


# =========================================================
# PARENT DASHBOARD
# =========================================================
def parent_dashboard():

    profile = st.session_state.profile

    st.title("👨‍👩‍👧 Parent Dashboard")

    st.write(
        f"Welcome, **{profile.get('full_name') or profile.get('email')}**"
    )

    st.info("Parent modules will be added next.")


# =========================================================
# MAIN
# =========================================================
if not st.session_state.logged_in:

    login()

else:

    profile = st.session_state.profile
    role = profile.get("role")

    # -----------------------------------------------------
    # TOP BAR
    # -----------------------------------------------------
    col1, col2 = st.columns([5, 1])

    with col1:
        st.caption(
            f"Role: {role} | "
            f"{profile.get('email', '')}"
        )

    with col2:
        if st.button(
            "Logout",
            use_container_width=True
        ):
            logout()

    # -----------------------------------------------------
    # ROLE ROUTING
    # -----------------------------------------------------
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
        st.error(
            f"Unknown user role: {role}"
        )
