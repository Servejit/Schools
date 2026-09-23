-- Class Teacher Notices
-- Run this once in Supabase SQL Editor.

create table if not exists public.school_notices (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    class_id uuid not null references public.classes(id) on delete cascade,
    teacher_id uuid not null references public.profiles(id) on delete cascade,
    notice_date date not null default current_date,
    message text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists school_notices_school_idx
on public.school_notices(school_id, notice_date desc);

create index if not exists school_notices_class_idx
on public.school_notices(class_id, notice_date desc);

alter table public.school_notices enable row level security;

-- SECURITY DEFINER checks avoid RLS recursion.
create or replace function public.class_teacher_notice_insert_allowed(
    p_school_id uuid,
    p_class_id uuid
)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select
        exists (
            select 1
            from public.profiles p
            where p.id = (select auth.uid())
              and p.role = 'SuperAdmin'
              and p.active = true
        )
        or exists (
            select 1
            from public.profiles p
            where p.id = (select auth.uid())
              and p.school_id = p_school_id
              and p.role in ('Admin', 'Admin+Teacher')
              and p.active = true
        )
        or exists (
            select 1
            from public.classes c
            where c.id = p_class_id
              and c.school_id = p_school_id
              and c.class_teacher_id = (select auth.uid())
              and c.active = true
        );
$$;

revoke all on function public.class_teacher_notice_insert_allowed(uuid, uuid)
from public;

grant execute on function public.class_teacher_notice_insert_allowed(uuid, uuid)
to authenticated;

create or replace function public.parent_notice_access(
    p_school_id uuid,
    p_class_id uuid
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
        join public.students s on s.id = l.student_id
        join public.classes c
          on c.school_id = s.school_id
         and lower(trim(c.class_name)) = lower(trim(s.class_name))
         and lower(trim(coalesce(c.section, ''))) =
             lower(trim(coalesce(s.section, '')))
        where l.parent_id = (select auth.uid())
          and s.school_id = p_school_id
          and c.id = p_class_id
          and s.active = true
          and c.active = true
    );
$$;

revoke all on function public.parent_notice_access(uuid, uuid)
from public;

grant execute on function public.parent_notice_access(uuid, uuid)
to authenticated;

create or replace function public.student_notice_access(
    p_school_id uuid,
    p_class_id uuid
)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
    select exists (
        select 1
        from public.students s
        join public.classes c
          on c.school_id = s.school_id
         and lower(trim(c.class_name)) = lower(trim(s.class_name))
         and lower(trim(coalesce(c.section, ''))) =
             lower(trim(coalesce(s.section, '')))
        where s.user_id = (select auth.uid())
          and s.school_id = p_school_id
          and c.id = p_class_id
          and s.active = true
          and c.active = true
    );
$$;

revoke all on function public.student_notice_access(uuid, uuid)
from public;

grant execute on function public.student_notice_access(uuid, uuid)
to authenticated;

drop policy if exists "class_teachers_insert_school_notices"
on public.school_notices;

create policy "class_teachers_insert_school_notices"
on public.school_notices
for insert
to authenticated
with check (
    (select public.class_teacher_notice_insert_allowed(school_id, class_id))
    and teacher_id = (select auth.uid())
);

drop policy if exists "parents_select_school_notices"
on public.school_notices;

create policy "parents_select_school_notices"
on public.school_notices
for select
to authenticated
using (
    (select public.parent_notice_access(school_id, class_id))
);

drop policy if exists "students_select_school_notices"
on public.school_notices;

create policy "students_select_school_notices"
on public.school_notices
for select
to authenticated
using (
    (select public.student_notice_access(school_id, class_id))
);

-- Teachers can see notices they have sent.
drop policy if exists "teachers_select_own_school_notices"
on public.school_notices;

create policy "teachers_select_own_school_notices"
on public.school_notices
for select
to authenticated
using (
    teacher_id = (select auth.uid())
);

