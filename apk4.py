import streamlit as st
import requests
from supabase import create_client

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

for x in [
    "logged_in",
    "user",
    "profile",
    "access_token",
    "refresh_token"
]:
    if x not in st.session_state:
        st.session_state[x] = None if x != "logged_in" else False


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

    st.session_state.user = None
    st.session_state.profile = None
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    st.session_state.logged_in = False

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

            r = sb.auth.sign_in_with_password({
                "email": email.strip(),
                "password": password
            })

            if not r.user or not r.session:
                st.error("Login failed.")
                return

            st.session_state.user = r.user

            st.session_state.access_token = (
                r.session.access_token
            )

            st.session_state.refresh_token = (
                r.session.refresh_token
            )

            sb.postgrest.auth(
                r.session.access_token
            )

            p = (
                sb.table("profiles")
                .select("*")
                .eq("id", r.user.id)
                .single()
                .execute()
                .data
            )

            if not p:
                st.error("Profile not found.")
                return

            if p.get("active") is False:

                st.error(
                    "Your account is inactive."
                )

                sb.auth.sign_out()

                return

            st.session_state.profile = p
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

        data = (
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

                old = (
                    sb.table("schools")
                    .select("id")
                    .eq(
                        "code",
                        code.strip()
                    )
                    .execute()
                    .data
                )

                if old:

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
                    "School added."
                )

                st.rerun()

            except Exception as e:

                st.error(
                    "Could not add school."
                )

                st.code(str(e))

    st.divider()

    for s in data:

        sid = s["id"]
        active = s.get(
            "active",
            True
        )

        with st.container(
            border=True
        ):

            c1, c2, c3 = st.columns(
                [3, 2, 1]
            )

            with c1:

                st.markdown(
                    f"### 🏫 {s.get('name','')}"
                )

                st.caption(
                    f"Code: {s.get('code','')}"
                )

                st.caption(
                    s.get("address")
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
                    key=f"sch_{sid}"
                ):

                    try:

                        (
                            sb.table("schools")
                            .update({
                                "active": not active
                            })
                            .eq(
                                "id",
                                sid
                            )
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(str(e))

            with st.expander(
                "✏️ Edit"
            ):

                n = st.text_input(
                    "Name",
                    s.get("name", ""),
                    key=f"n{sid}"
                )

                c = st.text_input(
                    "Code",
                    s.get("code", ""),
                    key=f"c{sid}"
                )

                a = st.text_area(
                    "Address",
                    s.get("address", ""),
                    key=f"a{sid}"
                )

                if st.button(
                    "Save",
                    key=f"save{sid}"
                ):

                    try:

                        duplicate = (
                            sb.table("schools")
                            .select("id")
                            .eq(
                                "code",
                                c.strip()
                            )
                            .neq(
                                "id",
                                sid
                            )
                            .execute()
                            .data
                        )

                        if duplicate:

                            st.error(
                                "School code already exists."
                            )

                            continue

                        (
                            sb.table("schools")
                            .update({
                                "name": n.strip(),
                                "code": c.strip(),
                                "address": a.strip()
                            })
                            .eq(
                                "id",
                                sid
                            )
                            .execute()
                        )

                        st.success(
                            "Updated."
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

        st.error(str(e))
        return

    active_schools = [
        x for x in schools_data
        if x.get("active", True)
    ]

    if not active_schools:

        st.warning(
            "Create an active school first."
        )

        return

    smap = {
        f"{x['name']} ({x['code']})":
            x["id"]
        for x in active_schools
    }

    with st.expander(
        "➕ Create User",
        expanded=True
    ):

        school = st.selectbox(
            "School",
            list(smap)
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

            if not all([
                name.strip(),
                email.strip(),
                password
            ]):

                st.warning(
                    "Fill all fields."
                )

                return

            if len(password) < 6:

                st.warning(
                    "Password must be at least 6 characters."
                )

                return

            token = (
                st.session_state.access_token
            )

            if not token:

                st.error(
                    "Session expired. Logout and login again."
                )

                return

            try:

                r = requests.post(
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
                            smap[school]
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

                if 200 <= r.status_code < 300:

                    st.success(
                        "User created successfully."
                    )

                    st.rerun()

                else:

                    st.error(
                        f"Create-User failed: HTTP {r.status_code}"
                    )

                    st.code(r.text)

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

        us = (
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
        for x in schools_data
    }

    for u in us:

        uid = u["id"]

        active = u.get(
            "active",
            True
        )

        with st.container(
            border=True
        ):

            c1, c2, c3 = st.columns(
                [3, 2, 1]
            )

            with c1:

                st.write(
                    u.get(
                        "full_name"
                    )
                    or u.get("email")
                )

                st.caption(
                    u.get("email")
                )

            with c2:

                st.write(
                    f"Role: **{u.get('role')}**"
                )

                st.caption(
                    school_names.get(
                        str(
                            u.get("school_id")
                        ),
                        "No school"
                    )
                )

            with c3:

                if st.button(
                    "Deactivate"
                    if active
                    else "Activate",
                    key=f"usr{uid}"
                ):

                    try:

                        (
                            sb.table("profiles")
                            .update({
                                "active":
                                    not active
                            })
                            .eq(
                                "id",
                                uid
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
    # LOAD SCHOOLS FOR SUPERADMIN
    # -----------------------------------------------------

    if role == "SuperAdmin":

        try:

            school_list = (
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
            x for x in school_list
            if x.get("active", True)
        ]

        if not active_schools:

            st.warning(
                "Create an active school first."
            )

            return

        school_options = {
            f"{x['name']} ({x['code']})":
                x["id"]
            for x in active_schools
        }

        selected_school = st.selectbox(
            "🏫 Select School",
            list(school_options),
            key="student_school"
        )

        school_id = school_options[
            selected_school
        ]

    else:

        if not school_id:

            st.error(
                "Your account is not assigned to a school."
            )

            return

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

    st.divider()

    # -----------------------------------------------------
    # ADD STUDENT
    # -----------------------------------------------------

    with st.expander(
        "➕ Add New Student",
        expanded=False
    ):

        name = st.text_input(
            "Student Name",
            key="add_student_name"
        )

        class_name = st.text_input(
            "Class",
            key="add_student_class",
            placeholder="Example: 6"
        )

        section = st.text_input(
            "Section",
            key="add_student_section",
            placeholder="Example: A"
        )

        roll_no = st.text_input(
            "Roll No.",
            key="add_student_roll"
        )

        dob = st.date_input(
            "Date of Birth",
            value=None,
            key="add_student_dob"
        )

        admission_no = st.text_input(
            "Admission No.",
            key="add_student_admission"
        )

        parent_name = st.text_input(
            "Parent Name",
            key="add_student_parent"
        )

        # Find student accounts
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
            "Not linked":
                None
        }

        for u in student_users:

            label = (
                f"{u.get('full_name') or 'Student'} "
                f"— {u.get('email')}"
            )

            user_options[label] = u["id"]

        selected_user = st.selectbox(
            "🔗 Student Login Account",
            list(user_options),
            key="add_student_user"
        )

        if st.button(
            "➕ Add Student",
            use_container_width=True
        ):

            if not name.strip():

                st.warning(
                    "Student name is required."
                )

                return

            try:

                payload = {
                    "school_id":
                        school_id,

                    "name":
                        name.strip(),

                    "class_name":
                        class_name.strip(),

                    "section":
                        section.strip(),

                    "roll_no":
                        roll_no.strip(),

                    "date_of_birth":
                        str(dob)
                        if dob
                        else None,

                    "dob":
                        str(dob)
                        if dob
                        else None,

                    "admission_no":
                        admission_no.strip(),

                    "parent_name":
                        parent_name.strip(),

                    "user_id":
                        user_options[
                            selected_user
                        ]
                }

                (
                    sb.table("students")
                    .insert(payload)
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
            .select("*")
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
        "🔍 Search student",
        placeholder="Name, roll no. or admission no."
    )

    if search.strip():

        q = search.strip().lower()

        student_data = [
            s for s in student_data
            if q in str(
                s.get("name", "")
            ).lower()
            or q in str(
                s.get("roll_no", "")
            ).lower()
            or q in str(
                s.get("admission_no", "")
            ).lower()
        ]

    st.caption(
        f"Showing {len(student_data)} student(s)"
    )

    # -----------------------------------------------------
    # STUDENT RECORDS
    # -----------------------------------------------------

    for s in student_data:

        sid = s["id"]

        with st.container(
            border=True
        ):

            c1, c2, c3 = st.columns(
                [4, 3, 1]
            )

            with c1:

                st.markdown(
                    f"### 🎓 {s.get('name','')}"
                )

                st.caption(
                    f"Class: "
                    f"{s.get('class_name') or '-'} "
                    f"| Section: "
                    f"{s.get('section') or '-'} "
                    f"| Roll: "
                    f"{s.get('roll_no') or '-'}"
                )

            with c2:

                st.write(
                    f"Admission No.: "
                    f"**{s.get('admission_no') or '-'}**"
                )

                st.write(
                    f"Parent: "
                    f"**{s.get('parent_name') or '-'}**"
                )

            with c3:

                if st.button(
                    "🗑️ Delete",
                    key=f"delete_student_{sid}"
                ):

                    try:

                        (
                            sb.table("students")
                            .delete()
                            .eq(
                                "id",
                                sid
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
            # EDIT
            # -------------------------------------------------

            with st.expander(
                "✏️ Modify Student"
            ):

                ename = st.text_input(
                    "Student Name",
                    s.get("name") or "",
                    key=f"ename_{sid}"
                )

                eclass = st.text_input(
                    "Class",
                    s.get("class_name") or "",
                    key=f"eclass_{sid}"
                )

                esection = st.text_input(
                    "Section",
                    s.get("section") or "",
                    key=f"esection_{sid}"
                )

                eroll = st.text_input(
                    "Roll No.",
                    s.get("roll_no") or "",
                    key=f"eroll_{sid}"
                )

                edob_value = (
                    s.get("date_of_birth")
                    or s.get("dob")
                )

                import datetime

                try:

                    if edob_value:

                        edob = datetime.date.fromisoformat(
                            str(edob_value)[:10]
                        )

                    else:

                        edob = datetime.date(
                            2010,
                            1,
                            1
                        )

                except Exception:

                    edob = datetime.date(
                        2010,
                        1,
                        1
                    )

                edob = st.date_input(
                    "Date of Birth",
                    value=edob,
                    key=f"edob_{sid}"
                )

                eadmission = st.text_input(
                    "Admission No.",
                    s.get("admission_no") or "",
                    key=f"eadmission_{sid}"
                )

                eparent = st.text_input(
                    "Parent Name",
                    s.get("parent_name") or "",
                    key=f"eparent_{sid}"
                )

                # Existing user
                try:

                    existing_users = (
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

                    existing_users = []

                edit_user_options = {
                    "Not linked":
                        None
                }

                current_uid = s.get(
                    "user_id"
                )

                current_label = "Not linked"

                for u in existing_users:

                    label = (
                        f"{u.get('full_name') or 'Student'} "
                        f"— {u.get('email')}"
                    )

                    edit_user_options[
                        label
                    ] = u["id"]

                    if (
                        str(u["id"])
                        == str(current_uid)
                    ):

                        current_label = label

                if (
                    current_label
                    not in edit_user_options
                ):

                    current_label = "Not linked"

                selected_edit_user = st.selectbox(
                    "🔗 Student Login Account",
                    list(edit_user_options),
                    index=list(
                        edit_user_options
                    ).index(
                        current_label
                    ),
                    key=f"edit_user_{sid}"
                )

                if st.button(
                    "💾 Save Changes",
                    key=f"save_student_{sid}",
                    use_container_width=True
                ):

                    try:

                        update_data = {
                            "name":
                                ename.strip(),

                            "class_name":
                                eclass.strip(),

                            "section":
                                esection.strip(),

                            "roll_no":
                                eroll.strip(),

                            "date_of_birth":
                                str(edob),

                            "dob":
                                str(edob),

                            "admission_no":
                                eadmission.strip(),

                            "parent_name":
                                eparent.strip(),

                            "user_id":
                                edit_user_options[
                                    selected_edit_user
                                ]
                        }

                        (
                            sb.table("students")
                            .update(update_data)
                            .eq(
                                "id",
                                sid
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

    p = st.session_state.profile

    role = p.get("role")

    top1, top2 = st.columns(
        [5, 1]
    )

    with top1:

        st.caption(
            f"Role: {role} | "
            f"{p.get('email','')}"
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

            schools_count = (
                sb.table("schools")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
                .count
                or 0
            )

            users_count = (
                sb.table("profiles")
                .select(
                    "id",
                    count="exact"
                )
                .execute()
                .count
                or 0
            )

            students_count = (
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

            schools_count = 0
            users_count = 0
            students_count = 0

        a, b, c = st.columns(3)

        a.metric(
            "🏫 Schools",
            schools_count
        )

        b.metric(
            "👥 Users",
            users_count
        )

        c.metric(
            "🎓 Students",
            students_count
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

            s = (
                sb.table("students")
                .select("*")
                .eq(
                    "user_id",
                    st.session_state.user.id
                )
                .maybe_single()
                .execute()
                .data
            )

            if s:

                st.subheader(
                    s.get(
                        "name",
                        "Student"
                    )
                )

                a, b, c = st.columns(3)

                a.metric(
                    "Class",
                    s.get(
                        "class_name",
                        "-"
                    )
                )

                b.metric(
                    "Section",
                    s.get(
                        "section",
                        "-"
                    )
                )

                c.metric(
                    "Roll No.",
                    s.get(
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
# RUN
# =========================================================

if st.session_state.logged_in:

    dashboard()

else:

    login()
