                for cl in session_class_rows
            }
        ]
        visible_subjects = [
            x for x in subjects
            if str(x.get("class_id")) in class_ids
        ]
        visible_class_ids = class_ids

    subject_ids = {str(x["id"]) for x in visible_subjects}

    # Marks are still restricted to the selected session/class scope.
    visible_marks = [
        x for x in marks
        if str(x.get("class_id")) in visible_class_ids
        and str(x.get("subject_id")) in subject_ids
    ]

    student_map = {str(x["id"]): x for x in visible_students}

    # Keep every subject as a separate entry by SUBJECT ID. This prevents
    # subjects with the same name in different classes from overwriting each
    # other in the dictionary.
    subject_rows = {}
    for subject in visible_subjects:
        sid = str(subject["id"])
        subject_name = (
            subject.get("subject_name")
            or subject.get("name")
            or "Subject"
        )

        rows = []
        for mark in visible_marks:
            if str(mark.get("subject_id")) != sid:
                continue

            student = student_map.get(str(mark.get("student_id")))
            if not student:
                continue

            maximum = float(
                mark.get("max_marks")
                or subject.get("max_marks")
                or 100
            )
            obtained = float(mark.get("marks") or 0)
            percentage = obtained * 100 / maximum if maximum else 0

            rows.append({
                "Student Name": student.get("name") or "",
                "Admission No.": student.get("admission_no") or "",
                "Class": student.get("class_name") or "",
                "Section": student.get("section") or "",
                "Father Name": (
                    student.get("father_name")
                    or student.get("parent_name")
                    or ""
                ),
                "Marks": round(obtained, 2),
                "Maximum": round(maximum, 2),
                "Percentage": round(percentage, 2)
            })

        rows.sort(
            key=lambda x: (
                float(x["Percentage"]),
                float(x["Marks"])
            ),
            reverse=True
        )

        subject_rows[sid] = {
            "name": subject_name,
            "rows": rows
        }

    if not subject_rows:
        st.info("No active subjects are available for this school.")
        return

    subject_items = list(subject_rows.items())

    subject_palette = [
        "#E3F2FD", "#E8F5E9", "#FFF3E0", "#F3E5F5", "#FFFDE7",
        "#E0F7FA", "#FBE9E7", "#E8EAF6", "#F1F8E9", "#FCE4EC"
    ]
    subject_colors = {
        sid: subject_palette[idx % len(subject_palette)]
        for idx, (sid, _) in enumerate(subject_items)
    }

    tab_topper, tab_70, tab_80, tab_90 = st.tabs(
        [
            "🏆 Top Students",
            "📈 >70%",
            "📈 >80%",
            "📈 >90%"
        ]
    )

    for tab, threshold in [
        (tab_70, 70),
        (tab_80, 80),
        (tab_90, 90)
    ]:
        with tab:
            shown = False
            for sid, info in subject_items:
                subject_name = info["name"]
                rows = info["rows"]
                filtered = [
                    row for row in rows
                    if float(row["Percentage"]) > threshold
                ]
                st.markdown(f"#### 📚 {subject_name}")
                if not filtered:
                    st.caption(
                        "No students above this percentage for the selected exam."
                    )
                    continue

                shown = True
                filtered_df = pd.DataFrame(filtered)
                bg = subject_colors[sid]
                st.dataframe(
                    filtered_df.style.map(
                        lambda _: f"background-color: {bg}"
                    ),
                    hide_index=True,
                    use_container_width=True
                )

            if not shown:
                st.info(
                    f"No students are above {threshold}% in the selected subjects."
                )

    with tab_topper:
        top_n = st.selectbox(
            "Show Top Students",
            [10, 20, 30, 50],
            index=0,
            key=f"subject_premium_top_n_{viewer_label}"
        )

        for sid, info in subject_items:
            subject_name = info["name"]
            rows = info["rows"]

            st.markdown(f"#### 📚 {subject_name}")

            if not rows:
                st.caption(
                    "No marks are available for this subject in the selected exam."
                )
                continue

            # Show up to the selected number. If a subject has fewer
            # students than the selected limit, show ALL available students.
            number_to_show = min(int(top_n), len(rows))
            top_rows = rows[:number_to_show]

            st.caption(
                f"Showing {number_to_show} of {len(rows)} student(s) "
                f"for this subject."
            )

            display_rows = []

            for index, row in enumerate(top_rows, start=1):
                display_rows.append({
                    "Rank": index,
                    "Student Name": row["Student Name"],
                    "Class": row["Class"],
                    "Section": row["Section"],
                    "Father Name": row["Father Name"],
                    "Marks": (
                        f'{format_mark(row["Marks"])}/{format_mark(row["Maximum"])}'
                    ),
                    "Percentage": f'{format_mark(row["Percentage"])}%'