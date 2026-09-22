-- Teacher subject assignments
-- One teacher can teach many Class + Subject combinations.

create table if not exists public.teacher_subject_assignments (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    teacher_id uuid not null references public.profiles(id) on delete cascade,
    class_id uuid not null references public.classes(id) on delete cascade,
    subject_id uuid not null references public.subjects(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (teacher_id, class_id, subject_id)
);

create index if not exists idx_teacher_subject_assignments_teacher
    on public.teacher_subject_assignments(teacher_id);

create index if not exists idx_teacher_subject_assignments_class
    on public.teacher_subject_assignments(class_id);

create index if not exists idx_teacher_subject_assignments_subject
    on public.teacher_subject_assignments(subject_id);

alter table public.teacher_subject_assignments enable row level security;

create or replace function public.is_school_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.role in ('Admin', 'SuperAdmin')
          and coalesce(p.active, true) = true
    );
$$;

drop policy if exists teacher_subject_assignments_select on public.teacher_subject_assignments;
create policy teacher_subject_assignments_select
on public.teacher_subject_assignments
for select
to authenticated
using (
    public.is_school_admin()
    or teacher_id = auth.uid()
);

drop policy if exists teacher_subject_assignments_insert on public.teacher_subject_assignments;
create policy teacher_subject_assignments_insert
on public.teacher_subject_assignments
for insert
to authenticated
with check (
    public.is_school_admin()
);

drop policy if exists teacher_subject_assignments_update on public.teacher_subject_assignments;
create policy teacher_subject_assignments_update
on public.teacher_subject_assignments
for update
to authenticated
using (public.is_school_admin())
with check (public.is_school_admin());

drop policy if exists teacher_subject_assignments_delete on public.teacher_subject_assignments;
create policy teacher_subject_assignments_delete
on public.teacher_subject_assignments
for delete
to authenticated
using (public.is_school_admin());
