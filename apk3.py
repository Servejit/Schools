import streamlit as st
import requests
from supabase import create_client

st.set_page_config(page_title="School Management", page_icon="🏫", layout="wide")

URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
CREATE_USER = f"{URL}/functions/v1/Create-User"

sb = create_client(URL, KEY)

for x in ["logged_in", "user", "profile", "access_token", "refresh_token"]:
    if x not in st.session_state:
        st.session_state[x] = None if x != "logged_in" else False

# Restore Supabase session after Streamlit rerun
if st.session_state.access_token and st.session_state.refresh_token:
    try:
        sb.auth.set_session(
            st.session_state.access_token,
            st.session_state.refresh_token
        )
    except Exception:
        pass


def logout():
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for x in ["user", "profile", "access_token", "refresh_token"]:
        st.session_state[x] = None
    st.session_state.logged_in = False
    st.rerun()


def login():
    st.title("🏫 School Management System")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("🔐 Login", use_container_width=True):
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
            st.session_state.access_token = r.session.access_token
            st.session_state.refresh_token = r.session.refresh_token

            p = sb.table("profiles").select("*").eq(
                "id", r.user.id
            ).single().execute().data

            if not p:
                st.error("Profile not found.")
                return

            if p.get("active") is False:
                st.error("Your account is inactive.")
                sb.auth.sign_out()
                return

            st.session_state.profile = p
            st.session_state.logged_in = True
            st.rerun()

        except Exception as e:
            st.error("Login failed.")
            st.code(str(e))


def schools():
    st.header("🏫 School Management")

    try:
        data = sb.table("schools").select("*").order(
            "created_at", desc=True
        ).execute().data or []
    except Exception as e:
        st.error("Could not load schools.")
        st.code(str(e))
        return

    with st.expander("➕ Add New School"):
        name = st.text_input("School Name", key="school_name")
        code = st.text_input("School Code", key="school_code")
        address = st.text_area("Address", key="school_address")

        if st.button("Add School", use_container_width=True):
            if not name.strip() or not code.strip():
                st.warning("School name and code are required.")
                return

            try:
                old = sb.table("schools").select("id").eq(
                    "code", code.strip()
                ).execute().data

                if old:
                    st.error("School code already exists.")
                    return

                sb.table("schools").insert({
                    "name": name.strip(),
                    "code": code.strip(),
                    "address": address.strip(),
                    "active": True
                }).execute()

                st.success("School added.")
                st.rerun()

            except Exception as e:
                st.error("Could not add school.")
                st.code(str(e))

    st.divider()

    for s in data:
        sid = s["id"]
        active = s.get("active", True)

        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])

            with c1:
                st.markdown(f"### 🏫 {s.get('name','')}")
                st.caption(f"Code: {s.get('code','')}")
                st.caption(s.get("address") or "No address")

            with c2:
                st.success("ACTIVE" if active else "INACTIVE")

            with c3:
                if st.button(
                    "Deactivate" if active else "Activate",
                    key=f"sch_{sid}"
                ):
                    try:
                        sb.table("schools").update({
                            "active": not active
                        }).eq("id", sid).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

            with st.expander("✏️ Edit"):
                n = st.text_input(
                    "Name", s.get("name", ""), key=f"n{sid}"
                )
                c = st.text_input(
                    "Code", s.get("code", ""), key=f"c{sid}"
                )
                a = st.text_area(
                    "Address", s.get("address", ""), key=f"a{sid}"
                )

                if st.button("Save", key=f"save{sid}"):
                    try:
                        duplicate = sb.table("schools").select(
                            "id"
                        ).eq("code", c.strip()).neq(
                            "id", sid
                        ).execute().data

                        if duplicate:
                            st.error("School code already exists.")
                            continue

                        sb.table("schools").update({
                            "name": n.strip(),
                            "code": c.strip(),
                            "address": a.strip()
                        }).eq("id", sid).execute()

                        st.success("Updated.")
                        st.rerun()

                    except Exception as e:
                        st.error(str(e))


