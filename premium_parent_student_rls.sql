-- School-wide Subject-wise Premium access for Parent and Student accounts.
-- Run this once in the Supabase SQL Editor.
-- This fixes the case where RLS hides school-wide students/classes/subjects/marks
-- from Parent/Student sessions even though Admin has enabled Premium.

create or replace function public.parent_student_premium_school_access(
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
        where p.id = (select auth.uid())
          and p.school_id = p_school_id
          and p.role in ('Parent', 'Student')
          and p.active = true
    )
    and public.parent_student_subject_wise_premium_enabled(p_school_id);
$$;

revoke all on function public.parent_student_premium_school_access(uuid)
from public;

grant execute on function public.parent_student_premium_school_access(uuid)
to authenticated;


drop policy if exists "parents_students_premium_school_students_select"
on public.students;

create policy "parents_students_premium_school_students_select"
on public.students
for select
to authenticated
using (
    (select public.parent_student_premium_school_access(school_id))
);


drop policy if exists "parents_students_premium_school_classes_select"
on public.classes;

create policy "parents_students_premium_school_classes_select"
on public.classes
for select
to authenticated
using (
    (select public.parent_student_premium_school_access(school_id))
);


drop policy if exists "parents_students_premium_school_subjects_select"
on public.subjects;

create policy "parents_students_premium_school_subjects_select"
on public.subjects
for select
to authenticated
using (
    (select public.parent_student_premium_school_access(school_id))
);


drop policy if exists "parents_students_premium_school_marks_select"
on public.marks;

create policy "parents_students_premium_school_marks_select"
on public.marks
for select
to authenticated
using (
    (select public.parent_student_premium_school_access(school_id))
);


drop policy if exists "parents_students_premium_school_exams_select"
on public.exam_assessments;

create policy "parents_students_premium_school_exams_select"
on public.exam_assessments
for select
to authenticated
using (
    (select public.parent_student_premium_school_access(school_id))
);
