"use client";

import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { AUTH_DISABLED, getSupabase, getSession } from "./supabase";

interface SessionState {
  session: Session | null;
  loading: boolean;
  /** 是否处于「免登录」模式 */
  anonymous: boolean;
}

/** 订阅 Supabase 登录态。 */
export function useSession(): SessionState {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(!AUTH_DISABLED);

  useEffect(() => {
    if (AUTH_DISABLED) {
      setLoading(false);
      return;
    }

    let alive = true;
    void getSession().then((value) => {
      if (!alive) return;
      setSession(value);
      setLoading(false);
    });

    const supabase = getSupabase();
    const subscription = supabase?.auth.onAuthStateChange((_event, nextSession) => {
      if (!alive) return;
      setSession(nextSession);
      setLoading(false);
    });

    return () => {
      alive = false;
      subscription?.data.subscription.unsubscribe();
    };
  }, []);

  return { session, loading, anonymous: AUTH_DISABLED };
}
