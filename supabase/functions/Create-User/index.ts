import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}

// Admin + SuperAdmin user creation enabled.\nDeno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return json({ error: "Method not allowed" }, 405);
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const publishableKey =
      Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ??
      Deno.env.get("SUPABASE_ANON_KEY");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
      return json(
        { error: "Create-User function is not configured correctly." },
        500,
      );
    }

    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return json({ error: "Authentication required" }, 401);
    }

    const accessToken = authHeader.replace("Bearer ", "").trim();
    if (!accessToken) {
      return json({ error: "Authentication required" }, 401);
    }

    // Client used only to identify the currently logged-in caller.
    const userClient = createClient(supabaseUrl, publishableKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    });

    const {
      data: { user: caller },
      error: callerError,
    } = await userClient.auth.getUser(accessToken);

    if (callerError || !caller) {
      return json({ error: "Authentication required" }, 401);
    }

    // Service-role client is kept inside the Edge Function only.
    const adminClient = createClient(supabaseUrl, serviceRoleKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    });

    const { data: callerProfile, error: profileError } =
      await adminClient
        .from("profiles")
        .select("id,email,full_name,role,active,school_id")
        .eq("id", caller.id)
        .maybeSingle();

    if (profileError) {
      return json(
        { error: "Could not verify your profile.", details: profileError.message },
        500,
      );
    }

    if (!callerProfile || callerProfile.active === false) {
      return json({ error: "Your account is inactive or profile was not found." }, 403);
    }

    const callerRole = String(callerProfile.role ?? "").trim();

    // Only SuperAdmin and Admin may use Create-User.
    if (
      callerRole !== "SuperAdmin" &&
      callerRole !== "Admin" &&
      callerRole !== "Admin+Teacher"
    ) {
      return json(
        { error: "Only an active SuperAdmin or Admin can create users." },
        403,
      );
    }

    const body = await req.json();

    const email = String(body?.email ?? "").trim().toLowerCase();
    const password = String(body?.password ?? "");
    const fullName = String(body?.full_name ?? "").trim();
    const requestedRole = String(body?.role ?? "").trim();
    const requestedSchoolId = String(body?.school_id ?? "").trim();

    if (!email || !password || !fullName || !requestedRole || !requestedSchoolId) {
      return json(
        {
          error:
            "Email, password, full_name, role and school_id are required.",
        },
        400,
      );
    }

    if (password.length < 6) {
      return json({ error: "Password must be at least 6 characters." }, 400);
    }

    const allowedRoles = [
      "Admin",
      "Admin+Teacher",
      "Teacher",
      "Student",
      "Parent"
    ];

    // SuperAdmin itself is not created through this endpoint.
    if (!allowedRoles.includes(requestedRole)) {
      return json(
        { error: "Invalid role. Allowed roles: Admin, Teacher, Student, Parent." },
        400,
      );
    }

    // Admin is permanently restricted to the Admin's own school.
    if (
      (callerRole === "Admin" || callerRole === "Admin+Teacher") &&
      String(callerProfile.school_id ?? "") !== requestedSchoolId
    ) {
      return json(
        { error: "Admin can create users only for their own school." },
        403,
      );
    }

    // Only SuperAdmin/Admin may assign the Admin+Teacher role.
    // Admin+Teacher users may still create other normal users, but they
    // cannot create or promote another user to Admin+Teacher.
    if (requestedRole === "Admin+Teacher" &&
        callerRole !== "SuperAdmin" &&
        callerRole !== "Admin") {
      return json(
        { error: "Only an active SuperAdmin or Admin can assign the Admin+Teacher role." },
        403,
      );
    }

    // SuperAdmin can create unlimited Admin+Teacher users.
    // Each Admin can create/own at most 2 ACTIVE Admin+Teacher users
    // in that Admin's own school.
    if (requestedRole === "Admin+Teacher" && callerRole === "Admin") {
      const { count: hybridCount, error: hybridCountError } = await adminClient
        .from("profiles")
        .select("id", { count: "exact", head: true })
        .eq("school_id", requestedSchoolId)
        .eq("role", "Admin+Teacher")
        .eq("active", true)
        .eq("admin_teacher_created_by", caller.id);

      if (hybridCountError) {
        return json(
          { error: "Could not verify your Admin + Teacher limit.", details: hybridCountError.message },
          500,
        );
      }

      if ((hybridCount ?? 0) >= 2) {
        return json(
          { error: "This Admin can have only 2 active Admin+Teacher users in this school." },
          400,
        );
      }
    }

    // Verify the target school exists and is active.
    const { data: targetSchool, error: schoolError } = await adminClient
      .from("schools")
      .select("id,name,code,active")
      .eq("id", requestedSchoolId)
      .maybeSingle();

    if (schoolError) {
      return json(
        { error: "Could not verify the selected school.", details: schoolError.message },
        500,
      );
    }

    if (!targetSchool) {
      return json({ error: "Selected school was not found." }, 400);
    }

    if (targetSchool.active === false) {
      return json({ error: "Selected school is inactive." }, 400);
    }

    // Create the Auth user. Service-role key is never sent to Streamlit.
    const { data: created, error: createError } =
      await adminClient.auth.admin.createUser({
        email,
        password,
        email_confirm: true,
        user_metadata: {
          full_name: fullName,
          role: requestedRole,
          school_id: requestedSchoolId,
        },
      });

    if (createError) {
      return json(
        { error: createError.message },
        createError.status && createError.status >= 400
          ? createError.status
          : 400,
      );
    }

    if (!created.user) {
      return json({ error: "User could not be created." }, 500);
    }

    // Normally handle_new_user() creates the profile. The fallback below
    // also supports projects where that trigger is not installed.
    const profilePayload = {
      id: created.user.id,
      email,
      full_name: fullName,
      role: requestedRole,
      active: true,
      school_id: requestedSchoolId,
      admin_teacher_created_by:
        requestedRole === "Admin+Teacher" && callerRole === "Admin"
          ? caller.id
          : null,
    };

    const { error: profileUpsertError } = await adminClient
      .from("profiles")
      .upsert(profilePayload, { onConflict: "id" });

    if (profileUpsertError) {
      // Roll back the Auth account if the profile cannot be created.
      await adminClient.auth.admin.deleteUser(created.user.id);

      return json(
        {
          error: "User was not saved to the school profile.",
          details: profileUpsertError.message,
        },
        500,
      );
    }

    return json({
      success: true,
      message: "User created successfully.",
      user: {
        id: created.user.id,
        email,
        full_name: fullName,
        role: requestedRole,
        school_id: requestedSchoolId,
      },
    });
  } catch (error) {
    return json(
      {
        error: "Unexpected error while creating user.",
        details: error instanceof Error ? error.message : String(error),
      },
      500,
    );
  }
});
