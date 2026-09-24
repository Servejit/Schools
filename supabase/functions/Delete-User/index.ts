import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function responseJson(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json",
    },
  });
}

Deno.serve(async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return responseJson({ error: "Method not allowed" }, 405);
  }

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const publishableKey =
      Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ??
      Deno.env.get("SUPABASE_ANON_KEY");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
      return responseJson(
        { error: "Delete-User function is not configured correctly." },
        500,
      );
    }

    const authHeader = req.headers.get("Authorization");

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return responseJson({ error: "Authentication required" }, 401);
    }

    const accessToken = authHeader.substring("Bearer ".length).trim();

    if (!accessToken) {
      return responseJson({ error: "Authentication required" }, 401);
    }

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
      return responseJson({ error: "Authentication required" }, 401);
    }

    const adminClient = createClient(supabaseUrl, serviceRoleKey, {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    });

    const { data: callerProfile, error: profileError } = await adminClient
      .from("profiles")
      .select("id, role, active, school_id")
      .eq("id", caller.id)
      .maybeSingle();

    if (profileError) {
      return responseJson(
        {
          error: "Could not verify your profile.",
          details: profileError.message,
        },
        500,
      );
    }

    if (!callerProfile || callerProfile.active === false) {
      return responseJson(
        { error: "Your account is inactive or profile was not found." },
        403,
      );
    }

    const callerRole = String(callerProfile.role ?? "").trim();

    if (
      callerRole !== "SuperAdmin" &&
      callerRole !== "Admin" &&
      callerRole !== "Admin+Teacher"
    ) {
      return responseJson(
        {
          error:
            "Only SuperAdmin or authorized school administrators can delete users.",
        },
        403,
      );
    }

    let body: { user_id?: unknown };

    try {
      body = await req.json();
    } catch {
      return responseJson({ error: "Invalid JSON request body." }, 400);
    }

    const targetUserId = String(body?.user_id ?? "").trim();

    if (!targetUserId) {
      return responseJson({ error: "user_id is required." }, 400);
    }

    if (targetUserId === caller.id) {
      return responseJson(
        { error: "You cannot delete your own account." },
        400,
      );
    }

    const { data: targetProfile, error: targetError } = await adminClient
      .from("profiles")
      .select("id, role, school_id")
      .eq("id", targetUserId)
      .maybeSingle();

    if (targetError) {
      return responseJson(
        {
          error: "Could not find target user.",
          details: targetError.message,
        },
        500,
      );
    }

    if (!targetProfile) {
      const { error: authDeleteError } =
        await adminClient.auth.admin.deleteUser(targetUserId);

      if (authDeleteError) {
        return responseJson(
          {
            error: "Could not delete the Auth account.",
            details: authDeleteError.message,
          },
          400,
        );
      }

      return responseJson({
        success: true,
        message: "User deleted successfully.",
      });
    }

    if (String(targetProfile.role ?? "").trim() === "SuperAdmin") {
      return responseJson(
        { error: "SuperAdmin accounts cannot be deleted here." },
        403,
      );
    }

    if (
      callerRole !== "SuperAdmin" &&
      String(callerProfile.school_id ?? "") !==
        String(targetProfile.school_id ?? "")
    ) {
      return responseJson(
        { error: "You can delete users only from your own school." },
        403,
      );
    }

    const { error: linksError } = await adminClient
      .from("parent_student_links")
      .delete()
      .eq("parent_id", targetUserId);

    if (linksError) {
      return responseJson(
        {
          error: "Could not remove parent links.",
          details: linksError.message,
        },
        500,
      );
    }

    const { error: assignmentsError } = await adminClient
      .from("teacher_subject_assignments")
      .delete()
      .eq("teacher_id", targetUserId);

    if (assignmentsError) {
      return responseJson(
        {
          error: "Could not remove teacher assignments.",
          details: assignmentsError.message,
        },
        500,
      );
    }

    const { error: classError } = await adminClient
      .from("classes")
      .update({ class_teacher_id: null })
      .eq("class_teacher_id", targetUserId);

    if (classError) {
      return responseJson(
        {
          error: "Could not clear class teacher assignment.",
          details: classError.message,
        },
        500,
      );
    }

    const { error: studentError } = await adminClient
      .from("students")
      .update({ user_id: null })
      .eq("user_id", targetUserId);

    if (studentError) {
      return responseJson(
        {
          error: "Could not clear student user link.",
          details: studentError.message,
        },
        500,
      );
    }

    const { error: authDeleteError } =
      await adminClient.auth.admin.deleteUser(targetUserId);

    if (authDeleteError) {
      return responseJson(
        {
          error: "Could not delete the Auth account.",
          details: authDeleteError.message,
        },
        400,
      );
    }

    const { error: profileDeleteError } = await adminClient
      .from("profiles")
      .delete()
      .eq("id", targetUserId);

    if (profileDeleteError) {
      return responseJson(
        {
          error:
            "Auth user deleted, but the school profile could not be removed.",
          details: profileDeleteError.message,
        },
        500,
      );
    }

    return responseJson({
      success: true,
      message: "User and Auth account deleted successfully.",
    });
  } catch (error) {
    return responseJson(
      {
        error: "Unexpected error while deleting user.",
        details: error instanceof Error ? error.message : String(error),
      },
      500,
    );
  }
});
