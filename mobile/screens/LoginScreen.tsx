import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
} from "react-native";

export type SprintRole = "STUDENT" | "PROFESSOR";

interface LoginScreenProps {
  onLogin: (payload: { role: SprintRole; loginId: string }) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [loginId, setLoginId] = useState("");

  const handleLogin = () => {
    const trimmed = loginId.trim().toUpperCase();
    if (!trimmed) {
      Alert.alert("Login Required", "Enter your ID to continue.");
      return;
    }

    if (trimmed.startsWith("PROF-")) {
      onLogin({ role: "PROFESSOR", loginId: trimmed });
      return;
    }

    if (trimmed.startsWith("AIDS-")) {
      onLogin({ role: "STUDENT", loginId: trimmed });
      return;
    }

    Alert.alert(
      "Invalid ID Prefix",
      "Use AIDS-... for Student or PROF-... for Professor (Sprint RBAC mode).",
    );
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>AuraGrade</Text>
      <Text style={styles.subtitle}>Unified Login (Sprint RBAC)</Text>

      <TextInput
        style={styles.input}
        value={loginId}
        onChangeText={setLoginId}
        autoCapitalize="characters"
        placeholder="AIDS-2026-001 or PROF-AIDS-01"
        placeholderTextColor="#94A3B8"
      />

      <TouchableOpacity style={styles.button} onPress={handleLogin} activeOpacity={0.85}>
        <Text style={styles.buttonText}>Continue</Text>
      </TouchableOpacity>

      <Text style={styles.hint}>Student: AIDS-... · Professor: PROF-...</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0F172A",
    padding: 24,
    justifyContent: "center",
  },
  title: {
    fontSize: 34,
    color: "#E2E8F0",
    fontWeight: "900",
    textAlign: "center",
  },
  subtitle: {
    marginTop: 6,
    color: "#94A3B8",
    textAlign: "center",
    marginBottom: 22,
  },
  input: {
    backgroundColor: "#1E293B",
    borderWidth: 1,
    borderColor: "#334155",
    color: "#E2E8F0",
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    fontSize: 16,
  },
  button: {
    marginTop: 14,
    backgroundColor: "#2563EB",
    borderRadius: 12,
    alignItems: "center",
    paddingVertical: 13,
  },
  buttonText: {
    color: "#fff",
    fontWeight: "800",
    fontSize: 16,
  },
  hint: {
    marginTop: 12,
    textAlign: "center",
    color: "#64748B",
    fontSize: 12,
  },
});
