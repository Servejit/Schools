-- Parent Report Card Access
-- Run this once in the Supabase SQL Editor.
-- Admin controls whether Parents may view report cards.
-- Parents can only view report cards for students linked to their own account.

-- ---------------------------------------------------------
-- 1. Allow Admin to manage the Parent Report Card feature
-- ---------------------------------------------------------

drop policy if exists "premium_feature_access_insert"
on public.premium_feature_access;

create policy "premium_feature_access_insert"
on public.premium_feature_access
for insert
to authenticated
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and (
              p.role = 'SuperAdmin'
              or (
                  p.role = 'Admin'
                  and p.id = premium_feature_access.admin_id
                  and p.school_id = premium_feature_access.school_id
                  and premium_feature_access.feature_key in (
                      'subject_wise_premium_parent_student',
                      'parent_report_card'
                  )
              )
          )
    )
);

drop policy if exists "premium_feature_access_update"
on public.premium_feature_access;

create policy "premium_feature_access_update"
on public.premium_feature_access
for update
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and (
              p.role = 'SuperAdmin'
              or (
                  p.role = 'Admin'
                  and p.id = premium_feature_access.admin_id
                  and p.school_id = premium_feature_access.school_id
                  and premium_feature_access.feature_key in (
                      'subject_wise_premium_parent_student',
                      'parent_report_card'
                  )
              )
          )
    )
)
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and (
              p.role = 'SuperAdmin'
              or (
                  p.role = 'Admin'
                  and p.id = premium_feature_access.admin_id
                  and p.school_id = premium_feature_access.school_id
                  and premium_feature_access.feature_key in (
                      'subject_wise_premium_parent_student',
                      'parent_report_card'
                  )
              )
          )
    )
);

-- ---------------------------------------------------------
-- 2. Secure permission check for Parent accounts
-- ---------------------------------------------------------

create or replace function public.parent_report_card_enabled(
    p_school_id uuid
)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1
        from public.profiles p
        join public.premium_feature_access f
          on f.school_id = p.school_id
         and f.feature_key = 'parent_report_card'
         and f.active = true
        where p.id = (select auth.uid())
          and p.school_id = p_school_id
          and p.role = 'Parent'
          and p.active = true
    );
$$;

revoke all on function public.parent_report_card_enabled(uuid)
from public;

grant execute on function public.parent_report_card_enabled(uuid)
to authenticated;

-- ---------------------------------------------------------
-- 3. Helper: current Parent has report-card permission
-- ---------------------------------------------------------

create or replace function public.parent_report_card_school_access(
    p_school_id uuid
)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select public.parent_report_card_enabled(p_school_id);
$$;

revoke all on function public.parent_report_card_school_access(uuid)
from public;

grant execute on function public.parent_report_card_school_access(uuid)
to authenticated;

-- ---------------------------------------------------------
-- 4. Parents can read ONLY their linked students
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_linked_students_select"
on public.students;

create policy "parents_report_card_linked_students_select"
on public.students
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
    and exists (
        select 1
        from public.parent_student_links l
        where l.parent_id = auth.uid()
          and l.student_id = students.id
    )
);

-- ---------------------------------------------------------
-- 5. Parents can read school subjects needed for the report
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_subjects_select"
on public.subjects;

create policy "parents_report_card_subjects_select"
on public.subjects
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
);

-- ---------------------------------------------------------
-- 6. Parents can read marks ONLY for linked children
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_marks_select"
on public.marks;

create policy "parents_report_card_marks_select"
on public.marks
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
    and exists (
        select 1
        from public.parent_student_links l
        where l.parent_id = auth.uid()
          and l.student_id = marks.student_id
    )
);

-- ---------------------------------------------------------
-- 7. Parents can read exam/assessment names for their school
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_exams_select"
on public.exam_assessments;

create policy "parents_report_card_exams_select"
on public.exam_assessments
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
);

-- ---------------------------------------------------------
-- 8. Parents can read attendance ONLY for linked children
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_attendance_select"
on public.attendance;

create policy "parents_report_card_attendance_select"
on public.attendance
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
    and exists (
        select 1
        from public.parent_student_links l
        where l.parent_id = auth.uid()
          and l.student_id = attendance.student_id
    )
);

-- ---------------------------------------------------------
-- 9. Parents can read the active Report Card template
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_templates_select"
on public.print_templates;

create policy "parents_report_card_templates_select"
on public.print_templates
for select
to authenticated
using (
    public.parent_report_card_school_access(school_id)
    and active = true
);

-- ---------------------------------------------------------
-- 10. Parents can read their school's basic information
-- ---------------------------------------------------------

drop policy if exists "parents_report_card_school_select"
on public.schools;

create policy "parents_report_card_school_select"
on public.schools
for select
to authenticated
using (
    public.parent_report_card_school_access(id)
);
