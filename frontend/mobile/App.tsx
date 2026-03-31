import { StatusBar } from "expo-status-bar";
import { useEffect, useState } from "react";
import LoginScreen from "./screens/LoginScreen";
import StudentDashboard from "./screens/StudentDashboard";
import StaffDashboard from "./screens/StaffDashboard";
import { supabase } from "./lib/supabase";
import { authFetch } from "./lib/api";
import { registerForPushNotifications, registerPushTokenOnBackend } from "./lib/notifications";

type AppRole = "STUDENT" | "PROFESSOR";

type AppSession = {
  role: AppRole;
  loginId: string;
  regNo?: string;
};

export default function App() {
  const [session, setSession] = useState<AppSession | null>(null);
  const [hydrating, setHydrating] = useState(true);

  const hydrateFromBackend = async () => {
    const { data: sessionData } = await supabase.auth.getSession();
    const activeSession = sessionData.session;

    if (!activeSession) {
      setSession(null);
      setHydrating(false);
      return;
    }

    const meRes = await authFetch("/api/auth/me");
    if (!meRes.ok) {
      await supabase.auth.signOut();
      setSession(null);
      setHydrating(false);
      return;
    }

    const mePayload = await meRes.json();
    const roleFromProfile = mePayload?.user?.role;
    const appRole: AppRole = roleFromProfile === "EVALUATOR" || roleFromProfile === "HOD_AUDITOR" || roleFromProfile === "ADMIN_COE"
      ? "PROFESSOR"
      : "STUDENT";

    const regNo = mePayload?.student?.reg_no || undefined;
    const loginId = regNo || mePayload?.user?.email || activeSession.user?.email || "USER";

    setSession({
      role: appRole,
      loginId,
      regNo,
    });

    const pushToken = await registerForPushNotifications();
    if (pushToken) {
      await registerPushTokenOnBackend(pushToken, appRole, regNo);
    }

    setHydrating(false);
  };

  useEffect(() => {
    hydrateFromBackend();

    const { data: authSubscription } = supabase.auth.onAuthStateChange(() => {
      hydrateFromBackend();
    });

    return () => {
      authSubscription.subscription.unsubscribe();
    };
  }, []);

  const handleLogout = async () => {
    await supabase.auth.signOut();
    setSession(null);
  };

  if (hydrating) {
    return <StatusBar style="light" />;
  }

  return (
    <>
      <StatusBar style="light" />
      {!session ? (
        <LoginScreen onLoginSuccess={hydrateFromBackend} />
      ) : session.role === "PROFESSOR" ? (
        <StaffDashboard loginId={session.loginId} onLogout={handleLogout} />
      ) : (
        <StudentDashboard initialRegNo={session.regNo || session.loginId} onLogout={handleLogout} />
      )}
    </>
  );
}
