import React, { useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
} from "react-native";

const API_BASE = process.env.EXPO_PUBLIC_API_URL || "http://192.168.0.14:8000";

interface PendingAppeal {
  id: string;
  ai_score: number;
  confidence: number;
  feedback: string[];
  appeal_reason: string;
  prof_status: string;
  graded_at: string;
  students: { reg_no: string; name: string };
  assessments: { id: string; subject: string; title: string };
}

interface StaffDashboardProps {
  loginId: string;
  onLogout: () => void;
}

export default function StaffDashboard({ loginId, onLogout }: StaffDashboardProps) {
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [appeals, setAppeals] = useState<PendingAppeal[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [newScore, setNewScore] = useState("");
  const [professorNotes, setProfessorNotes] = useState("");

  const selected = useMemo(
    () => appeals.find((item) => item.id === selectedId) || null,
    [appeals, selectedId],
  );

  const fetchPending = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/staff/appeals/pending?limit=100`);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "Failed to load pending appeals");
      }
      setAppeals(Array.isArray(data) ? data : []);
      if (!selectedId && Array.isArray(data) && data.length > 0) {
        setSelectedId(data[0].id);
      }
    } catch (err: any) {
      Alert.alert("Load Error", err?.message || "Unable to fetch pending appeals.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPending();
  }, []);

  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchPending();
    }, 25000);

    return () => clearInterval(intervalId);
  }, []);

  const resolveAppeal = async () => {
    if (!selected) {
      Alert.alert("No Selection", "Choose an appeal card first.");
      return;
    }

    const parsedScore = Number(newScore);
    if (!Number.isFinite(parsedScore)) {
      Alert.alert("Invalid Score", "Enter a valid numeric score.");
      return;
    }

    if (!professorNotes.trim()) {
      Alert.alert("Professor Notes Required", "Add professor notes before resealing.");
      return;
    }

    setResolving(true);
    try {
      const res = await fetch(`${API_BASE}/api/staff/appeals/${selected.id}/resolve`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          new_score: parsedScore,
          professor_notes: professorNotes.trim(),
          resolved_by: loginId,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "Failed to resolve appeal");
      }

      Alert.alert(
        "Appeal Resolved",
        `Score updated and resealed.\nTransaction Hash: ${data.transaction_hash || "N/A"}`,
      );

      setNewScore("");
      setProfessorNotes("");
      setSelectedId(null);
      await fetchPending();
    } catch (err: any) {
      Alert.alert("Resolve Error", err?.message || "Unable to resolve appeal.");
    } finally {
      setResolving(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>AuraGrade Staff</Text>
          <Text style={styles.subtitle}>Appeal Resolution Engine · {loginId}</Text>
        </View>
        <TouchableOpacity onPress={onLogout} style={styles.switchBtn} activeOpacity={0.85}>
          <Text style={styles.switchText}>Switch Role</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.centerState}>
          <ActivityIndicator color="#38BDF8" />
          <Text style={styles.stateText}>Loading pending appeals…</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Triage Dashboard (APPEAL_PENDING)</Text>
            {appeals.length === 0 ? (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyText}>No pending appeals right now.</Text>
              </View>
            ) : (
              appeals.map((item) => (
                <TouchableOpacity
                  key={item.id}
                  style={[styles.appealCard, selectedId === item.id && styles.appealCardActive]}
                  onPress={() => {
                    setSelectedId(item.id);
                    setNewScore(String(item.ai_score));
                  }}
                  activeOpacity={0.85}
                >
                  <View style={styles.rowBetween}>
                    <Text style={styles.courseText}>{item.assessments?.subject || "Course"}</Text>
                    <View style={styles.badgeRed}>
                      <Text style={styles.badgeText}>Needs Review</Text>
                    </View>
                  </View>
                  <Text style={styles.metaText}>
                    {item.students?.reg_no || "UNKNOWN"} · {item.students?.name || "Student"}
                  </Text>
                  <Text style={styles.metaText}>Current Score: {item.ai_score}</Text>
                </TouchableOpacity>
              ))
            )}
          </View>

          {selected && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Comparison View</Text>

              <View style={styles.compareBox}>
                <Text style={styles.compareTitle}>Student Argument</Text>
                <Text style={styles.compareBody}>{selected.appeal_reason || "No appeal text provided."}</Text>
              </View>

              <View style={styles.compareBox}>
                <Text style={styles.compareTitle}>AI Original Feedback Trace</Text>
                {(selected.feedback || []).length > 0 ? (
                  selected.feedback.map((line, i) => (
                    <Text key={`${selected.id}-fb-${i}`} style={styles.feedbackLine}>
                      • {line}
                    </Text>
                  ))
                ) : (
                  <Text style={styles.compareBody}>No AI feedback trace available.</Text>
                )}
              </View>

              <View style={styles.compareBox}>
                <Text style={styles.compareTitle}>Override & Reseal</Text>
                <TextInput
                  style={styles.input}
                  value={newScore}
                  onChangeText={setNewScore}
                  keyboardType="numeric"
                  placeholder="New Score"
                  placeholderTextColor="#94A3B8"
                />
                <TextInput
                  style={[styles.input, styles.notesInput]}
                  value={professorNotes}
                  onChangeText={setProfessorNotes}
                  multiline
                  placeholder="Professor notes (required)"
                  placeholderTextColor="#94A3B8"
                />

                <TouchableOpacity
                  onPress={resolveAppeal}
                  disabled={resolving}
                  style={[styles.resolveBtn, resolving && { opacity: 0.7 }]}
                  activeOpacity={0.85}
                >
                  {resolving ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.resolveBtnText}>Override & Reseal</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0B1120",
  },
  header: {
    paddingTop: 54,
    paddingHorizontal: 18,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: "#1E293B",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  title: {
    color: "#E2E8F0",
    fontSize: 24,
    fontWeight: "900",
  },
  subtitle: {
    color: "#94A3B8",
    marginTop: 3,
    fontSize: 11,
  },
  switchBtn: {
    borderWidth: 1,
    borderColor: "#334155",
    borderRadius: 999,
    paddingVertical: 7,
    paddingHorizontal: 12,
    backgroundColor: "#111827",
  },
  switchText: {
    color: "#CBD5E1",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  content: {
    padding: 14,
    paddingBottom: 34,
    gap: 12,
  },
  section: {
    gap: 10,
  },
  sectionTitle: {
    color: "#CBD5E1",
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  appealCard: {
    backgroundColor: "#111827",
    borderWidth: 1,
    borderColor: "#1E293B",
    borderRadius: 12,
    padding: 12,
    gap: 4,
  },
  appealCardActive: {
    borderColor: "#38BDF8",
    backgroundColor: "#0F172A",
  },
  rowBetween: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  courseText: {
    color: "#E2E8F0",
    fontSize: 14,
    fontWeight: "700",
  },
  metaText: {
    color: "#94A3B8",
    fontSize: 12,
  },
  badgeRed: {
    backgroundColor: "#7F1D1D",
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  badgeText: {
    color: "#FCA5A5",
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  compareBox: {
    backgroundColor: "#111827",
    borderWidth: 1,
    borderColor: "#1E293B",
    borderRadius: 12,
    padding: 12,
    gap: 8,
  },
  compareTitle: {
    color: "#C7D2FE",
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  compareBody: {
    color: "#E2E8F0",
    fontSize: 13,
    lineHeight: 19,
  },
  feedbackLine: {
    color: "#CBD5E1",
    fontSize: 12,
    lineHeight: 18,
  },
  input: {
    borderWidth: 1,
    borderColor: "#334155",
    backgroundColor: "#0F172A",
    color: "#E2E8F0",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  notesInput: {
    minHeight: 100,
    textAlignVertical: "top",
  },
  resolveBtn: {
    marginTop: 4,
    backgroundColor: "#2563EB",
    borderRadius: 10,
    alignItems: "center",
    paddingVertical: 12,
  },
  resolveBtnText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  centerState: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
  },
  stateText: {
    color: "#94A3B8",
    fontSize: 13,
  },
  emptyCard: {
    borderWidth: 1,
    borderColor: "#1E293B",
    borderRadius: 12,
    padding: 14,
    backgroundColor: "#111827",
  },
  emptyText: {
    color: "#94A3B8",
    fontSize: 13,
  },
});
