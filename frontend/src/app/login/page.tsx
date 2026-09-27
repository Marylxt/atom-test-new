"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Boxes, KeyRound, Mail, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/primitives";
import {
  AUTH_DISABLED,
  SUPABASE_CONFIGURED,
  sendMagicLink,
  signInWithPassword,
  signUpWithPassword,
} from "@/lib/supabase";
import { useSession } from "@/lib/use-session";
import { errorMessage } from "@/lib/utils";

type Mode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();
  const { session, loading, anonymous } = useSession();

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (anonymous || session) router.replace("/");
  }, [anonymous, session, router]);

  async function handleSubmit() {
    if (!email.trim() || !password) {
      setError("请填写邮箱和密码");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === "signin") {
        await signInWithPassword(email.trim(), password);
        router.replace("/");
      } else {
        const hasSession = await signUpWithPassword(email.trim(), password);
        if (hasSession) {
          router.replace("/");
        } else {
          setNotice("注册成功，请到邮箱点确认链接后再登录");
          setMode("signin");
        }
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleMagicLink() {
    if (!email.trim()) {
      setError("请先填写邮箱");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await sendMagicLink(email.trim(), `${window.location.origin}/`);
      setNotice("登录链接已发送，请查收邮件");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-5 py-10">
      <div className="w-full max-w-md">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-1.5 text-xs text-slate-500 transition hover:text-slate-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          返回首页
        </Link>

        <div className="surface p-6 sm:p-7">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-violet-500">
              <Boxes className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-semibold text-slate-100">
                {mode === "signin" ? "登录 Atoms Demo" : "注册新账号"}
              </h1>
              <p className="text-xs text-slate-500">Supabase Auth · 邮箱密码 / 魔法链接</p>
            </div>
          </div>

          {!SUPABASE_CONFIGURED && !AUTH_DISABLED ? (
            <div className="mb-5 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/[0.08] px-3 py-2.5 text-xs leading-relaxed text-amber-200">
              <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                还没有配置 Supabase：请在 <code className="font-mono">frontend/.env.local</code> 中填写
                NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY；
                如果只想在本地跑通流程，把前后端的 AUTH_DISABLED 都设为 true 即可免登录。
              </span>
            </div>
          ) : null}

          <div className="space-y-4">
            <div>
              <label className="label">邮箱</label>
              <Input
                type="email"
                autoComplete="email"
                value={email}
                placeholder="you@example.com"
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div>
              <label className="label">密码</label>
              <Input
                type="password"
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                placeholder="至少 6 位"
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void handleSubmit();
                }}
              />
            </div>
          </div>

          {error ? (
            <p className="mt-4 rounded-lg border border-rose-500/30 bg-rose-500/[0.08] px-3 py-2 text-xs text-rose-200">
              {error}
            </p>
          ) : null}
          {notice ? (
            <p className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/[0.08] px-3 py-2 text-xs text-emerald-200">
              {notice}
            </p>
          ) : null}

          <Button className="mt-5 w-full" size="lg" loading={busy || loading} onClick={handleSubmit}>
            <KeyRound className="h-4 w-4" />
            {mode === "signin" ? "登录" : "注册"}
          </Button>

          <Button
            className="mt-2 w-full"
            size="lg"
            variant="outline"
            disabled={busy}
            onClick={handleMagicLink}
          >
            <Mail className="h-4 w-4" />
            发送邮箱登录链接
          </Button>

          <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-500">
            {mode === "signin" ? "还没有账号？" : "已经有账号？"}
            <button
              type="button"
              className="font-medium text-brand-300 transition hover:text-brand-200"
              onClick={() => {
                setMode(mode === "signin" ? "signup" : "signin");
                setError(null);
                setNotice(null);
              }}
            >
              {mode === "signin" ? "去注册" : "去登录"}
            </button>
          </div>
        </div>

        <p className="mt-4 text-center text-[11px] leading-relaxed text-slate-600">
          登录态由 Supabase Auth 签发 JWT，前端保存在 localStorage，
          后端用 SUPABASE_JWT_SECRET 校验，不会接触到你的密码。
        </p>
      </div>
    </div>
  );
}
