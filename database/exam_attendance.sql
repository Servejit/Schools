-- Exam-wise attendance replaces daily attendance in the application.
-- Existing public.attendance is intentionally preserved for now so historical
-- daily records are not lost. The Streamlit app will no longer use it.

create table if not exists public.exam_attendance (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    student_id uuid not null references public.students(id) on delete cascade,
    class_id uuid references public.classes(id) on delete set null,
    exam_name text not null,
    total_days integer not null default 0 check (total_days >= 0),
    present_days integer not null default 0 check (present_days >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint exam_attendance_present_not_over_total
        check (present_days <= total_days),
    constraint exam_attendance_unique_student_exam
        unique (school_id, student_id, exam_name)
);

create index if not exists idx_exam_attendance_school_exam
    on public.exam_attendance (school_id, exam_name);

create index if not exists idx_exam_attendance_school_student
    on public.exam_attendance (school_id, student_id);

create index if not exists idx_exam_attendance_class_exam
    on public.exam_attendance (school_id, class_id, exam_name);

alter table public.exam_attendance enable row level security;

drop policy if exists "exam_attendance_select" on public.exam_attendance;
create policy "exam_attendance_select"
on public.exam_attendance
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or p.school_id = exam_attendance.school_id
          )
    )
);

drop policy if exists "exam_attendance_insert" on public.exam_attendance;
create policy "exam_attendance_insert"
on public.exam_attendance
for insert
to authenticated
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or p.school_id = exam_attendance.school_id
          )
    )
);

drop policy if exists "exam_attendance_update" on public.exam_attendance;
create policy "exam_attendance_update"
on public.exam_attendance
for update
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or p.school_id = exam_attendance.school_id
          )
    )
)
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or p.school_id = exam_attendance.school_id
          )
    )
);

drop policy if exists "exam_attendance_delete" on public.exam_attendance;
create policy "exam_attendance_delete"
on public.exam_attendance
for delete
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or p.school_id = exam_attendance.school_id
          )
    )
);

-- Keep updated_at correct when a row is edited.
create or replace function public.set_exam_attendance_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_exam_attendance_updated_at on public.exam_attendance;
create trigger trg_exam_attendance_updated_at
before update on public.exam_attendance
for each row
execute function public.set_exam_attendance_updated_at();
