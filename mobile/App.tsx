import { StatusBar } from "expo-status-bar";
import { useState } from "react";
import LoginScreen, { SprintRole } from "./screens/LoginScreen";
import StudentDashboard from "./screens/StudentDashboard";
import StaffDashboard from "./screens/StaffDashboard";

export default function App() {
  const [session, setSession] = useState<{ role: SprintRole; loginId: string } | null>(null);

  return (
    <>
      <StatusBar style="light" />
      {!session ? (
        <LoginScreen onLogin={setSession} />
      ) : session.role === "PROFESSOR" ? (
        <StaffDashboard loginId={session.loginId} onLogout={() => setSession(null)} />
      ) : (
        <StudentDashboard initialRegNo={session.loginId} onLogout={() => setSession(null)} />
      )}
    </>
  );
}
