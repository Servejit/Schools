-- Premium feature access control
-- SuperAdmin controls premium features for each Admin.

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
          and p.role = 'SuperAdmin'
          and p.active = true
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
          and p.role = 'SuperAdmin'
          and p.active = true
    )
)
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and p.role = 'SuperAdmin'
          and p.active = true
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
          and p.role = 'SuperAdmin'
          and p.active = true
    )
);
