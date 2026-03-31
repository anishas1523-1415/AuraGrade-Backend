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
import * as SecureStore from "expo-secure-store";
import { supabase } from "../lib/supabase";

interface LoginScreenProps {
  onLoginSuccess: () => Promise<void>;
}

export default function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password.trim()) {
      Alert.alert("Error", "Please enter both institutional email and password.");
      return;
    }

    setLoading(true);

    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: normalizedEmail,
        password,
      });

      if (error) {
        throw error;
      }

      if (data.session) {
        // Explicitly vault tokens for downstream flows that need direct token access.
        await SecureStore.setItemAsync("access_token", data.session.access_token);
        await SecureStore.setItemAsync("refresh_token", data.session.refresh_token);
      }

      await onLoginSuccess();
    } catch (error: any) {
      Alert.alert("Authentication Failed", error?.message || "Unable to sign in.");
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

      <TouchableOpacity
        style={[styles.button, loading && { opacity: 0.7 }]}
        onPress={handleLogin}
        activeOpacity={0.85}
        disabled={loading}
      >
        {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Authenticate</Text>}
      </TouchableOpacity>

      <Text style={styles.hint}>Secure institutional access via Supabase.</Text>
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
