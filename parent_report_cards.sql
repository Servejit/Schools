-- Parent Report Card permission
-- Admin controls access for Parents. Parents can only read/generate
-- report cards for students linked to their own Parent account.

create or replace function public.parent_report_cards_enabled(
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
         and f.admin_id = p.id
         and f.feature_key = 'parent_report_cards'
         and f.active = true
        where p.id = (select auth.uid())
          and p.school_id = p_school_id
          and p.role = 'Parent'
          and p.active = true
    );
$$;

revoke all on function public.parent_report_cards_enabled(uuid)
from public;

grant execute on function public.parent_report_cards_enabled(uuid)
to authenticated;


create or replace function public.parent_report_card_linked_access(
    p_student_id uuid
)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1
        from public.parent_student_links l
        join public.students s
          on s.id = l.student_id
        where l.parent_id = (select auth.uid())
          and l.student_id = p_student_id
          and s.active = true
          and public.parent_report_cards_enabled(s.school_id)
    );
$$;

revoke all on function public.parent_report_card_linked_access(uuid)
from public;

grant execute on function public.parent_report_card_linked_access(uuid)
to authenticated;


drop policy if exists "parents_report_cards_linked_students_select"
on public.students;

create policy "parents_report_cards_linked_students_select"
on public.students
for select
to authenticated
using (
    (select public.parent_report_card_linked_access(id))
);


drop policy if exists "parents_report_cards_linked_marks_select"
on public.marks;

create policy "parents_report_cards_linked_marks_select"
on public.marks
for select
to authenticated
using (
    (select public.parent_report_card_linked_access(student_id))
);


drop policy if exists "parents_report_cards_linked_attendance_select"
on public.attendance;

create policy "parents_report_cards_linked_attendance_select"
on public.attendance
for select
to authenticated
using (
    (select public.parent_report_card_linked_access(student_id))
);


drop policy if exists "parents_report_cards_school_subjects_select"
on public.subjects;

create policy "parents_report_cards_school_subjects_select"
on public.subjects
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = (select auth.uid())
          and p.school_id = subjects.school_id
          and p.role = 'Parent'
          and p.active = true
          and public.parent_report_cards_enabled(subjects.school_id)
    )
);


drop policy if exists "parents_report_cards_school_templates_select"
on public.print_templates;

create policy "parents_report_cards_school_templates_select"
on public.print_templates
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = (select auth.uid())
          and p.school_id = print_templates.school_id
          and p.role = 'Parent'
          and p.active = true
          and public.parent_report_cards_enabled(print_templates.school_id)
    )
);


drop policy if exists "parents_report_cards_school_exams_select"
on public.exam_assessments;

create policy "parents_report_cards_school_exams_select"
on public.exam_assessments
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = (select auth.uid())
          and p.school_id = exam_assessments.school_id
          and p.role = 'Parent'
          and p.active = true
          and public.parent_report_cards_enabled(exam_assessments.school_id)
    )
);


drop policy if exists "parents_report_cards_school_select"
on public.schools;

create policy "parents_report_cards_school_select"
on public.schools
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = (select auth.uid())
          and p.school_id = schools.id
          and p.role = 'Parent'
          and p.active = true
          and public.parent_report_cards_enabled(schools.id)
    )
);
