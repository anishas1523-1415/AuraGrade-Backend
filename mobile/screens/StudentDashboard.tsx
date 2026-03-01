import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
} from "react-native";

// ⚠️  Replace with your computer's local IPv4 address.
//     Run `ipconfig` (Windows) or `ifconfig` (Mac/Linux) to find it.
//     Expo Go on a physical phone CANNOT reach "localhost" — it points to the phone itself.
const API_BASE = "http://192.168.0.14:8000";

export default function StudentDashboard() {
  const [regNo, setRegNo] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  const fetchResults = async () => {
    if (!regNo.trim()) {
      Alert.alert("Error", "Please enter your Registration Number.");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/results/${regNo.trim()}`
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not fetch results.");
      }

      setResult(data.data);
    } catch (error: any) {
      Alert.alert("Result Not Found", error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView style={styles.container}>
      {/* ── Header ─────────────────────────────────────────── */}
      <View style={styles.header}>
        <Text style={styles.title}>AuraGrade Student</Text>
        <Text style={styles.subtitle}>Instant Result Portal</Text>
      </View>

      {/* ── Search Card ────────────────────────────────────── */}
      <View style={styles.searchCard}>
        <TextInput
          style={styles.input}
          placeholder="Enter Registration No. (e.g., AD011)"
          placeholderTextColor="#94A3B8"
          value={regNo}
          onChangeText={setRegNo}
          autoCapitalize="characters"
          returnKeyType="search"
          onSubmitEditing={fetchResults}
        />
        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={fetchResults}
          disabled={loading}
          activeOpacity={0.8}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>Get Results</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* ── Results Card ───────────────────────────────────── */}
      {result && (
        <View style={styles.resultCard}>
          {/* Score */}
          <View style={styles.scoreHeader}>
            <Text style={styles.scoreLabel}>Final Score</Text>
            <Text style={styles.scoreValue}>
              {result.score ?? result.total_marks ?? "—"} / 15
            </Text>
          </View>

          {/* Penalties */}
          {result.penalties_applied && result.penalties_applied.length > 0 && (
            <View style={styles.penaltyBox}>
              <Text style={styles.penaltyTitle}>🚨 Marks Deducted</Text>
              {result.penalties_applied.map(
                (penalty: string, index: number) => (
                  <Text key={index} style={styles.penaltyText}>
                    • {penalty}
                  </Text>
                )
              )}
            </View>
          )}

          {/* Per-Question Breakdown (if available) */}
          {result.questions &&
            result.questions.length > 0 &&
            result.questions.map((q: any, idx: number) => (
              <View key={idx} style={styles.questionBox}>
                <View style={styles.questionHeader}>
                  <Text style={styles.questionTitle}>
                    Q{q.question_number ?? idx + 1}
                  </Text>
                  <Text style={styles.questionMarks}>
                    {q.marks_awarded ?? "?"} / {q.max_marks ?? "?"}
                  </Text>
                </View>
                {q.feedback && (
                  <Text style={styles.questionFeedback}>{q.feedback}</Text>
                )}
              </View>
            ))}

          {/* AI Justification / Feedback */}
          {(result.justification_note || result.audit_justification) && (
            <View style={styles.justificationBox}>
              <Text style={styles.justificationTitle}>
                Professor AI Feedback
              </Text>
              <Text style={styles.justificationText}>
                {result.justification_note || result.audit_justification}
              </Text>
            </View>
          )}
        </View>
      )}

      {/* Bottom spacer for safe scrolling */}
      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

/* ── Styles ──────────────────────────────────────────────────────── */

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F8FAFC",
  },
  header: {
    backgroundColor: "#0F172A",
    padding: 30,
    paddingTop: 60,
    alignItems: "center",
  },
  title: {
    color: "white",
    fontSize: 24,
    fontWeight: "bold",
  },
  subtitle: {
    color: "#94A3B8",
    fontSize: 14,
    marginTop: 5,
  },

  // Search
  searchCard: {
    margin: 20,
    backgroundColor: "white",
    padding: 20,
    borderRadius: 15,
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowRadius: 10,
    elevation: 5,
  },
  input: {
    backgroundColor: "#F1F5F9",
    padding: 15,
    borderRadius: 10,
    fontSize: 16,
    marginBottom: 15,
    borderWidth: 1,
    borderColor: "#E2E8F0",
    color: "#0F172A",
  },
  button: {
    backgroundColor: "#2563EB",
    padding: 15,
    borderRadius: 10,
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: "white",
    fontSize: 16,
    fontWeight: "bold",
  },

  // Results
  resultCard: {
    margin: 20,
    marginTop: 0,
  },
  scoreHeader: {
    backgroundColor: "white",
    padding: 25,
    borderRadius: 15,
    alignItems: "center",
    marginBottom: 15,
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 3,
  },
  scoreLabel: {
    color: "#64748B",
    fontSize: 16,
    fontWeight: "600",
  },
  scoreValue: {
    color: "#10B981",
    fontSize: 48,
    fontWeight: "900",
    marginTop: 5,
  },

  // Penalties
  penaltyBox: {
    backgroundColor: "#FEF2F2",
    padding: 20,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: "#FECACA",
    marginBottom: 15,
  },
  penaltyTitle: {
    color: "#991B1B",
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 10,
  },
  penaltyText: {
    color: "#B91C1C",
    fontSize: 14,
    marginBottom: 5,
    lineHeight: 20,
  },

  // Per-question breakdown
  questionBox: {
    backgroundColor: "white",
    padding: 16,
    borderRadius: 12,
    marginBottom: 10,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  questionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  questionTitle: {
    fontSize: 15,
    fontWeight: "700",
    color: "#334155",
  },
  questionMarks: {
    fontSize: 15,
    fontWeight: "700",
    color: "#2563EB",
  },
  questionFeedback: {
    fontSize: 13,
    color: "#64748B",
    lineHeight: 19,
  },

  // Justification / AI feedback
  justificationBox: {
    backgroundColor: "white",
    padding: 20,
    borderRadius: 15,
    shadowColor: "#000",
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 2,
  },
  justificationTitle: {
    color: "#334155",
    fontSize: 16,
    fontWeight: "bold",
    marginBottom: 10,
  },
  justificationText: {
    color: "#475569",
    fontSize: 15,
    lineHeight: 22,
  },
});
