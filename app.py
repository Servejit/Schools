import streamlit as st
import requests
import datetime
from supabase import create_client

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

sb = create_client(URL, KEY)

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
            False if key == "logged_in"
            else None
        )

# Restore Supabase session
if (
    st.session_state.access_token
    and st.session_state.refresh_token
):
    try:
        sb.auth.set_session(
            st.session_state.access_token,
            st.session_state.refresh_token
        )

        sb.postgrest.auth(
            st.session_state.access_token
        )

    except Exception:
        pass


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

                st.error(
                    "Your account is inactive."
                )

                sb.auth.sign_out()

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
            .order(
                "created_at",
                desc=True
            )
            .execute()
            .data
            or []
        )

    except Exception as e:

        st.error("Could not load schools.")
        st.code(str(e))
        return

    # -----------------------------------------------------
    # ADD SCHOOL
    # -----------------------------------------------------

    with st.expander(
        "➕ Add New School"
    ):

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
                    .eq(
                        "code",
                        code.strip()
                    )
                    .execute()
                    .data
                    or []
                )

                if existing:

                    st.error(
                        "School code already exists."
                    )

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

                st.success(
                    "School added successfully."
                )

                st.rerun()

            except Exception as e:

                st.error(
                    "Could not add school."
                )

                st.code(str(e))

    st.divider()

    # -----------------------------------------------------
    # EXISTING SCHOOLS
    # -----------------------------------------------------

    for school in school_data:

        school_id = school["id"]

        active = school.get(
            "active",
            True
        )

        with st.container(border=True):

            c1, c2, c3 = st.columns(
                [3, 2, 1]
            )

            with c1:

                st.markdown(
                    f"### 🏫 {school.get('name', '')}"
                )

                st.caption(
                    f"Code: {school.get('code', '')}"
                )

                st.caption(
                    school.get("address")
                    or "No address"
                )

            with c2:

                if active:
                    st.success("ACTIVE")
                else:
                    st.error("INACTIVE")

            with c3:

                if st.button(
                    "Deactivate"
                    if active
                    else "Activate",
                    key=f"school_status_{school_id}"
                ):

                    try:

                        (
                            sb.table("schools")
                            .update({
                                "active": not active
                            })
                            .eq(
                                "id",
                                school_id
                            )
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(str(e))

            # -------------------------------------------------
            # EDIT SCHOOL
            # -------------------------------------------------

            with st.expander(
                "✏️ Edit"
            ):

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

                if st.button(
                    "Save",
                    key=f"school_save_{school_id}"
                ):

                    try:

                        duplicate = (
                            sb.table("schools")
                            .select("id")
                            .eq(
                                "code",
                                edit_code.strip()
                            )
                            .neq(
                                "id",
                                school_id
                            )
                            .execute()
                            .data
                            or []
                        )

                        if duplicate:

                            st.error(
                                "School code already exists."
                            )

                            continue

                        (
                            sb.table("schools")
                            .update({
                                "name":
                                    edit_name.strip(),

                                "code":
                                    edit_code.strip(),

                                "address":
                                    edit_address.strip()
                            })
                            .eq(
                                "id",
                                school_id
                            )
                            .execute()
                        )

                        st.success(
                            "School updated."
                        )

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
            .select(
                "id,name,code,active"
            )
            .order("name")
            .execute()
            .data
            or []
        )

    except Exception as e:

        st.error(str(e))
        return

    active_schools = [
        x for x in school_data
        if x.get("active", True)
    ]

    if not active_schools:

        st.warning(
            "Create an active school first."
        )

        return

    school_map = {
        f"{x['name']} ({x['code']})":
            x["id"]
        for x in active_schools
    }

    # -----------------------------------------------------
    # CREATE USER
    # -----------------------------------------------------

    with st.expander(
        "➕ Create User",
        expanded=True
    ):

        selected_school = st.selectbox(
            "School",
            list(school_map.keys())
        )

        name = st.text_input(
            "Full Name"
        )

        email = st.text_input(
            "Email"
        )

        password = st.text_input(
            "Password",
            type="password"
        )

        role = st.selectbox(
            "Role",
            [
                "Admin",
                "Teacher",
                "Student",
                "Parent"
            ]
        )

        if st.button(
            "👤 Create User",
            use_container_width=True
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
                st.warning(
                    "Password must be at least 6 characters."
                )
                return

            token = st.session_state.access_token

            if not token:

                st.error(
                    "Session expired. Logout and login again."
                )

                return

            try:

                response = requests.post(
                    CREATE_USER,
                    json={
                        "email":
                            email.strip(),

                        "password":
                            password,

                        "full_name":
                            name.strip(),

                        "role":
                            role,

                        "school_id":
                            school_map[
                                selected_school
                            ]
                    },
                    headers={
                        "Authorization":
                            f"Bearer {token}",

                        "apikey":
                            KEY,

                        "Content-Type":
                            "application/json"
                    },
                    timeout=30
                )

                if 200 <= response.status_code < 300:

                    st.success(
                        "User created successfully."
                    )

                    st.rerun()

                else:

                    st.error(
                        f"Create-User failed: "
                        f"HTTP {response.status_code}"
                    )

                    st.code(response.text)

            except Exception as e:

                st.error(
                    "Could not connect to Create-User."
                )

                st.code(str(e))

    st.divider()

    st.subheader(
        "📋 Existing Users"
    )

    try:

        user_data = (
            sb.table("profiles")
            .select(
                "id,email,full_name,role,active,school_id"
            )
            .order(
                "created_at",
                desc=True
            )
            .execute()
            .data
            or []
        )

    except Exception as e:

        st.error(str(e))
        return

    school_names = {
        str(x["id"]):
            x["name"]
        for x in school_data
    }

    for user in user_data:

        user_id = user["id"]

        active = user.get(
            "active",
            True
        )

        with st.container(border=True):

            c1, c2, c3 = st.columns(
                [3, 2, 1]
            )

            with c1:

                st.write(
                    user.get(
                        "full_name"
                    )
                    or user.get("email")
                )

                st.caption(
                    user.get("email")
                )

            with c2:

                st.write(
                    f"Role: **{user.get('role')}**"
                )

                st.caption(
                    school_names.get(
                        str(
                            user.get("school_id")
                        ),
                        "No school"
                    )
                )

            with c3:

                if st.button(
                    "Deactivate"
                    if active
                    else "Activate",
                    key=f"user_status_{user_id}"
                ):

                    try:

                        (
                            sb.table("profiles")
                            .update({
                                "active": not active
                            })
                            .eq(
                                "id",
                                user_id
                            )
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(str(e))


# =========================================================
# STUDENT MANAGEMENT
# =========================================================

def students():

    st.header("🎓 Student Management")

    profile = st.session_state.profile
    role = profile.get("role")

    school_id = profile.get(
        "school_id"
    )

    # -----------------------------------------------------
    # SCHOOL SELECTION
    # -----------------------------------------------------

    if role == "SuperAdmin":

        try:

            schools_data = (
                sb.table("schools")
                .select(
                    "id,name,code,active"
                )
                .order("name")
                .execute()
                .data
                or []
            )

        except Exception as e:

            st.error(
                "Could not load schools."
            )

            st.code(str(e))
            return

        active_schools = [
            s for s in schools_data
            if s.get("active", True)
        ]

        if not active_schools:

            st.warning(
                "Create an active school first."
            )

            return

        school_map = {
            f"{s['name']} ({s['code']})":
                s["id"]
            for s in active_schools
        }

        selected_school = st.selectbox(
            "🏫 Select School",
            list(school_map.keys()),
            key="student_selected_school"
        )

        school_id = school_map[
            selected_school
        ]

    else:

        if not school_id:

            st.error(
                "Your account is not assigned to a school."
            )

            return

        try:

            school_info = (
                sb.table("schools")
                .select("name,code")
                .eq(
                    "id",
                    school_id
                )
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

    st.divider()

    # -----------------------------------------------------
    # LOAD STUDENT LOGIN ACCOUNTS
    # -----------------------------------------------------

    try:

        student_users = (
            sb.table("profiles")
            .select(
                "id,email,full_name"
            )
            .eq(
                "role",
                "Student"
            )
            .eq(
                "school_id",
                school_id
            )
            .eq(
                "active",
                True
            )
            .order("full_name")
            .execute()
            .data
            or []
        )

    except Exception:

        student_users = []

    user_options = {
        "Not linked": None
    }

    for user in student_users:

        label = (
            f"{user.get('full_name') or 'Student'} "
            f"— {user.get('email')}"
        )

        user_options[label] = user["id"]

    # -----------------------------------------------------
    # ADD STUDENT
    # -----------------------------------------------------

    with st.expander(
        "➕ Add New Student",
        expanded=False
    ):

        name = st.text_input(
            "Student Name",
            key="student_add_name"
        )

        admission_no = st.text_input(
            "Admission No.",
            key="student_add_admission"
        )

        roll_no = st.text_input(
            "Roll No.",
            key="student_add_roll"
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
            value=datetime.date(
                2010,
                1,
                1
            ),
            key="student_add_date_of_birth"
        )

        gender = st.selectbox(
            "Gender",
            [
                "Male",
                "Female",
                "Other"
            ],
            key="student_add_gender"
        )

        parent_name = st.text_input(
            "Parent Name",
            key="student_add_parent_name"
        )

        parent_phone = st.text_input(
            "Parent Phone",
            key="student_add_parent_phone"
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

            if not name.strip():

                st.warning(
                    "Student name is required."
                )

            else:

                try:

                    student_record = {

                        "school_id":
                            school_id,

                        "user_id":
                            user_options[
                                selected_user
                            ],

                        "name":
                            name.strip(),

                        "admission_no":
                            admission_no.strip(),

                        "roll_no":
                            roll_no.strip(),

                        "class_name":
                            class_name.strip(),

                        "section":
                            section.strip(),

                        "date_of_birth":
                            str(date_of_birth),

                        "gender":
                            gender,

                        "parent_name":
                            parent_name.strip(),

                        "parent_phone":
                            parent_phone.strip(),

                        "active":
                            True
                    }

                    (
                        sb.table("students")
                        .insert(student_record)
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
                "id,"
                "school_id,"
                "user_id,"
                "name,"
                "admission_no,"
                "roll_no,"
                "class_name,"
                "section,"
                "date_of_birth,"
                "gender,"
                "parent_name,"
                "parent_phone,"
                "active,"
                "created_at,"
                "updated_at"
            )
            .eq(
                "school_id",
                school_id
            )
            .order("name")
            .execute()
            .data
            or []
        )

    except Exception as e:

        st.error(
            "Could not load students."
        )

        st.code(str(e))
        return

    st.subheader(
        f"📋 Students ({len(student_data)})"
    )

    if not student_data:

        st.info(
            "No students added yet."
        )

        return

    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    search = st.text_input(
        "🔍 Search Student",
        placeholder=(
            "Name, admission no. or roll no."
        ),
        key="student_search"
    )

    if search.strip():

        search_text = (
            search.strip().lower()
        )

        student_data = [
            student
            for student in student_data
            if search_text in str(
                student.get(
                    "name",
                    ""
                )
            ).lower()
            or search_text in str(
                student.get(
                    "admission_no",
                    ""
                )
            ).lower()
            or search_text in str(
                student.get(
                    "roll_no",
                    ""
                )
            ).lower()
        ]

    st.caption(
        f"Showing {len(student_data)} student(s)"
    )

    # -----------------------------------------------------
    # DISPLAY STUDENTS
    # -----------------------------------------------------

    for student in student_data:

        student_id = student["id"]

        with st.container(border=True):

            c1, c2, c3 = st.columns(
                [4, 3, 1]
            )

            with c1:

                st.markdown(
                    f"### 🎓 "
                    f"{student.get('name', '-')}"
                )

                st.caption(
                    f"Class: "
                    f"{student.get('class_name') or '-'} "
                    f"| Section: "
                    f"{student.get('section') or '-'} "
                    f"| Roll: "
                    f"{student.get('roll_no') or '-'}"
                )

                st.caption(
                    f"Gender: "
                    f"{student.get('gender') or '-'} "
                    f"| DOB: "
                    f"{student.get('date_of_birth') or '-'}"
                )

            with c2:

                st.write(
                    "Admission No.: "
                    f"**{student.get('admission_no') or '-'}**"
                )

                st.write(
                    "Parent: "
                    f"**{student.get('parent_name') or '-'}**"
                )

                st.write(
                    "Phone: "
                    f"**{student.get('parent_phone') or '-'}**"
                )

            with c3:

                if student.get(
                    "active",
                    True
                ):

                    st.success("ACTIVE")

                else:

                    st.error("INACTIVE")

                if st.button(
                    "🗑️ Delete",
                    key=f"delete_student_{student_id}"
                ):

                    try:

                        (
                            sb.table("students")
                            .delete()
                            .eq(
                                "id",
                                student_id
                            )
                            .execute()
                        )

                        st.success(
                            "Student deleted."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            "Delete failed."
                        )

                        st.code(str(e))

            # -------------------------------------------------
            # MODIFY STUDENT
            # -------------------------------------------------

            with st.expander(
                "✏️ Modify Student"
            ):

                edit_name = st.text_input(
                    "Student Name",
                    value=student.get(
                        "name"
                    ) or "",
                    key=f"edit_name_{student_id}"
                )

                edit_admission = st.text_input(
                    "Admission No.",
                    value=student.get(
                        "admission_no"
                    ) or "",
                    key=f"edit_admission_{student_id}"
                )

                edit_roll = st.text_input(
                    "Roll No.",
                    value=student.get(
                        "roll_no"
                    ) or "",
                    key=f"edit_roll_{student_id}"
                )

                edit_class = st.text_input(
                    "Class",
                    value=student.get(
                        "class_name"
                    ) or "",
                    key=f"edit_class_{student_id}"
                )

                edit_section = st.text_input(
                    "Section",
                    value=student.get(
                        "section"
                    ) or "",
                    key=f"edit_section_{student_id}"
                )

                # Existing DOB
                try:

                    existing_dob = (
                        datetime.date.fromisoformat(
                            str(
                                student.get(
                                    "date_of_birth"
                                )
                            )[:10]
                        )
                    )

                except Exception:

                    existing_dob = datetime.date(
                        2010,
                        1,
                        1
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

                existing_gender = student.get(
                    "gender"
                )

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

                edit_parent_name = st.text_input(
                    "Parent Name",
                    value=student.get(
                        "parent_name"
                    ) or "",
                    key=f"edit_parent_name_{student_id}"
                )

                edit_parent_phone = st.text_input(
                    "Parent Phone",
                    value=student.get(
                        "parent_phone"
                    ) or "",
                    key=f"edit_parent_phone_{student_id}"
                )

                edit_active = st.checkbox(
                    "Student Active",
                    value=student.get(
                        "active",
                        True
                    ),
                    key=f"edit_active_{student_id}"
                )

                # -------------------------------------------------
                # LOGIN ACCOUNT
                # -------------------------------------------------

                edit_user_options = {
                    "Not linked": None
                }

                current_user_id = student.get(
                    "user_id"
                )

                current_user_label = (
                    "Not linked"
                )

                for user in student_users:

                    label = (
                        f"{user.get('full_name') or 'Student'} "
                        f"— {user.get('email')}"
                    )

                    edit_user_options[
                        label
                    ] = user["id"]

                    if (
                        str(
                            user["id"]
                        )
                        ==
                        str(
                            current_user_id
                        )
                    ):

                        current_user_label = label

                user_labels = list(
                    edit_user_options.keys()
                )

                if (
                    current_user_label
                    not in user_labels
                ):

                    current_user_label = (
                        "Not linked"
                    )

                selected_edit_user = st.selectbox(
                    "🔗 Student Login Account",
                    user_labels,
                    index=user_labels.index(
                        current_user_label
                    ),
                    key=f"edit_user_{student_id}"
                )

                # -------------------------------------------------
                # SAVE
                # -------------------------------------------------

                if st.button(
                    "💾 Save Changes",
                    key=f"save_student_{student_id}",
                    use_container_width=True
                ):

                    try:

                        update_record = {

                            "user_id":
                                edit_user_options[
                                    selected_edit_user
                                ],

                            "name":
                                edit_name.strip(),

                            "admission_no":
                                edit_admission.strip(),

                            "roll_no":
                                edit_roll.strip(),

                            "class_name":
                                edit_class.strip(),

                            "section":
                                edit_section.strip(),

                            "date_of_birth":
                                str(
                                    edit_date_of_birth
                                ),

                            "gender":
                                edit_gender,

                            "parent_name":
                                edit_parent_name.strip(),

                            "parent_phone":
                                edit_parent_phone.strip(),

                            "active":
                                edit_active
                        }

                        (
                            sb.table("students")
                            .update(
                                update_record
                            )
                            .eq(
                                "id",
                                student_id
                            )
                            .execute()
                        )

                        st.success(
                            "Student updated successfully."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            "Could not update student."
                        )

                        st.code(str(e))


# =========================================================
# DASHBOARD
# =========================================================

def dashboard():

    profile = st.session_state.profile

    role = profile.get("role")

    # -----------------------------------------------------
    # TOP BAR
    # -----------------------------------------------------

    top1, top2 = st.columns(
        [5, 1]
    )

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

        st.title(
            "👑 SuperAdmin Dashboard"
        )

        try:

            school_count = (
                sb.table("schools")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
                .count
                or 0
            )

            user_count = (
                sb.table("profiles")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
                .count
                or 0
            )

            student_count = (
                sb.table("students")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
                .count
                or 0
            )

        except Exception:

            school_count = 0
            user_count = 0
            student_count = 0

        a, b, c = st.columns(3)

        a.metric(
            "🏫 Schools",
            school_count
        )

        b.metric(
            "👥 Users",
            user_count
        )

        c.metric(
            "🎓 Students",
            student_count
        )

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

        if menu == "🏫 Schools":

            schools()

        elif menu == "👥 Users":

            users()

        elif menu == "🎓 Students":

            students()

        else:

            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # ADMIN
    # =====================================================

    elif role == "Admin":

        st.title(
            "🛠️ Admin Dashboard"
        )

        menu = st.radio(
            "Management",
            [
                "🎓 Students",
                "📚 Classes & Subjects",
                "📝 Marks",
                "📅 Attendance",
                "🖨️ Print Templates",
                "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🎓 Students":

            students()

        else:

            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # TEACHER
    # =====================================================

    elif role == "Teacher":

        st.title(
            "👨‍🏫 Teacher Dashboard"
        )

        menu = st.radio(
            "Teacher Menu",
            [
                "🎓 Students",
                "📝 Marks",
                "📅 Attendance",
                "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🎓 Students":

            students()

        else:

            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # STUDENT
    # =====================================================

    elif role == "Student":

        st.title(
            "🎓 Student Dashboard"
        )

        try:

            student = (
                sb.table("students")
                .select(
                    "id,"
                    "school_id,"
                    "user_id,"
                    "name,"
                    "admission_no,"
                    "roll_no,"
                    "class_name,"
                    "section,"
                    "date_of_birth,"
                    "gender,"
                    "parent_name,"
                    "parent_phone,"
                    "active"
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
                    "Roll No.",
                    student.get(
                        "roll_no",
                        "-"
                    )
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

    # =====================================================
    # PARENT
    # =====================================================

    elif role == "Parent":

        st.title(
            "👨‍👩‍👧 Parent Dashboard"
        )

        st.info(
            "Parent modules will be added next."
        )

    else:

        st.error(
            f"Unknown role: {role}"
        )


# =========================================================
# START APP
# =========================================================

if st.session_state.logged_in:

    dashboard()

else:

    login()
