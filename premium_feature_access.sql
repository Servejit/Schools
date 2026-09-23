-- Premium feature access control
-- SuperAdmin controls Admin Premium.
-- Admin can enable Subject-wise Premium for Parents/Students.
-- Parent/Student access is checked through a SECURITY DEFINER RPC because
-- they should not receive direct SELECT access to premium_feature_access.

create table if not exists public.premium_feature_access (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    admin_id uuid not null references public.profiles(id) on delete cascade,
    feature_key text not null,
    active boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (school_id, admin_id, feature_key)
);

create index if not exists premium_feature_access_school_idx
on public.premium_feature_access(school_id);

create index if not exists premium_feature_access_admin_idx
on public.premium_feature_access(admin_id);

alter table public.premium_feature_access enable row level security;

drop policy if exists "premium_feature_access_select" on public.premium_feature_access;
drop policy if exists "premium_feature_access_insert" on public.premium_feature_access;
drop policy if exists "premium_feature_access_update" on public.premium_feature_access;
drop policy if exists "premium_feature_access_delete" on public.premium_feature_access;

create policy "premium_feature_access_select"
on public.premium_feature_access
for select
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
              )
          )
    )
);

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
                  and premium_feature_access.feature_key =
                      'subject_wise_premium_parent_student'
              )
          )
    )
);

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
                  and premium_feature_access.feature_key =
                      'subject_wise_premium_parent_student'
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
                  and premium_feature_access.feature_key =
                      'subject_wise_premium_parent_student'
              )
          )
    )
);

create policy "premium_feature_access_delete"
on public.premium_feature_access
for delete
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role = 'SuperAdmin'
    )
);

create or replace function public.parent_student_subject_wise_premium_enabled(
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
        from public.profiles a
        join public.premium_feature_access admin_premium
          on admin_premium.school_id = a.school_id
         and admin_premium.admin_id = a.id
         and admin_premium.feature_key = 'school_academic_status'
         and admin_premium.active = true
        join public.premium_feature_access parent_permission
          on parent_permission.school_id = a.school_id
         and parent_permission.admin_id = a.id
         and parent_permission.feature_key =
             'subject_wise_premium_parent_student'
         and parent_permission.active = true
        where a.school_id = p_school_id
          and a.role = 'Admin'
          and a.active = true
    );
$$;

revoke all on function public.parent_student_subject_wise_premium_enabled(uuid)
from public;

grant execute on function public.parent_student_subject_wise_premium_enabled(uuid)
to authenticated;


-- =========================================================
-- PARENT ↔ STUDENT LINKING
-- =========================================================
-- Parent accounts are linked to students separately from
-- students.user_id. This allows one Parent to have multiple
-- children while keeping Student login independent.

create table if not exists public.parent_student_links (
    id uuid primary key default gen_random_uuid(),
    parent_id uuid not null references public.profiles(id) on delete cascade,
    student_id uuid not null references public.students(id) on delete cascade,
    created_at timestamptz not null default now(),
    unique (parent_id, student_id)
);

create index if not exists parent_student_links_parent_idx
on public.parent_student_links(parent_id);

create index if not exists parent_student_links_student_idx
on public.parent_student_links(student_id);

alter table public.parent_student_links enable row level security;

drop policy if exists "parent_student_links_select"
on public.parent_student_links;

drop policy if exists "parent_student_links_insert"
on public.parent_student_links;

drop policy if exists "parent_student_links_update"
on public.parent_student_links;

drop policy if exists "parent_student_links_delete"
on public.parent_student_links;

create policy "parent_student_links_select"
on public.parent_student_links
for select
to authenticated
using (
    parent_id = auth.uid()
    or exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('Admin', 'SuperAdmin')
    )
);

create policy "parent_student_links_insert"
on public.parent_student_links
for insert
to authenticated
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('Admin', 'SuperAdmin')
          and p.school_id = (
              select s.school_id
              from public.students s
              where s.id = parent_student_links.student_id
          )
    )
);

create policy "parent_student_links_update"
on public.parent_student_links
for update
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('Admin', 'SuperAdmin')
    )
)
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('Admin', 'SuperAdmin')
    )
);

create policy "parent_student_links_delete"
on public.parent_student_links
for delete
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.active = true
          and p.role in ('Admin', 'SuperAdmin')
    )
);