def users():
    st.header("👥 User Management")

    try:
        schools_data = sb.table("schools").select(
            "id,name,code,active"
        ).order("name").execute().data or []
    except Exception as e:
        st.error(str(e))
        return

    active_schools = [x for x in schools_data if x.get("active", True)]

    if not active_schools:
        st.warning("Create an active school first.")
        return

    smap = {
        f"{x['name']} ({x['code']})": x["id"]
        for x in active_schools
    }

    with st.expander("➕ Create User", expanded=True):
        school = st.selectbox("School", list(smap))
        name = st.text_input("Full Name")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        role = st.selectbox(
            "Role", ["Admin", "Teacher", "Student", "Parent"]
        )

        if st.button("👤 Create User", use_container_width=True):
            if not all([name.strip(), email.strip(), password]):
                st.warning("Fill all fields.")
                return

            if len(password) < 6:
                st.warning("Password must be at least 6 characters.")
                return

            token = st.session_state.access_token

            if not token:
                st.error("Session expired. Logout and login again.")
                return

            try:
                r = requests.post(
                    CREATE_USER,
                    json={
                        "email": email.strip(),
                        "password": password,
                        "full_name": name.strip(),
                        "role": role,
                        "school_id": smap[school]
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": KEY,
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )

                if 200 <= r.status_code < 300:
                    st.success("User created successfully.")
                    st.rerun()
                else:
                    st.error(f"Create-User failed: HTTP {r.status_code}")
                    st.code(r.text)

            except Exception as e:
                st.error("Could not connect to Create-User.")
                st.code(str(e))

    st.divider()
    st.subheader("📋 Existing Users")

    try:
        us = sb.table("profiles").select(
            "id,email,full_name,role,active,school_id"
        ).order("created_at", desc=True).execute().data or []
    except Exception as e:
        st.error(str(e))
        return

    school_names = {str(x["id"]): x["name"] for x in schools_data}

    for u in us:
        uid = u["id"]
        active = u.get("active", True)

        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 1])

            with c1:
                st.write(u.get("full_name") or u.get("email"))
                st.caption(u.get("email"))

            with c2:
                st.write(f"Role: **{u.get('role')}**")
                st.caption(
                    school_names.get(
                        str(u.get("school_id")), "No school"
                    )
                )

            with c3:
                if st.button(
                    "Deactivate" if active else "Activate",
                    key=f"usr{uid}"
                ):
                    try:
                        sb.table("profiles").update({
                            "active": not active
                        }).eq("id", uid).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def dashboard():
    p = st.session_state.profile
    role = p.get("role")

    top1, top2 = st.columns([5, 1])
    with top1:
        st.caption(f"Role: {role} | {p.get('email','')}")
    with top2:
        if st.button("Logout", use_container_width=True):
            logout()

    if role == "SuperAdmin":
        st.title("👑 SuperAdmin Dashboard")

        try:
            schools_count = sb.table("schools").select(
                "id", count="exact"
            ).execute().count or 0

            users_count = sb.table("profiles").select(
                "id", count="exact"
            ).execute().count or 0

            students_count = sb.table("students").select(
                "id", count="exact"
            ).execute().count or 0
        except Exception:
            schools_count = users_count = students_count = 0

        a, b, c = st.columns(3)
        a.metric("🏫 Schools", schools_count)
        b.metric("👥 Users", users_count)
        c.metric("🎓 Students", students_count)

        menu = st.radio(
            "Management",
            [
                "🏫 Schools", "👥 Users", "🎓 Students",
                "📚 Classes & Subjects", "📝 Marks",
                "📅 Attendance", "🖨️ Print Templates", "📊 Reports"
            ],
            horizontal=True
        )

        if menu == "🏫 Schools":
            schools()
        elif menu == "👥 Users":
            users()
        else:
            st.info(f"{menu} will be added next.")

    elif role == "Admin":
        st.title("🛠️ Admin Dashboard")
        st.info("Admin modules will be added next.")

    elif role == "Teacher":
        st.title("👨‍🏫 Teacher Dashboard")
        st.info("Teacher modules will be added next.")

    elif role == "Student":
        st.title("🎓 Student Dashboard")

        try:
            s = sb.table("students").select("*").eq(
                "user_id", st.session_state.user.id
            ).maybe_single().execute().data

            if s:
                st.subheader(s.get("name", "Student"))
                a, b, c = st.columns(3)
                a.metric("Class", s.get("class_name", "-"))
                b.metric("Section", s.get("section", "-"))
                c.metric("Roll No.", s.get("roll_no", "-"))
            else:
                st.info("Your student record is not linked yet.")
        except Exception as e:
            st.error("Could not load student information.")
            st.code(str(e))

    elif role == "Parent":
        st.title("👨‍👩‍👧 Parent Dashboard")
        st.info("Parent modules will be added next.")

    else:
        st.error(f"Unknown role: {role}")


if st.session_state.logged_in:
    dashboard()
else:
    login()
