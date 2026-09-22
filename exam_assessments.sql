-- Central Exam / Assessment names for each school
create table if not exists public.exam_assessments (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    name text not null,
    active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (school_id, name)
);

create index if not exists exam_assessments_school_id_idx
on public.exam_assessments(school_id);

alter table public.exam_assessments enable row level security;

drop policy if exists "exam_assessments_select_school" on public.exam_assessments;
drop policy if exists "exam_assessments_admin_insert" on public.exam_assessments;
drop policy if exists "exam_assessments_admin_update" on public.exam_assessments;
drop policy if exists "exam_assessments_admin_delete" on public.exam_assessments;

create policy "exam_assessments_select_school"
on public.exam_assessments
for select
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.school_id = exam_assessments.school_id
          and p.active = true
    )
);

create policy "exam_assessments_admin_insert"
on public.exam_assessments
for insert
with check (
    is_school_admin()
    and exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.school_id = exam_assessments.school_id
    )
);

create policy "exam_assessments_admin_update"
on public.exam_assessments
for update
using (
    is_school_admin()
    and exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.school_id = exam_assessments.school_id
    )
)
with check (
    is_school_admin()
    and exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.school_id = exam_assessments.school_id
    )
);

create policy "exam_assessments_admin_delete"
on public.exam_assessments
for delete
using (is_school_admin());

