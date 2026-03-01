import { StatusBar } from "expo-status-bar";
import StudentDashboard from "./screens/StudentDashboard";

export default function App() {
  return (
    <>
      <StatusBar style="light" />
      <StudentDashboard />
    </>
  );
}
