import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Pressable,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
  Animated,
} from "react-native";
import * as Notifications from "expo-notifications";
import { authFetch } from "../lib/api";

/* ── Skeleton Loader ─────────────────────────────────────────
 * Gray pulsing boxes that show instantly while the GET request
 * runs, so Arun never sees a blank white screen.              */
function SkeletonBox({ width, height, style }: { width: number | string; height: number; style?: any }) {
  const opacity = useRef(new Animated.Value(0.3)).current;

  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.3, duration: 800, useNativeDriver: true }),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        { width, height, backgroundColor: "#E2E8F0", borderRadius: 10, opacity },
        style,
      ]}
    />
  );
}

function ResultSkeleton() {
  return (
    <View style={styles.resultCard}>
      {/* Score skeleton */}
      <View style={[styles.scoreHeader, { gap: 10 }]}>
        <SkeletonBox width={120} height={18} />
        <SkeletonBox width={160} height={52} />
      </View>
      {/* Question skeletons */}
      {[1, 2, 3].map((i) => (
        <View key={i} style={[styles.questionBox, { gap: 8 }]}>
          <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
            <SkeletonBox width={60} height={16} />
            <SkeletonBox width={50} height={16} />
          </View>
          <SkeletonBox width="100%" height={14} />
          <SkeletonBox width="80%" height={14} />
        </View>
      ))}
      {/* Feedback skeleton */}
      <View style={[styles.justificationBox, { gap: 8 }]}>
        <SkeletonBox width={180} height={18} />
        <SkeletonBox width="100%" height={14} />
        <SkeletonBox width="100%" height={14} />
        <SkeletonBox width="60%" height={14} />
      </View>
    </View>
  );
}


interface StudentDashboardProps {
  initialRegNo?: string;
  onLogout?: () => void;
}

export default function StudentDashboard({ initialRegNo = "", onLogout }: StudentDashboardProps) {
  const [regNo, setRegNo] = useState(initialRegNo);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (initialRegNo) {
      setRegNo(initialRegNo);
    }
  }, [initialRegNo]);

  const fetchResults = async () => {
    if (!regNo.trim()) {
      Alert.alert("Error", "Please enter your Registration Number.");
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      const response = await authFetch(`/api/results/${encodeURIComponent(regNo.trim())}`);
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

  useEffect(() => {
    const onReceived = Notifications.addNotificationReceivedListener((notification: Notifications.Notification) => {
      const type = notification.request.content.data?.type;
      if (type === "RESULT_PUBLISHED" || type === "APPEAL_RESOLVED") {
        if (regNo.trim()) {
          fetchResults();
        }
      }
    });

    const onResponse = Notifications.addNotificationResponseReceivedListener((response: Notifications.NotificationResponse) => {
      const type = response.notification.request.content.data?.type;
      if (type === "RESULT_PUBLISHED" || type === "APPEAL_RESOLVED") {
        if (regNo.trim()) {
          fetchResults();
        }
      }
    });

    return () => {
      onReceived.remove();
      onResponse.remove();
    };
  }, [regNo]);

  return (
    <ScrollView style={styles.container}>
      {/* ── Header ─────────────────────────────────────────── */}
      <View style={styles.header}>
        <Text style={styles.title}>AuraGrade Student</Text>
        <Text style={styles.subtitle}>Instant Result Portal</Text>
        {onLogout && (
          <Pressable onPress={onLogout} style={styles.logoutBtn}>
            <Text style={styles.logoutText}>Switch Role</Text>
          </Pressable>
        )}
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

      {/* ── Skeleton Loader (while fetching) ──────────────── */}
      {loading && !result && <ResultSkeleton />}

      {/* ── Results Card ───────────────────────────────────── */}
      {result && !loading && (
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
  logoutBtn: {
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#334155",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: "#1E293B",
  },
  logoutText: {
    color: "#CBD5E1",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
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
