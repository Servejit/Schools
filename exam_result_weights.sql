-- Exam result weightage storage for the School Management app
-- Run this once in Supabase SQL Editor.

create table if not exists public.exam_result_weights (
    id uuid primary key default gen_random_uuid(),
    school_id uuid not null references public.schools(id) on delete cascade,
    academic_year text not null,
    exam_id uuid not null references public.exam_assessments(id) on delete cascade,
    weight_percent numeric(6,2) not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint exam_result_weights_percent_chk
        check (weight_percent >= 0 and weight_percent <= 100),
    constraint exam_result_weights_unique
        unique (school_id, academic_year, exam_id)
);

alter table public.exam_result_weights enable row level security;

grant select, insert, update, delete
on public.exam_result_weights
to authenticated;

drop policy if exists "exam_result_weights_select" on public.exam_result_weights;
create policy "exam_result_weights_select"
on public.exam_result_weights
for select
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or (
                  p.school_id = exam_result_weights.school_id
                  and p.role in ('Admin', 'Admin+Teacher')
              )
          )
    )
);

drop policy if exists "exam_result_weights_insert" on public.exam_result_weights;
create policy "exam_result_weights_insert"
on public.exam_result_weights
for insert
to authenticated
with check (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or (
                  p.school_id = exam_result_weights.school_id
                  and p.role in ('Admin', 'Admin+Teacher')
              )
          )
    )
);

drop policy if exists "exam_result_weights_update" on public.exam_result_weights;
create policy "exam_result_weights_update"
on public.exam_result_weights
for update
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or (
                  p.school_id = exam_result_weights.school_id
                  and p.role in ('Admin', 'Admin+Teacher')
              )
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
              or (
                  p.school_id = exam_result_weights.school_id
                  and p.role in ('Admin', 'Admin+Teacher')
              )
          )
    )
);

drop policy if exists "exam_result_weights_delete" on public.exam_result_weights;
create policy "exam_result_weights_delete"
on public.exam_result_weights
for delete
to authenticated
using (
    exists (
        select 1
        from public.profiles p
        where p.id = auth.uid()
          and (
              p.role = 'SuperAdmin'
              or (
                  p.school_id = exam_result_weights.school_id
                  and p.role in ('Admin', 'Admin+Teacher')
              )
          )
    )
);
