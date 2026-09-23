-- School Management performance indexes
-- Run this once in Supabase SQL Editor.
-- These indexes speed up the most frequently filtered school/class/user/marks/attendance queries.
-- They do not change existing data or permissions.

create index if not exists idx_profiles_school_role_active
    on public.profiles (school_id, role, active);

create index if not exists idx_students_school_active_class_section
    on public.students (school_id, active, class_name, section);

create index if not exists idx_students_user_id
    on public.students (user_id);

create index if not exists idx_classes_school_active_class_section
    on public.classes (school_id, active, class_name, section);

create index if not exists idx_classes_school_class_teacher
    on public.classes (school_id, class_teacher_id, active);

create index if not exists idx_subjects_school_class_active
    on public.subjects (school_id, class_id, active);

create index if not exists idx_marks_school_class_subject_exam
    on public.marks (school_id, class_id, subject_id, exam_name);

create index if not exists idx_marks_student_exam
    on public.marks (student_id, exam_name);

create index if not exists idx_attendance_school_date
    on public.attendance (school_id, attendance_date);

create index if not exists idx_attendance_school_student_date
    on public.attendance (school_id, student_id, attendance_date);

create index if not exists idx_teacher_subject_assignments_teacher_school
    on public.teacher_subject_assignments (teacher_id, school_id);

create index if not exists idx_teacher_subject_assignments_class_subject
    on public.teacher_subject_assignments (school_id, class_id, subject_id);
