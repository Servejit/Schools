import os
import io
import pandas as pd
import streamlit as st
from supabase import create_client, Client

st.set_page_config(
    page_title="Multi-School ERP",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_PUBLISHABLE_KEY", os.getenv("SUPABASE_PUBLISHABLE_KEY", ""))

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to Streamlit Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def q(table, select="*", **kwargs):
    r = supabase.table(table).select(select)
    for k, v in kwargs.items():
        r = r.eq(k, v)
    return r.execute().data or []

def get_profile(user_id):
    rows = q("profiles", "*", id=user_id)
    return rows[0] if rows else None

def current_user():
    try:
        s = supabase.auth.get_session()
        return s.user if s else None
    except Exception:
        return None

def sign_out():
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    for k in ["user", "profile"]:
        st.session_state.pop(k, None)
    st.rerun()

def login():
    st.title("🏫 Multi-School ERP")
    st.subheader("Sign in")

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        try:
            res = supabase.auth.sign_in_with_password(
                {"email": email.strip(), "password": password}
            )
            if not res.user:
                st.error("Login failed.")
                return
            profile = get_profile(res.user.id)
            if not profile:
                st.error("Profile not found. Ask the administrator to create/link your profile.")
                supabase.auth.sign_out()
                return
            if not profile.get("active", True):
                st.error("Your account is inactive.")
                supabase.auth.sign_out()
                return
            st.session_state.user = res.user
            st.session_state.profile = profile
            st.rerun()
        except Exception as e:
            st.error(f"Login error: {e}")

def school_options(profile):
    if profile["role"] == "SuperAdmin":
        return q("schools", "id,name,code", active=True)
    sid = profile.get("school_id")
    return q("schools", "id,name,code", id=sid, active=True) if sid else []

def bulk_upsert(table, rows, on_conflict=None):
    if not rows:
        return
    if on_conflict:
        supabase.table(table).upsert(rows, on_conflict=on_conflict).execute()
    else:
        supabase.table(table).insert(rows).execute()

def page_dashboard(profile, school):
    st.title("Dashboard")
    st.caption(f'{school["name"]} ({school["code"]})')
    students = q("students", "id", school_id=school["id"], active=True)
    teachers = q("profiles", "id", school_id=school["id"], role="Teacher", active=True)
    classes = q("classes", "id", school_id=school["id"], active=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Students", len(students))
    c2.metric("Teachers", len(teachers))
    c3.metric("Classes", len(classes))
    st.info("Use the sidebar to manage students, classes, subjects, teachers, marks, attendance and print templates.")

def page_schools():
    st.title("🏫 Schools")
    st.subheader("Add school")
    with st.form("new_school"):
        name = st.text_input("School name")
        code = st.text_input("School code")
        address = st.text_area("Address")
        ok = st.form_submit_button("Create school")
    if ok:
        try:
            supabase.table("schools").insert(
                {"name": name.strip(), "code": code.strip().upper(), "address": address}
            ).execute()
            st.success("School created.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    rows = q("schools", "id,name,code,address,active,created_at")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

def page_students(school):
    st.title("👨‍🎓 Students")
    tab1, tab2 = st.tabs(["Bulk import", "Edit / view"])

    with tab1:
        st.write("Upload Excel/CSV. Required: name. Optional: admission_no, roll_no, class_name, section, date_of_birth, gender, parent_name, parent_phone.")
        file = st.file_uploader("Student file", type=["xlsx", "xls", "csv"])
        if file:
            df = pd.read_csv(file) if file.name.lower().endswith(".csv") else pd.read_excel(file)
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
            st.dataframe(df.head(20), use_container_width=True)
            if "name" not in df.columns:
                st.error("The file must contain a 'name' column.")
            elif st.button("SAVE ALL STUDENTS", type="primary"):
                rows = []
                for _, r in df.iterrows():
                    name = str(r.get("name", "")).strip()
                    if not name or name.lower() == "nan":
                        continue
                    def clean(v):
                        if pd.isna(v):
                            return None
                        return str(v).strip()
                    rows.append({
                        "school_id": school["id"],
                        "name": name,
                        "admission_no": clean(r.get("admission_no")),
                        "roll_no": clean(r.get("roll_no")),
                        "class_name": clean(r.get("class_name")),
                        "section": clean(r.get("section")),
                        "date_of_birth": clean(r.get("date_of_birth")),
                        "gender": clean(r.get("gender")),
                        "parent_name": clean(r.get("parent_name")),
                        "parent_phone": clean(r.get("parent_phone")),
                        "active": True,
                    })
                try:
                    bulk_upsert("students", rows, "school_id,admission_no")
                    st.success(f"Saved {len(rows)} students.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    with tab2:
        rows = q("students", "*", school_id=school["id"], active=True)
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode()
            st.download_button("Download students CSV", csv, "students.csv", "text/csv")
        else:
            st.info("No students yet.")

def page_classes(school):
    st.title("🏷️ Classes & Sections")
    with st.form("class"):
        class_name = st.text_input("Class name", placeholder="8")
        section = st.text_input("Section", placeholder="A")
        year = st.text_input("Academic year", value="2026-27")
        ok = st.form_submit_button("Add class")
    if ok:
        try:
            supabase.table("classes").upsert(
                {"school_id": school["id"], "class_name": class_name.strip(), "section": section.strip(), "academic_year": year.strip()},
                on_conflict="school_id,class_name,section,academic_year"
            ).execute()
            st.success("Class saved.")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    rows = q("classes", "*", school_id=school["id"], active=True)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def page_subjects(school):
    st.title("📚 Subjects")
    with st.form("subject"):
        name = st.text_input("Subject name")
        code = st.text_input("Subject code")
        ok = st.form_submit_button("Add subject")
    if ok:
        try:
            supabase.table("subjects").upsert(
                {"school_id": school["id"], "name": name.strip(), "code": code.strip().upper()},
                on_conflict="school_id,code"
            ).execute()
            st.success("Subject saved.")
            st.rerun()
        except Exception as e:
            st.error(str(e))
    rows = q("subjects", "*", school_id=school["id"], active=True)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def page_teacher_assignment(school):
    st.title("👩‍🏫 Teacher / Subject Assignment")
    teachers = q("profiles", "id,full_name,email", school_id=school["id"], role="Teacher", active=True)
    classes = q("classes", "id,class_name,section,academic_year", school_id=school["id"], active=True)
    subjects = q("subjects", "id,name,code", school_id=school["id"], active=True)

    if not teachers:
        st.warning("Create Teacher profiles first.")
        return
    if not classes or not subjects:
        st.warning("Create classes and subjects first.")
        return

    teacher_map = {f'{x.get("full_name") or x.get("email")}': x["id"] for x in teachers}
    class_map = {f'{x["class_name"]}-{x["section"]} ({x["academic_year"]})': x["id"] for x in classes}
    subject_map = {f'{x["name"]} ({x["code"]})': x["id"] for x in subjects}

    with st.form("assignment"):
        teacher = st.selectbox("Teacher", list(teacher_map))
        cls = st.selectbox("Class", list(class_map))
        subs = st.multiselect("Subjects", list(subject_map))
        save = st.form_submit_button("ASSIGN SELECTED SUBJECTS", type="primary")

    if save and subs:
        rows = [{
            "school_id": school["id"],
            "teacher_id": teacher_map[teacher],
            "class_id": class_map[cls],
            "subject_id": subject_map[s],
        } for s in subs]
        try:
            supabase.table("teacher_subjects").upsert(
                rows, on_conflict="school_id,teacher_id,class_id,subject_id"
            ).execute()
            st.success(f"Assigned {len(rows)} subject(s) in one operation.")
        except Exception as e:
            st.error(str(e))

def page_marks(school):
    st.title("📝 Bulk Marks Entry")
    classes = q("classes", "id,class_name,section,academic_year", school_id=school["id"], active=True)
    subjects = q("subjects", "id,name,code", school_id=school["id"], active=True)
    if not classes or not subjects:
        st.warning("Create classes and subjects first.")
        return

    cm = {f'{x["class_name"]}-{x["section"]} ({x["academic_year"]})': x["id"] for x in classes}
    sm = {f'{x["name"]} ({x["code"]})': x["id"] for x in subjects}

    c1, c2 = st.columns(2)
    cls_name = c1.selectbox("Class", list(cm))
    sub_name = c2.selectbox("Subject", list(sm))
    exam = st.text_input("Exam", value="Annual")
    max_marks = st.number_input("Maximum marks", min_value=1.0, value=100.0)

    students = q("students", "id,name,roll_no,admission_no", school_id=school["id"], active=True, class_name=cls_name.split("-")[0])
    if not students:
        st.info("No students found for this class. Import/assign students first.")
        return

    base = pd.DataFrame([{
        "student_id": s["id"],
        "roll_no": s.get("roll_no") or "",
        "student_name": s["name"],
        "marks": ""
    } for s in students]).sort_values(["roll_no", "student_name"])

    edited = st.data_editor(
        base,
        use_container_width=True,
        hide_index=True,
        disabled=["student_id", "roll_no", "student_name"],
        column_config={"marks": st.column_config.NumberColumn("Marks", min_value=0, max_value=float(max_marks), step=0.5)},
        key="marks_editor"
    )

    if st.button("SAVE ALL MARKS", type="primary"):
        rows = []
        for _, r in edited.iterrows():
            if pd.isna(r["marks"]) or str(r["marks"]).strip() == "":
                continue
            rows.append({
                "school_id": school["id"],
                "student_id": r["student_id"],
                "subject_id": sm[sub_name],
                "exam_name": exam.strip(),
                "marks": float(r["marks"]),
                "max_marks": float(max_marks),
            })
        try:
            if rows:
                supabase.table("marks").upsert(
                    rows, on_conflict="school_id,student_id,subject_id,exam_name"
                ).execute()
            st.success(f"Saved {len(rows)} marks in one operation.")
        except Exception as e:
            st.error(str(e))

def page_attendance(school):
    st.title("📅 Bulk Attendance")
    classes = q("classes", "id,class_name,section,academic_year", school_id=school["id"], active=True)
    if not classes:
        st.warning("Create classes first.")
        return
    cm = {f'{x["class_name"]}-{x["section"]} ({x["academic_year"]})': x["id"] for x in classes}
    cls_name = st.selectbox("Class", list(cm))
    date = st.date_input("Date")

    class_only = cls_name.split("-")[0]
    students = q("students", "id,name,roll_no", school_id=school["id"], active=True, class_name=class_only)
    if not students:
        st.info("No students found.")
        return

    df = pd.DataFrame([{
        "student_id": s["id"],
        "roll_no": s.get("roll_no") or "",
        "student_name": s["name"],
        "present": True
    } for s in students]).sort_values(["roll_no", "student_name"])

    a = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=["student_id", "roll_no", "student_name"],
        column_config={"present": st.column_config.CheckboxColumn("Present")}
    )

    c1, c2 = st.columns(2)
    if c1.button("ALL PRESENT"):
        st.session_state["attendance_all_present"] = True
        st.rerun()
    if c2.button("SAVE ALL ATTENDANCE", type="primary"):
        rows = [{
            "school_id": school["id"],
            "student_id": r["student_id"],
            "attendance_date": str(date),
            "present": bool(r["present"]),
        } for _, r in a.iterrows()]
        try:
            supabase.table("attendance").upsert(
                rows, on_conflict="school_id,student_id,attendance_date"
            ).execute()
            st.success(f"Saved {len(rows)} attendance records.")
        except Exception as e:
            st.error(str(e))

def page_templates(school):
    st.title("🖨️ A4 Print Templates")
    st.write("Each school can keep its own A4 report-card/print design. Upload a background/template file and store its configuration.")
    with st.form("template"):
        name = st.text_input("Template name", value="Default A4 Report Card")
        orientation = st.selectbox("Orientation", ["portrait", "landscape"])
        bg = st.file_uploader("Template/background (PDF/PNG/JPG)", type=["pdf", "png", "jpg", "jpeg"])
        config = st.text_area("Template configuration JSON (optional)", value='{"page":"A4","margin_mm":10}')
        save = st.form_submit_button("Save template")
    if save:
        try:
            path = None
            if bg:
                ext = bg.name.rsplit(".", 1)[-1].lower()
                path = f'{school["id"]}/templates/{name.replace(" ", "_")}.{ext}'
                supabase.storage.from_("school-assets").upload(
                    path, bg.getvalue(), {"upsert": "true"}
                )
            supabase.table("print_templates").insert({
                "school_id": school["id"],
                "name": name.strip(),
                "page_size": "A4",
                "orientation": orientation,
                "storage_path": path,
                "config_json": config,
                "active": True,
            }).execute()
            st.success("Template saved.")
        except Exception as e:
            st.error(str(e))

    rows = q("print_templates", "*", school_id=school["id"], active=True)
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def page_users(school):
    st.title("👥 User/Profile Management")
    st.info("Create authentication users from Supabase Dashboard initially. This screen manages/links their ERP profile.")
    users = q("profiles", "id,email,full_name,role,active,school_id", school_id=school["id"])
    if users:
        st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)

def main():
    if "user" not in st.session_state:
        login()
        return

    user = st.session_state.user
    profile = st.session_state.profile

    schools = school_options(profile)
    if not schools:
        st.error("No active school is assigned to this account.")
        if st.button("Logout"):
            sign_out()
        return

    names = {f'{s["name"]} ({s["code"]})': s for s in schools}
    with st.sidebar:
        st.title("🏫 ERP")
        st.write(f'**{profile.get("full_name") or user.email}**')
        st.caption(profile["role"])
        selected = st.selectbox("School", list(names))
        school = names[selected]
        st.divider()

        if profile["role"] == "SuperAdmin":
            menu = st.radio("Menu", ["Dashboard", "Schools", "Students", "Classes", "Subjects", "Teacher Assignment", "Marks", "Attendance", "Print Templates", "Users"])
        elif profile["role"] == "Admin":
            menu = st.radio("Menu", ["Dashboard", "Students", "Classes", "Subjects", "Teacher Assignment", "Marks", "Attendance", "Print Templates", "Users"])
        elif profile["role"] == "Teacher":
            menu = st.radio("Menu", ["Dashboard", "Marks", "Attendance"])
        elif profile["role"] == "Parent":
            menu = st.radio("Menu", ["Dashboard"])
        else:
            menu = st.radio("Menu", ["Dashboard"])

        st.divider()
        if st.button("Logout", use_container_width=True):
            sign_out()

    if menu == "Dashboard":
        page_dashboard(profile, school)
    elif menu == "Schools":
        page_schools()
    elif menu == "Students":
        page_students(school)
    elif menu == "Classes":
        page_classes(school)
    elif menu == "Subjects":
        page_subjects(school)
    elif menu == "Teacher Assignment":
        page_teacher_assignment(school)
    elif menu == "Marks":
        page_marks(school)
    elif menu == "Attendance":
        page_attendance(school)
    elif menu == "Print Templates":
        page_templates(school)
    elif menu == "Users":
        page_users(school)

main()
