import streamlit as st
import requests
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

CREATE_USER_URL = f"{SUPABASE_URL}/functions/v1/Create-User"


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

                button_text = "Deactivate" if active else "Activate"

                if st.button(
                    button_text,
                    key=f"status_{school_id}"
                ):

                    try:

                        (
                            supabase
                            .table("schools")
                            .update({
                                "active": not active
                            })
                            .eq("id", school_id)
                            .execute()
                        )

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
# USER MANAGEMENT
# =========================================================
def user_management():

    st.header("👥 User Management")

    profile = st.session_state.profile

    # -----------------------------------------------------
    # ONLY SUPERADMIN
    # -----------------------------------------------------
    if profile.get("role") != "SuperAdmin":
        st.error("Only SuperAdmin can manage users.")
        return

    # -----------------------------------------------------
    # LOAD SCHOOLS
    # -----------------------------------------------------
    try:

        school_result = (
            supabase
            .table("schools")
            .select("id,name,code,active")
            .order("name")
            .execute()
        )

        schools = school_result.data or []

    except Exception as e:
        st.error("Could not load schools.")
        st.code(str(e))
        return

    active_schools = [
        s for s in schools
        if s.get("active", True)
    ]

    if not active_schools:
        st.warning(
            "Please create an active school before creating users."
        )
        return

    # -----------------------------------------------------
    # CREATE USER
    # -----------------------------------------------------
    with st.expander("➕ Create New User", expanded=True):

        school_options = {
            f"{s.get('name')} ({s.get('code')})": s.get("id")
            for s in active_schools
        }

        selected_school_name = st.selectbox(
            "School",
            list(school_options.keys()),
            key="create_user_school"
        )

        selected_school_id = school_options[
            selected_school_name
        ]

        col1, col2 = st.columns(2)

        with col1:

            full_name = st.text_input(
                "Full Name",
                key="create_user_name"
            )

            email = st.text_input(
                "Email",
                key="create_user_email"
            )

        with col2:

            password = st.text_input(
                "Password",
                type="password",
                key="create_user_password"
            )

            role = st.selectbox(
                "Role",
                [
                    "Admin",
                    "Teacher",
                    "Student",
                    "Parent"
                ],
                key="create_user_role"
            )

        if st.button(
            "👤 Create User",
            type="primary",
            use_container_width=True
        ):

            if not full_name.strip():
                st.warning("Enter full name.")
                return

            if not email.strip():
                st.warning("Enter email.")
                return

            if not password:
                st.warning("Enter password.")
                return

            if len(password) < 6:
                st.warning(
                    "Password must be at least 6 characters."
                )
                return

            # -------------------------------------------------
            # GET CURRENT ACCESS TOKEN
            # -------------------------------------------------
            try:

                session = supabase.auth.get_session()

                if not session or not session.access_token:
                    st.error(
                        "Your login session has expired. Please login again."
                    )
                    return

                access_token = session.access_token

            except Exception as e:
                st.error("Could not obtain login session.")
                st.code(str(e))
                return

            # -------------------------------------------------
            # CALL CREATE-USER EDGE FUNCTION
            # -------------------------------------------------
            payload = {
                "email": email.strip(),
                "password": password,
                "full_name": full_name.strip(),
                "role": role,
                "school_id": selected_school_id
            }

            headers = {
                "Authorization": f"Bearer {access_token}",
                "apikey": SUPABASE_KEY,
                "Content-Type": "application/json"
            }

            try:

                response = requests.post(
                    CREATE_USER_URL,
                    json=payload,
                    headers=headers,
                    timeout=30
                )

                # ---------------------------------------------
                # SUCCESS
                # ---------------------------------------------
                if 200 <= response.status_code < 300:

                    try:
                        result = response.json()
                    except Exception:
                        result = {}

                    st.success(
                        f"User created successfully: {email.strip()}"
                    )

                    if result:
                        st.json(result)

                    # Clear form values
                    for key in [
                        "create_user_name",
                        "create_user_email",
                        "create_user_password"
                    ]:
                        if key in st.session_state:
                            del st.session_state[key]

                    st.rerun()

                # ---------------------------------------------
                # ERROR
                # ---------------------------------------------
                else:

                    try:
                        error_data = response.json()
                    except Exception:
                        error_data = response.text

                    st.error(
                        f"Create-User failed "
                        f"(HTTP {response.status_code})"
                    )

                    st.code(
                        str(error_data)
                    )

            except requests.exceptions.Timeout:

                st.error(
                    "Create-User request timed out."
                )

            except requests.exceptions.RequestException as e:

                st.error(
                    "Could not connect to Create-User."
                )

                st.code(str(e))

    st.divider()

    # =====================================================
    # EXISTING USERS
    # =====================================================
    st.subheader("📋 Existing Users")

    try:

        users_result = (
            supabase
            .table("profiles")
            .select(
                "id,email,full_name,role,active,school_id"
            )
            .order("created_at", desc=True)
            .execute()
        )

        users = users_result.data or []

    except Exception as e:
        st.error("Could not load users.")
        st.code(str(e))
        return

    if not users:
        st.info("No users found.")
        return

    # -----------------------------------------------------
    # SCHOOL NAME MAP
    # -----------------------------------------------------
    school_map = {
        str(s.get("id")): s.get("name", "")
        for s in schools
    }

    # -----------------------------------------------------
    # USER TABLE
    # -----------------------------------------------------
    for user in users:

        user_id = user.get("id")
        user_email = user.get("email", "")
        user_name = user.get("full_name") or ""
        user_role = user.get("role", "")
        user_active = user.get("active", True)
        user_school_id = user.get("school_id")

        school_name = school_map.get(
            str(user_school_id),
            "No school"
        )

        with st.container(border=True):

            c1, c2, c3, c4 = st.columns(
                [3, 2, 2, 1]
            )

            with c1:
                st.markdown(
                    f"**{user_name or user_email}**"
                )
                st.caption(user_email)

            with c2:
                st.write(f"Role: **{user_role}**")
                st.caption(school_name)

            with c3:
                if user_active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with c4:

                button_text = (
                    "Deactivate"
                    if user_active
                    else "Activate"
                )

                if st.button(
                    button_text,
                    key=f"user_status_{user_id}"
                ):

                    try:

                        (
                            supabase
                            .table("profiles")
                            .update({
                                "active": not user_active
                            })
                            .eq("id", user_id)
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:
                        st.error(
                            "Could not update user."
                        )
                        st.code(str(e))


# =========================================================
# SUPERADMIN DASHBOARD
# =========================================================
def superadmin_dashboard():

    profile = st.session_state.profile

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
        user_management()

    elif menu == "🎓 Students":
        st.info(
            "Student Management will be added next."
        )

    elif menu == "📚 Classes & Subjects":
        st.info(
            "Classes & Subjects will be added next."
        )

    elif menu == "📝 Marks":
        st.info(
            "Bulk Marks Entry will be added next."
        )

    elif menu == "📅 Attendance":
        st.info(
            "Bulk Attendance will be added next."
        )

    elif menu == "🖨️ Print Templates":
        st.info(
            "A4 Print Template Management will be added next."
        )

    elif menu == "📊 Reports":
        st.info(
            "Reports will be added next."
        )


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
            .eq(
                "user_id",
                st.session_state.user.id
            )
            .maybe_single()
            .execute()
        )

        student = result.data

        if student:

            st.subheader(
                student.get("name", "Student")
            )

            c1, c2, c3 = st.columns(3)

            with c1:
                st.write("Class")
                st.write(
                    student.get(
                        "class_name",
                        "-"
                    )
                )

            with c2:
                st.write("Section")
                st.write(
                    student.get(
                        "section",
                        "-"
                    )
                )

            with c3:
                st.write("Roll No.")
                st.write(
                    student.get(
                        "roll_no",
                        "-"
                    )
                )

        else:

            st.info(
                "Your student record has not been linked "
                "to your User ID yet."
            )

    except Exception as e:

        st.error(
            "Could not load student information."
        )

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
