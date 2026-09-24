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

        student_users_query = (
            sb.table("profiles")
            .select("id,email,full_name")
            .eq("role", "Student")
            .eq("school_id", school_id)
            .eq("active", True)
        )

        student_users = (
            student_users_query
            .order("full_name")
            .execute()
            .data or []
        )

    except Exception:

        student_users = []

    # Class Teachers may link Student login accounts only for students
    # belonging to their assigned Class Teacher class(es). Admin roles retain
    # school-wide access. Subject-only teachers do not get this control.
    if role == "Teacher" and assigned_class_keys:
        try:
            existing_students_for_teacher = (
                sb.table("students")
                .select("user_id,class_name,section")
                .eq("school_id", school_id)
                .eq("active", True)
                .execute()
                .data or []
            )
            allowed_student_user_ids = {
                str(row.get("user_id"))
                for row in existing_students_for_teacher
                if row.get("user_id") and (
                    str(row.get("class_name") or "").strip().lower(),
                    str(row.get("section") or "").strip().lower()
                ) in assigned_class_keys
            }
            # Keep unlinked accounts available only when they will be selected
            # from a student row in the Class Teacher's assigned class.
            # Existing linked accounts outside the assigned class are hidden.
            linked_outside_ids = {
                str(row.get("user_id"))
                for row in existing_students_for_teacher
                if row.get("user_id") and str(row.get("user_id")) not in allowed_student_user_ids
            }
            student_users = [
                user for user in student_users
                if str(user.get("id")) not in linked_outside_ids
            ]
        except Exception:
            pass

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
    # SuperAdmin, Admin and Admin+Teacher can add students school-wide.
    # A normal Teacher can add students ONLY when they are assigned as
    # the Class Teacher of that class. Subject-only Teachers cannot add.
    can_add_students = (
        role in ["SuperAdmin", "Admin", "Admin+Teacher"]
        or (role == "Teacher" and assigned_class_keys)
    )

    if can_add_students:
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
