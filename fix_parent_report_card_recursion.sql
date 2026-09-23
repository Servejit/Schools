-- Fix infinite recursion in Parent Report Card RLS
-- Run this once in Supabase SQL Editor.

create or replace function public.parent_report_card_linked_student_access(
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
        where l.parent_id = (select auth.uid())
          and l.student_id = p_student_id
    );
$$;

revoke all on function public.parent_report_card_linked_student_access(uuid)
from public;

grant execute on function public.parent_report_card_linked_student_access(uuid)
to authenticated;


drop policy if exists "parents_report_card_linked_students_select"
on public.students;

create policy "parents_report_card_linked_students_select"
on public.students
for select
to authenticated
using (
    (select public.parent_report_card_school_access(school_id))
    and (select public.parent_report_card_linked_student_access(id))
);


drop policy if exists "parents_report_card_marks_select"
on public.marks;

create policy "parents_report_card_marks_select"
on public.marks
for select
to authenticated
using (
    (select public.parent_report_card_school_access(school_id))
    and (select public.parent_report_card_linked_student_access(student_id))
);


drop policy if exists "parents_report_card_attendance_select"
on public.attendance;

create policy "parents_report_card_attendance_select"
on public.attendance
for select
to authenticated
using (
    (select public.parent_report_card_school_access(school_id))
    and (select public.parent_report_card_linked_student_access(student_id))
);
