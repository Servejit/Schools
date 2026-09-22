import streamlit as st
import requests
import datetime
import pandas as pd
import uuid
import json
import io
import zipfile
import fitz

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
            False if key == "logged_in" else None
        )


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

                if st.button(
                    "Save",
                    key=f"school_save_{school_id}"
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

    active_schools = [
        x for x in school_data
        if x.get("active", True)
    ]

    if not active_schools:
        st.warning("Create an active school first.")
        return

    school_map = {
        f"{x['name']} ({x['code']})": x["id"]
        for x in active_schools
    }

    with st.expander(
        "➕ Create User",
        expanded=True
    ):

        selected_school = st.selectbox(
            "School",
            list(school_map.keys())
        )

        name = st.text_input("Full Name")
        email = st.text_input("Email")

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
                        "email": email.strip(),
                        "password": password,
                        "full_name": name.strip(),
                        "role": role,
                        "school_id": school_map[
                            selected_school
                        ]
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": KEY,
                        "Content-Type": "application/json"
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

    st.subheader("📋 Existing Users")

    try:

        user_data = (
            sb.table("profiles")
            .select(
                "id,email,full_name,role,active,school_id"
            )
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

    for user in user_data:

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

                st.write(
                    f"Role: **{user.get('role')}**"
                )

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

                        (
                            sb.table("profiles")
                            .update({
                                "active": not active
                            })
                            .eq("id", user_id)
                            .execute()
                        )

                        st.rerun()

                    except Exception as e:
                        st.error(str(e))


# =========================================================
# GET ACTIVE SCHOOL
# =========================================================

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
                "You can only see and change students in these classes."
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

        parent_phone = st.text_input(
            "Parent Phone",
            key="student_add_parent_phone"
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
                    "parent_phone": parent_phone.strip(),
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
                "parent_name,parent_phone,remarks,"
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

    st.caption(
        f"Showing {len(student_data)} student(s)"
    )

    for student in student_data:

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

                if st.button(
                    "🗑️ Delete",
                    key=f"delete_student_{student_id}"
                ):

                    if role == "Teacher" and (
                        str(student.get("class_name") or "").strip().lower(),
                        str(student.get("section") or "").strip().lower()
                    ) not in assigned_class_keys:
                        st.error("You can only change students assigned to your class.")
                        return

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

                edit_parent_phone = st.text_input(
                    "Parent Phone",
                    value=student.get("parent_phone") or "",
                    key=f"edit_parent_phone_{student_id}"
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

                if st.button(
                    "💾 Save Changes",
                    key=f"save_student_{student_id}",
                    use_container_width=True
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

                            "parent_phone":
                                edit_parent_phone.strip(),

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
# CLASSES & SUBJECTS
# =========================================================

def classes_subjects():

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

    with st.expander("👨‍🏫 Assign Class Teachers"):
        st.caption("Assign one class teacher to each class. Teachers will only see students from their assigned classes.")

        if not teacher_data:
            st.info("Create an active Teacher account first.")

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

    st.divider()

    st.caption(
        f"Total Classes: {len(class_data)}"
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

                if st.button(
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

                if st.button(
                    "💾 Save Class",
                    key=f"save_class_{class_id}"
                ):

                    try:

                        (
                            sb.table("classes")
                            .update({
                                "class_name":
                                    edit_class_name.strip(),
                                "section":
                                    edit_section.strip(),
                                "academic_year":
                                    edit_year.strip(),
                                "class_teacher_id":
                                    teacher_options[selected_teacher_label],
                                "updated_at":
                                    datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                            })
                            .eq("id", class_id)
                            .execute()
                        )

                        st.success("Class updated.")
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

                    if st.button(
                        "✏️ Edit",
                        key=f"edit_subject_button_{subject_id}"
                    ):

                        st.session_state[
                            f"editing_subject_{subject_id}"
                        ] = True

                        st.rerun()

                if st.session_state.get(
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

                            if st.button(
                                "💾 Save Subject",
                                key=f"save_subject_{subject_id}",
                                use_container_width=True
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

            if not subject_data:
                st.caption(
                    "No subjects added for this class."
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

    role = st.session_state.profile.get("role")

    if role not in [
        "SuperAdmin",
        "Admin",
        "Teacher"
    ]:

        st.error(
            "You do not have permission to enter marks."
        )
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

    selected_class = class_map[
        selected_class_label
    ]

    class_id = selected_class["id"]

    class_name = selected_class.get(
        "class_name"
    ) or ""

    section = selected_class.get(
        "section"
    ) or ""

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

        st.warning(
            "No active subjects found for this class."
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

        label = (
            f"{subject_name} (Max: {max_marks})"
        )

        subject_map[label] = subject

    selected_subject_label = st.selectbox(
        "📖 Select Subject",
        list(subject_map.keys()),
        key="marks_subject"
    )

    selected_subject = subject_map[
        selected_subject_label
    ]

    subject_id = selected_subject["id"]

    subject_name = (
        selected_subject.get("subject_name")
        or selected_subject.get("name")
        or "Subject"
    )

    max_marks = float(
        selected_subject.get("max_marks") or 100
    )

    passing_marks = float(
        selected_subject.get("passing_marks") or 0
    )

    st.caption(
        f"Maximum Marks: **{max_marks:g}** "
        f"| Passing Marks: **{passing_marks:g}**"
    )

    exam_name = st.text_input(
        "📝 Exam / Assessment Name",
        placeholder="Example: Half Yearly, Annual",
        key="marks_exam_name"
    ).strip()

    if not exam_name:

        st.info(
            "Enter the Exam / Assessment name."
        )
        return

    try:

        student_data = (
            sb.table("students")
            .select(
                "id,name,admission_no,"
                "class_name,section,active"
            )
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

    students_for_class = [
        student
        for student in student_data
        if (
            str(student.get("class_name") or "").strip().lower()
            ==
            str(class_name).strip().lower()
            and
            str(student.get("section") or "").strip().lower()
            ==
            str(section).strip().lower()
        )
    ]

    if not students_for_class:

        st.warning(
            f"No active students found for "
            f"{class_name} / Section {section}."
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
            "Student ID":
                student_id,

            "Student Name":
                student.get("name") or "",

            "Admission No.":
                student.get("admission_no") or "",

            "Marks":
                existing.get("marks")
                if existing else None
        })

    marks_df = pd.DataFrame(editor_rows)

    st.markdown(
        f"### 📝 {subject_name} — {exam_name}"
    )

    st.caption(
        f"{len(students_for_class)} students | "
        f"Maximum {max_marks:g} marks"
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
            "Marks":
                st.column_config.NumberColumn(
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

    if st.button(
        "💾 Save All Marks",
        type="primary",
        use_container_width=True
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
                    deletes.append(existing["id"])

                continue

            try:
                mark_value = float(value)
            except Exception:

                errors.append(
                    f"{row['Student Name']}: Invalid marks."
                )

                continue

            if mark_value < 0:

                errors.append(
                    f"{row['Student Name']}: "
                    "Marks cannot be negative."
                )

                continue

            if mark_value > max_marks:

                errors.append(
                    f"{row['Student Name']}: "
                    f"{mark_value:g} exceeds "
                    f"maximum {max_marks:g}."
                )

                continue

            if existing:

                updates.append({
                    "id": existing["id"],
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
                    "max_marks": max_marks,                    "class_id": class_id
                })

        if errors:
            st.error(
                "Please correct these errors:"
            )
            for error in errors:
                st.error(error)

            return

        try:

            if records_to_insert:

                (
                    sb.table("marks")
                    .insert(records_to_insert)
                    .execute()
                )

            for record in updates:

                (
                    sb.table("marks")
                    .update({
                        "marks": record["marks"],
                        "max_marks": record["max_marks"],
                        "class_id": record["class_id"]
                    })
                    .eq("id", record["id"])
                    .execute()
                )

            for mark_id in deletes:

                (
                    sb.table("marks")
                    .delete()
                    .eq("id", mark_id)
                    .execute()
                )

            st.success(
                "✅ All marks saved successfully."
            )

            st.rerun()

        except Exception as e:

            st.error("Could not save marks.")
            st.code(str(e))


# =========================================================
# A4 PRINT TEMPLATES
# =========================================================

def print_templates():

    st.header("🖨️ A4 Print Templates")

    role = st.session_state.profile.get("role")

    if role not in [
        "SuperAdmin",
        "Admin",
        "Teacher"
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

        if st.button(
            "⬆️ Upload & Save Template",
            type="primary",
            use_container_width=True,
            key="upload_template_button"
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

                st.success(
                    "✅ A4 template uploaded successfully."
                )

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

    if role not in ["SuperAdmin", "Admin", "Teacher"]:
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

    class_options = ["All Classes"] + sorted({
        str(x.get("class_name") or "")
        for x in students_data
        if str(x.get("class_name") or "")
    })

    selected_class = st.selectbox(
        "Class",
        class_options,
        key="attendance_class"
    )

    if selected_class != "All Classes":
        students_data = [
            x for x in students_data
            if str(x.get("class_name") or "") == selected_class
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

    if st.button(
        "💾 Save Attendance",
        type="primary",
        use_container_width=True,
        key="save_attendance_button"
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
            mark_display = f"{mark_number:g}"
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
            f"{max_number:g}"
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
        f"Total Marks: {total_marks:g} / {total_max:g}"
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
# REPORT CARD GENERATOR
# =========================================================

def report_cards():

    st.header("📄 Report Card Generator")

    role = st.session_state.profile.get("role")

    if role not in [
        "SuperAdmin",
        "Admin",
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

    selected_template_label = st.selectbox(
        "🖨️ Select Active Report Card Template",
        list(template_map.keys()),
        key="report_template_select"
    )

    selected_template = template_map[
        selected_template_label
    ]

    current_logo_path = school_logo_from_template(
        selected_template
    )

    logo_size = school_logo_size_from_template(
        selected_template
    )

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

            if st.button(
                "💾 Save Logo Size",
                use_container_width=True,
                key=f"save_report_school_logo_size_{selected_template['id']}"
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

        if uploaded_logo and st.button(
            replace_label,
            use_container_width=True,
            type="primary",
            key="save_report_school_logo"
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

    st.success(
        f"Active template: "
        f"{selected_template.get('template_name') or selected_template.get('name')}"
    )

    st.caption(
        "The template is used as the A4 background. "
        "Student information and marks are placed over it."
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

    if not student_data:

        st.warning(
            "No active students found."
        )

        return

    # -----------------------------------------------------
    # EXAMS    # -----------------------------------------------------

    try:

        marks_exam_rows = (
            sb.table("marks")
            .select("exam_name")
            .eq("school_id", school_id)            .execute()
            .data or []
        )

    except Exception as e:

        st.error(
            "Could not load exams."
        )

        st.code(str(e))
        return

    exam_names = sorted({
        str(x.get("exam_name"))
        for x in marks_exam_rows
        if x.get("exam_name")
    })

    if not exam_names:

        st.warning(
            "No marks/exams found. Enter marks first."
        )

        return

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
# DASHBOARD# =========================================================

def dashboard():

    profile = st.session_state.profile
    role = profile.get("role")

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
                "🎓 Students",                "📚 Classes & Subjects",
                "📝 Marks",
                "📅 Attendance",
                "🖨️ Print Templates",
                "📄 Report Cards",
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

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "🖨️ Print Templates":
            print_templates()

        elif menu == "📄 Report Cards":
            report_cards()

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # ADMIN
    # =====================================================

    elif role == "Admin":

        st.title("🛠️ Admin Dashboard")

        menu = st.radio(
            "Management",
            [
                "🎓 Students",
                "📝 Marks",
                "📅 Attendance",
                "🖨️ Print Templates",
                "📄 Report Cards",
                "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🎓 Students":
            students()

        elif menu == "📚 Classes & Subjects":
            classes_subjects()

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "🖨️ Print Templates":
            print_templates()

        elif menu == "📄 Report Cards":
            report_cards()

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # TEACHER
    # =====================================================

    elif role == "Teacher":

        st.title("👨‍🏫 Teacher Dashboard")

        menu = st.radio(
            "Teacher Menu",
            [
                "🎓 Students",
                "📚 Classes & Subjects",
                "📝 Marks",
                "📅 Attendance",
                "🖨️ Print Templates",
                "📄 Report Cards",
                "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🎓 Students":
            students()

        elif menu == "📚 Classes & Subjects":
            classes_subjects()

        elif menu == "📝 Marks":
            bulk_marks()

        elif menu == "📅 Attendance":
            attendance()

        elif menu == "🖨️ Print Templates":
            print_templates()

        elif menu == "📄 Report Cards":
            report_cards()

        else:
            st.info(
                f"{menu} will be added next."
            )

    # =====================================================
    # STUDENT
    # =====================================================

    elif role == "Student":

        st.title("🎓 Student Dashboard")

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

    # =====================================================
    # PARENT
    # =====================================================

    elif role == "Parent":

        st.title("👨‍👩‍👧 Parent Dashboard")

        st.info(
            "Parent modules will be added next."
        )

    else:

        st.error(
            f"Unknown role: {role}"
        )


# =========================================================
# START
# =========================================================

if st.session_state.logged_in:

    dashboard()

else:

    login()