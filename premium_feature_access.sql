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
-- Admin / SuperAdmin:
--   Can link any Parent to any student in the school.
-- Admin+Teacher:
--   Has Admin-level linking authority for the school.
-- Teacher:
--   Can link Parents only to students in classes where the
--   teacher is the Class Teacher.
--
-- Premium remains completely separate:
--   Only Admin controls Parent/Student Subject-wise Premium.
--   Teachers cannot enable or disable Premium.

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


-- ---------------------------------------------------------
-- SELECT
-- ---------------------------------------------------------
-- Parent: own links.
-- SuperAdmin/Admin/Admin+Teacher: school-wide links.
-- Teacher: links for own Class Teacher classes.

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
          and (
              p.role = 'SuperAdmin'
              or (
                  p.role in ('Admin', 'Admin+Teacher')
                  and p.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
              )
              or (
                  p.role = 'Teacher'
                  and p.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
                  and exists (
                      select 1
                      from public.classes c
                      join public.students s
                        on s.school_id = c.school_id
                       and lower(trim(coalesce(s.class_name, ''))) =
                           lower(trim(coalesce(c.class_name, '')))
                       and lower(trim(coalesce(s.section, ''))) =
                           lower(trim(coalesce(c.section, '')))
                      where c.id = c.id
                        and c.class_teacher_id = auth.uid()
                        and c.active = true
                        and s.id = parent_student_links.student_id
                  )
              )
          )
    )
);


-- ---------------------------------------------------------
-- INSERT
-- ---------------------------------------------------------
create policy "parent_student_links_insert"
on public.parent_student_links
for insert
to authenticated
with check (
    exists (
        select 1
        from public.profiles parent_profile
        join public.students s
          on s.id = parent_student_links.student_id
         and s.school_id = parent_profile.school_id
        where parent_profile.id = parent_student_links.parent_id
          and parent_profile.role = 'Parent'
          and parent_profile.active = true
    )

    and exists (
        select 1
        from public.profiles actor
        where actor.id = auth.uid()
          and actor.active = true
          and (
              actor.role = 'SuperAdmin'

              or (
                  actor.role in ('Admin', 'Admin+Teacher')
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
              )

              or (
                  actor.role = 'Teacher'
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
                  and exists (
                      select 1
                      from public.classes c
                      join public.students s
                        on s.school_id = c.school_id
                       and lower(trim(coalesce(s.class_name, ''))) =
                           lower(trim(coalesce(c.class_name, '')))
                       and lower(trim(coalesce(s.section, ''))) =
                           lower(trim(coalesce(c.section, '')))
                      where c.class_teacher_id = auth.uid()
                        and c.active = true
                        and s.id = parent_student_links.student_id
                  )
              )
          )
    )
);


-- ---------------------------------------------------------
-- DELETE
-- ---------------------------------------------------------
-- Same authority as linking. This lets a Teacher remove a
-- link from a student in the Teacher's own Class Teacher class.

create policy "parent_student_links_delete"
on public.parent_student_links
for delete
to authenticated
using (
    exists (
        select 1
        from public.profiles actor
        where actor.id = auth.uid()
          and actor.active = true
          and (
              actor.role = 'SuperAdmin'

              or (
                  actor.role in ('Admin', 'Admin+Teacher')
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
              )

              or (
                  actor.role = 'Teacher'
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
                  and exists (
                      select 1
                      from public.classes c
                      join public.students s
                        on s.school_id = c.school_id
                       and lower(trim(coalesce(s.class_name, ''))) =
                           lower(trim(coalesce(c.class_name, '')))
                       and lower(trim(coalesce(s.section, ''))) =
                           lower(trim(coalesce(c.section, '')))
                      where c.class_teacher_id = auth.uid()
                        and c.active = true
                        and s.id = parent_student_links.student_id
                  )
              )
          )
    )
);


-- ---------------------------------------------------------
-- UPDATE
-- ---------------------------------------------------------
-- Links are replaced by the app (delete + insert), but this
-- policy is included for direct database updates as well.

create policy "parent_student_links_update"
on public.parent_student_links
for update
to authenticated
using (
    exists (
        select 1
        from public.profiles actor
        where actor.id = auth.uid()
          and actor.active = true
          and (
              actor.role = 'SuperAdmin'
              or (
                  actor.role in ('Admin', 'Admin+Teacher')
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
              )
              or (
                  actor.role = 'Teacher'
                  and actor.school_id = (
                      select s.school_id
                      from public.students s
                      where s.id = parent_student_links.student_id
                  )
                  and exists (
                      select 1
                      from public.classes c
                      join public.students s
                        on s.school_id = c.school_id
                       and lower(trim(coalesce(s.class_name, ''))) =
                           lower(trim(coalesce(c.class_name, '')))
                       and lower(trim(coalesce(s.section, ''))) =
                           lower(trim(coalesce(c.section, '')))
                      where c.class_teacher_id = auth.uid()
                        and c.active = true
                        and s.id = parent_student_links.student_id
                  )
              )
          )
    )
)
with check (
    exists (
        select 1
        from public.profiles parent_profile
        join public.students s
          on s.id = parent_student_links.student_id
         and s.school_id = parent_profile.school_id
        where parent_profile.id = parent_student_links.parent_id
          and parent_profile.role = 'Parent'
          and parent_profile.active = true
    )
);


-- =========================================================
-- IMPORTANT PREMIUM RULE
-- =========================================================
-- DO NOT give Teachers or Admin+Teacher permission to modify
-- premium_feature_access.
--
-- Premium access remains:
-- SuperAdmin → controls Admin Premium
-- Admin      → controls Parent/Student Subject-wise Premium
-- Teacher    → NO Premium control
-- Admin+Teacher → NO Premium control
--
-- The policies above this section enforce that rule.
