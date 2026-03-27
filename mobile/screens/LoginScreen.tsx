import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
} from "react-native";
import { supabase } from "../lib/supabase";
import { authFetch } from "../lib/api";

interface LoginScreenProps {
  onLoginSuccess: () => Promise<void>;
}

export default function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [dob, setDob] = useState("");
  const [loading, setLoading] = useState(false);

  const normalizeDobInput = (value: string): string | null => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }

    const normalized = trimmed.replace(/[./]/g, "-");
    const isoMatch = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (isoMatch) {
      return normalized;
    }

    const dmyMatch = normalized.match(/^(\d{2})-(\d{2})-(\d{4})$/);
    if (dmyMatch) {
      const [, day, month, year] = dmyMatch;
      return `${year}-${month}-${day}`;
    }

    return null;
  };

  const handleLogin = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedDob = normalizeDobInput(dob);

    if (!normalizedEmail || !password.trim()) {
      Alert.alert("Login Required", "Enter email and password.");
      return;
    }

    if (dob.trim() && !normalizedDob) {
      Alert.alert("Invalid DOB", "Use DOB as YYYY-MM-DD or DD-MM-YYYY.");
      return;
    }

    setLoading(true);

    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: normalizedEmail,
        password,
      });

      if (error) {
        throw error;
      }

      const verifyRes = await authFetch("/api/auth/verify-student-dob", {
        method: "POST",
        body: JSON.stringify({ dob: normalizedDob || "" }),
      });

      if (!verifyRes.ok) {
        const verifyPayload = await verifyRes.json().catch(() => ({}));
        await supabase.auth.signOut();
        throw new Error(verifyPayload?.detail || "DOB verification failed.");
      }

      await onLoginSuccess();
    } catch (error: any) {
      Alert.alert("Login Failed", error?.message || "Unable to sign in.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>AuraGrade</Text>
      <Text style={styles.subtitle}>Secure Sign In</Text>

      <TextInput
        style={styles.input}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        placeholder="college-mail@example.edu"
        placeholderTextColor="#94A3B8"
      />

      <TextInput
        style={[styles.input, { marginTop: 10 }]}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        placeholder="Password"
        placeholderTextColor="#94A3B8"
      />

      <TextInput
        style={[styles.input, { marginTop: 10 }]}
        value={dob}
        onChangeText={setDob}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="DOB (YYYY-MM-DD or DD-MM-YYYY)"
        placeholderTextColor="#94A3B8"
      />

      <TouchableOpacity
        style={[styles.button, loading && { opacity: 0.7 }]}
        onPress={handleLogin}
        activeOpacity={0.85}
        disabled={loading}
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Continue</Text>}
      </TouchableOpacity>

      <Text style={styles.hint}>Students: add DOB. Staff: DOB optional.</Text>
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
