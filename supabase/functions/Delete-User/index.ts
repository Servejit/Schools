import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "Method not allowed" }, 405);

  try {
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const publishableKey =
      Deno.env.get("SUPABASE_PUBLISHABLE_KEY") ??
      Deno.env.get("SUPABASE_ANON_KEY");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !publishableKey || !serviceRoleKey) {
      return json({ error: "Delete-User function is not configured correctly." }, 500);
    }

    const authHeader = req.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return json({ error: "Authentication required" }, 401);
    }

    const accessToken = authHeader.replace("Bearer ", "").trim();
    const userClient = createClient(supabaseUrl, publishableKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });

    const { data: { user: caller }, error: callerError } =
      await userClient.auth.getUser(accessToken);

    if (callerError || !caller) return json({ error: "Authentication required" }, 401);

    const adminClient = createClient(supabaseUrl, serviceRoleKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });

    const { data: callerProfile, error: profileError } = await adminClient
      .from("profiles")
      .select("id,role,active,school_id")
      .eq("id", caller.id)
      .maybeSingle();

    if (profileError) return json({ error: "Could not verify your profile.", details: profileError.message }, 500);
    if (!callerProfile || callerProfile.active === false) {
      return json({ error: "Your account is inactive or profile was not found." }, 403);
    }

    const callerRole = String(callerProfile.role ?? "").trim();
    if (!["SuperAdmin", "Admin", "Admin+Teacher"].includes(callerRole)) {
      return json({ error: "Only SuperAdmin or authorized school administrators can delete users." }, 403);
    }

    const body = await req.json();
    const targetUserId = String(body?.user_id ?? "").trim();
    if (!targetUserId) return json({ error: "user_id is required." }, 400);
    if (targetUserId === caller.id) return json({ error: "You cannot delete your own account." }, 400);

    const { data: targetProfile, error: targetError } = await adminClient
      .from("profiles")
      .select("id,role,school_id")
      .eq("id", targetUserId)
      .maybeSingle();

    if (targetError) return json({ error: "Could not find target user.", details: targetError.message }, 500);
    if (!targetProfile) {
      // The Auth account may exist even when its profile was already removed.
      const { error: authDeleteError } = await adminClient.auth.admin.deleteUser(targetUserId);
      if (authDeleteError) return json({ error: authDeleteError.message }, 400);
      return json({ success: true, message: "User deleted successfully." });
    }

    if (targetProfile.role === "SuperAdmin") {
      return json({ error: "SuperAdmin accounts cannot be deleted here." }, 403);
    }

    if (
      callerRole !== "SuperAdmin" &&
      String(callerProfile.school_id ?? "") !== String(targetProfile.school_id ?? "")
    ) {
      return json({ error: "You can delete users only from your own school." }, 403);
    }

    // Remove application-level dependent records before deleting Auth.
    await adminClient.from("parent_student_links").delete().eq("parent_id", targetUserId);
    await adminClient.from("teacher_subject_assignments").delete().eq("teacher_id", targetUserId);
    await adminClient.from("classes").update({ class_teacher_id: null }).eq("class_teacher_id", targetUserId);
    await adminClient.from("students").update({ user_id: null }).eq("user_id", targetUserId);

    const { error: authDeleteError } =
      await adminClient.auth.admin.deleteUser(targetUserId);

    if (authDeleteError) {
      return json({ error: "Could not delete the Auth account.", details: authDeleteError.message }, 400);
    }

    // Delete profile explicitly in case there is no cascade/trigger.
    const { error: profileDeleteError } =
      await adminClient.from("profiles").delete().eq("id", targetUserId);

    if (profileDeleteError) {
      return json({
        error: "Auth user deleted, but the school profile could not be removed.",
        details: profileDeleteError.message,
      }, 500);
    }

    return json({ success: true, message: "User and Auth account deleted successfully." });
  } catch (error) {
    return json({
      error: "Unexpected error while deleting user.",
      details: error instanceof Error ? error.message : String(error),
    }, 500);
  }
});
