import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

/** 与后端 AUTH_DISABLED 对应：开启后不登录，直接用本地开发账号。 */
export const AUTH_DISABLED = process.env.NEXT_PUBLIC_AUTH_DISABLED === "true";

/** Supabase 是否已完成配置。 */
export const SUPABASE_CONFIGURED = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

let client: SupabaseClient | null = null;

/**
 * 惰性创建 Supabase 客户端。
 *
 * 只在浏览器端首次调用时创建，避免 SSR 阶段访问 localStorage。
 */
export function getSupabase(): SupabaseClient | null {
  if (!SUPABASE_CONFIGURED) return null;
  if (typeof window === "undefined") return null;
  if (!client) {
    client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        storageKey: "atoms-demo-auth",
      },
    });
  }
  return client;
}

/** 读取当前会话（未登录返回 null）。 */
export async function getSession(): Promise<Session | null> {
  const supabase = getSupabase();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session ?? null;
}

/** 取出 access_token，供后端 Authorization 头使用。 */
export async function getAccessToken(): Promise<string | null> {
  const session = await getSession();
  return session?.access_token ?? null;
}

export async function signInWithPassword(email: string, password: string) {
  const supabase = getSupabase();
  if (!supabase) throw new Error("Supabase 未配置，请检查 NEXT_PUBLIC_SUPABASE_URL / ANON_KEY");
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  if (error) throw new Error(translateAuthError(error.message));
}

export async function signUpWithPassword(email: string, password: string) {
  const supabase = getSupabase();
  if (!supabase) throw new Error("Supabase 未配置，请检查 NEXT_PUBLIC_SUPABASE_URL / ANON_KEY");
  const { data, error } = await supabase.auth.signUp({ email, password });
  if (error) throw new Error(translateAuthError(error.message));
  // 开启邮箱验证时不会有 session，需要提示用户去收信
  return Boolean(data.session);
}

export async function sendMagicLink(email: string, redirectTo: string) {
  const supabase = getSupabase();
  if (!supabase) throw new Error("Supabase 未配置，请检查 NEXT_PUBLIC_SUPABASE_URL / ANON_KEY");
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: { emailRedirectTo: redirectTo },
  });
  if (error) throw new Error(translateAuthError(error.message));
}

export async function signOut() {
  const supabase = getSupabase();
  if (!supabase) return;
  await supabase.auth.signOut();
}

function translateAuthError(message: string): string {
  const map: Record<string, string> = {
    "Invalid login credentials": "邮箱或密码不正确",
    "Email not confirmed": "邮箱还没验证，请先去收件箱点确认链接",
    "User already registered": "该邮箱已注册，直接登录即可",
    "Password should be at least 6 characters": "密码至少 6 位",
  };
  return map[message] ?? message;
}
