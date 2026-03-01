"use client";

import React, { useState, useRef, useEffect } from "react";
import imageCompression from "browser-image-compression";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Cpu,
  Database,
  UploadCloud,
  Zap,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Send,
  FileText,
  Gavel,
  ShieldAlert,
  AlertTriangle,
  GraduationCap,
  Settings2,
  Shield,
  Scan,
} from "lucide-react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { UserBadge } from "@/components/UserBadge";
import { useAuth } from "@/lib/auth-context";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import { AnnotationOverlay, Annotation } from "@/components/AnnotationOverlay";
import { AuraVoiceControl, VoiceCommand } from "@/components/AuraVoiceControl";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GradeResult {
  score: number;
  confidence: number;
  feedback: string[];
  is_flagged: boolean;
  saved_to_db?: boolean;
  grade_id?: string | null;
}

interface Student {
  id: string;
  reg_no: string;
  name: string;
  email: string;
}

interface Assessment {
  id: string;
  subject: string;
  title: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const GradingDashboard = () => {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const authFetch = useAuthFetch();

  /* ---------- core grading state ---------- */
  const [isGrading, setIsGrading] = useState(false);
  const [feedback, setFeedback] = useState<string[]>([]);
  const [score, setScore] = useState<number | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [isFlagged, setIsFlagged] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const feedbackEndRef = useRef<HTMLDivElement>(null);

  /* ---------- annotation overlay state ---------- */
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  /* ---------- pass tracking for Progress HUD ---------- */
  const [currentPass, setCurrentPass] = useState(0); // 0: Idle, 1: Grader, 2: Auditor, 3: Done

  /* ---------- DB / Supabase state ---------- */
  const [gradeId, setGradeId] = useState<string | null>(null);
  const [savedToDb, setSavedToDb] = useState(false);
  const [profStatus, setProfStatus] = useState<string>("Pending");
  const [studentRegNo, setStudentRegNo] = useState("");
  const [students, setStudents] = useState<Student[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessment, setSelectedAssessment] = useState("");
  const [appealReason, setAppealReason] = useState("");
  const [showAppealInput, setShowAppealInput] = useState(false);
  const [dbConnected, setDbConnected] = useState(false);

  /* ---------- auto-scroll feedback ---------- */
  useEffect(() => {
    feedbackEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [feedback]);

  /* ---------- load students & assessments ---------- */
  useEffect(() => {
    const loadData = async () => {
      try {
        const [studentsRes, assessmentsRes] = await Promise.all([
          fetch(`${API_URL}/api/students`),
          fetch(`${API_URL}/api/assessments`),
        ]);
        if (studentsRes.ok) {
          const s = await studentsRes.json();
          setStudents(s);
          setDbConnected(true);
        }
        if (assessmentsRes.ok) {
          const a = await assessmentsRes.json();
          setAssessments(a);
          if (a.length > 0) setSelectedAssessment(a[0].id);
        }
      } catch {
        setDbConnected(false);
      }
    };
    loadData();
  }, []);

  /* ---------------------------------------------------------------- */
  /*  Handlers                                                         */
  /* ---------------------------------------------------------------- */

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setFeedback([]);
      setScore(null);
      setConfidence(null);
      setIsFlagged(false);
      setError(null);
      setIsGrading(false);
      setGradeId(null);
      setSavedToDb(false);
      setProfStatus("Pending");
      setShowAppealInput(false);
      setAnnotations([]);
    }
  };

  const startGrading = async () => {
    if (!selectedFile) {
      runDemoSimulation();
      return;
    }

    setIsGrading(true);
    setFeedback([]);
    setScore(null);
    setConfidence(null);
    setIsFlagged(false);
    setError(null);
    setGradeId(null);
    setSavedToDb(false);
    setProfStatus("Pending");
    setAnnotations([]);
    setCurrentPass(0);

    try {
      // ── Client-side image compression ──────────────────────────
      let uploadFile: File = selectedFile;
      try {
        const compressed = await imageCompression(selectedFile, {
          maxSizeMB: 0.5,
          maxWidthOrHeight: 1920,
          useWebWorker: true,
        });
        console.log(
          `📦 Compressed: ${(selectedFile.size / 1024).toFixed(0)}KB → ${(compressed.size / 1024).toFixed(0)}KB`
        );
        uploadFile = compressed;
      } catch (compErr) {
        console.warn("⚠️ Compression failed, uploading original:", compErr);
      }

      const formData = new FormData();
      formData.append("file", uploadFile);

      let url = `${API_URL}/api/grade/stream`;
      const params = new URLSearchParams();
      if (studentRegNo) params.set("student_reg_no", studentRegNo);
      if (selectedAssessment) params.set("assessment_id", selectedAssessment);
      if (params.toString()) url += `?${params.toString()}`;

      // POST with fetch, then read the response body as an SSE stream
      const response = await fetch(url, { method: "POST", body: formData });

      if (!response.ok) {
        const errData = await response
          .json()
          .catch(() => ({ detail: "Server error" }));
        throw new Error(errData.detail || `HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No readable stream in response");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse complete SSE frames (separated by double newlines)
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || ""; // keep incomplete tail

        for (const frame of frames) {
          if (!frame.trim()) continue;

          let eventType = "message";
          let eventData = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) {
              eventType = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.slice(6);
            }
          }

          if (!eventData) continue;

          try {
            const payload = JSON.parse(eventData);
            handleSSEEvent(eventType, payload);
          } catch {
            // non-JSON data line — skip
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      setFeedback((prev) => [...prev, `❌ Error: ${message}`]);
    }
  };

  /** Handle a single parsed SSE event from the agentic pipeline */
  const handleSSEEvent = (
    eventType: string,
    payload: Record<string, unknown>,
  ) => {
    switch (eventType) {
      case "step":
        setFeedback((prev) => [
          ...prev,
          `${payload.icon ?? "⚡"} ${payload.text}`,
        ]);
        break;

      case "pass1":
        setCurrentPass(1);
        // Show Pass 1 feedback items
        if (Array.isArray(payload.feedback)) {
          (payload.feedback as string[]).forEach((text) => {
            const icon =
              text.toLowerCase().includes("missing") ||
              text.toLowerCase().includes("incorrect")
                ? "⚠️"
                : "✅";
            setFeedback((prev) => [...prev, `${icon} ${text}`]);
          });
        }
        break;

      case "pass1_partial": {
        // Incremental annotation streaming — boxes appear one-by-one
        setCurrentPass(1);
        const newAnnotations = payload.new_annotations as Annotation[];
        if (Array.isArray(newAnnotations)) {
          setAnnotations((prev) => [...prev, ...newAnnotations]);
        }
        break;
      }

      case "rag":
        if (payload.status === "retrieved") {
          setFeedback((prev) => [
            ...prev,
            `📚 Retrieved ${payload.chunks} model-answer chunks from vector store`,
          ]);
        }
        break;

      case "pass2":
        // Show any new / corrected feedback items from the audit pass
        if (Array.isArray(payload.feedback)) {
          (payload.feedback as string[]).forEach((text) => {
            const icon = text.toLowerCase().includes("correct")
              ? "✅"
              : "🔬";
            setFeedback((prev) => [...prev, `${icon} ${text}`]);
          });
        }
        if (payload.audit_notes) {
          setFeedback((prev) => [
            ...prev,
            `📝 Audit: ${payload.audit_notes}`,
          ]);
        }
        break;

      case "result": {
        const s = payload.score as number;
        const c = payload.confidence as number;
        const flagged = payload.is_flagged as boolean;
        setScore(s);
        setConfidence(c);
        setIsFlagged(flagged);
        setFeedback((prev) => [
          ...prev,
          `💯 Final Score: ${s}/10`,
        ]);
        if (payload.self_corrected) {
          setFeedback((prev) => [
            ...prev,
            `✏️ Self-corrected: ${payload.pass1_score} → ${payload.pass2_score}`,
          ]);
        }
        if (flagged) {
          setFeedback((prev) => [
            ...prev,
            "🚩 Flagged for manual review.",
          ]);
        }
        break;
      }

      case "db":
        if (payload.saved) {
          setSavedToDb(true);
          setGradeId((payload.grade_id as string) ?? null);
          setFeedback((prev) => [...prev, "💾 Grade saved to Supabase."]);
        }
        break;

      case "annotations": {
        setCurrentPass(1);
        const annots = payload.annotations as Annotation[];
        if (Array.isArray(annots)) {
          setAnnotations(annots);
          setFeedback((prev) => [
            ...prev,
            `🎯 ${annots.length} annotation region(s) mapped onto script`,
          ]);
        }
        break;
      }

      case "annotation_review":
      case "pass2_audit": {
        // Pass 2 is reviewing these annotations — turn them yellow
        setCurrentPass(2);
        const reviewIds = (payload.ids ?? payload.auditing_ids) as string[];
        if (Array.isArray(reviewIds)) {
          setAnnotations((prev) =>
            prev.map((a) =>
              reviewIds.includes(a.id)
                ? { ...a, reviewState: "reviewing" as const }
                : a,
            ),
          );
          setFeedback((prev) => [
            ...prev,
            `🔬 Pass 2 auditing ${reviewIds.length} annotation(s)…`,
          ]);
        }
        break;
      }

      case "annotation_verdict":
      case "pass2_result": {
        // Pass 2 verdicts — turn boxes green/red/purple
        setCurrentPass(3);
        // If pass2_result provides final_pass2_annotations, use them directly
        if (payload.final_pass2_annotations) {
          setAnnotations(payload.final_pass2_annotations as Annotation[]);
          break;
        }
        const verdicts = payload.verdicts as Array<{
          id: string;
          verdict: string;
          adjusted_points?: number | null;
          note?: string;
        }>;
        if (Array.isArray(verdicts)) {
          setAnnotations((prev) =>
            prev.map((a) => {
              const v = verdicts.find((vd) => vd.id === a.id);
              if (!v) return { ...a, reviewState: "confirmed" as const };
              const stateMap: Record<string, Annotation["reviewState"]> = {
                confirmed: "confirmed",
                adjusted: "adjusted",
                rejected: "rejected",
              };
              return {
                ...a,
                reviewState: stateMap[v.verdict] || "confirmed",
                points: v.adjusted_points != null ? v.adjusted_points : a.points,
                verdictNote: v.note || undefined,
              };
            }),
          );
          const adjusted = verdicts.filter((v) => v.verdict !== "confirmed").length;
          setFeedback((prev) => [
            ...prev,
            adjusted > 0
              ? `⚖️ Pass 2 adjusted ${adjusted} annotation(s)`
              : `✅ Pass 2 confirmed all annotations`,
          ]);
        }
        break;
      }

      case "diagram_detect":
        if (payload.has_diagram) {
          const diagrams = (payload.diagrams as Array<{ type: string }>) || [];
          const types = diagrams.map((d) => d.type).join(", ");
          setFeedback((prev) => [
            ...prev,
            `📐 Detected ${diagrams.length} diagram(s): ${types}`,
          ]);
        }
        break;

      case "diagram_result":
        if (payload.has_diagram && payload.mermaid_code) {
          const dScore = payload.logic_score as number;
          const dValid = payload.is_valid as boolean;
          const dType = payload.diagram_type as string;
          if (dValid) {
            setFeedback((prev) => [
              ...prev,
              `✅ Diagram (${dType}) logic validated — score: ${dScore}/10`,
            ]);
          } else {
            const flaws = (payload.logic_flaws as Array<{ flaw: string }>) || [];
            setFeedback((prev) => [
              ...prev,
              `⚠️ Diagram (${dType}) has ${flaws.length} logic flaw(s) — score: ${dScore}/10`,
            ]);
          }
          if (payload.mermaid_code) {
            setFeedback((prev) => [
              ...prev,
              `💻 Mermaid.js code generated for ${dType} diagram`,
            ]);
          }
        }
        break;

      case "error":
        setError(payload.message as string);
        setFeedback((prev) => [
          ...prev,
          `❌ ${payload.message}`,
        ]);
        break;

      case "done":
        setCurrentPass(0);
        break;
    }
  };

  const handleApprove = async () => {
    if (!gradeId) return;
    try {
      const res = await authFetch(`${API_URL}/api/grades/${gradeId}/approve`, {
        method: "PUT",
      });
      if (res.ok) {
        setProfStatus("Approved");
        setFeedback((prev) => [...prev, "✅ Grade approved by professor."]);
      } else {
        const body = await res.json().catch(() => null);
        const detail = body?.detail || `Server error (${res.status})`;
        setFeedback((prev) => [...prev, `❌ Failed to approve grade: ${detail}`]);
      }
    } catch {
      setFeedback((prev) => [...prev, "❌ Failed to approve grade."]);
    }
  };

  const handleAppeal = async () => {
    if (!gradeId || !appealReason.trim()) return;
    try {
      const qp = new URLSearchParams({ reason: appealReason });
      const res = await authFetch(`${API_URL}/api/grades/${gradeId}/appeal?${qp}`, {
        method: "PUT",
      });
      if (res.ok) {
        setProfStatus("Flagged");
        setShowAppealInput(false);
        setAppealReason("");
        setFeedback((prev) => [
          ...prev,
          "📩 Appeal submitted — professor will review.",
        ]);
      }
    } catch {
      setFeedback((prev) => [...prev, "❌ Failed to submit appeal."]);
    }
  };

  const runDemoSimulation = () => {
    const aiComments = [
      "🔍 Scanning handwriting via Document AI...",
      "✅ Student identified 'Newton's Second Law' correctly.",
      "⚠️ Formula derivation missing 'dt' term in step 3.",
      "📊 Diagram analysis: Flowchart logic matches Model Answer.",
      "✨ Assigning partial marks for clear conceptual understanding.",
      "💯 Final Score Calculated: 8.5/10",
    ];
    setIsGrading(true);
    setFeedback([]);
    aiComments.forEach((text, i) => {
      setTimeout(() => setFeedback((prev) => [...prev, text]), i * 1500);
    });
    setTimeout(() => {
      setScore(8.5);
      setConfidence(0.92);
    }, aiComments.length * 1500);
  };

  /* ---------------------------------------------------------------- */
  /*  Derived values                                                   */
  /* ---------------------------------------------------------------- */

  const confidencePct =
    confidence !== null ? Math.round(confidence * 100) : null;
  const confidenceLabel =
    confidence !== null
      ? confidence >= 0.8
        ? "High"
        : confidence >= 0.5
          ? "Medium"
          : "Low"
      : "--";
  const confidenceColor =
    confidence !== null
      ? confidence >= 0.8
        ? "text-emerald-400"
        : confidence >= 0.5
          ? "text-amber-400"
          : "text-red-400"
      : "text-white/40";

  const statusLabel = isGrading
    ? score !== null
      ? profStatus !== "Pending"
        ? profStatus
        : isFlagged
          ? "Flagged"
          : "Complete"
      : "Grading…"
    : "Ready";

  const statusDot = isGrading
    ? score !== null
      ? profStatus === "Approved"
        ? "bg-emerald-400"
        : profStatus === "Flagged" || isFlagged
          ? "bg-amber-400"
          : "bg-emerald-400"
      : "bg-blue-400 animate-pulse"
    : "bg-emerald-400";

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black text-white font-sans">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleFileSelect}
      />

      <div className="mx-auto max-w-[1440px] px-6 py-6">
        {/* ========== HEADER ========== */}
        <header className="flex flex-wrap items-center justify-between gap-4 mb-8 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl px-6 py-4">
          {/* Brand */}
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 shadow-lg shadow-blue-500/25">
              <Cpu className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-cyan-300 to-emerald-400 bg-clip-text text-transparent">
                AuraGrade AI Engine
              </h1>
              <p className="text-[11px] text-white/40 tracking-wide">
                Multimodal Exam Evaluation · Gemini&nbsp;3&nbsp;Flash
              </p>
            </div>
          </div>

          {/* Status cluster */}
          <div className="flex items-center gap-3">
            {/* Status pill */}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-medium text-white/70">
              <span className={`h-1.5 w-1.5 rounded-full ${statusDot}`} />
              {statusLabel}
            </span>

            {/* DB badge */}
            {dbConnected && (
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[10px] font-semibold text-emerald-400 tracking-wide">
                <Database className="h-3 w-3" /> Supabase
              </span>
            )}

            {savedToDb && (
              <span className="inline-flex items-center gap-1 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2.5 py-1 text-[10px] font-semibold text-cyan-400 tracking-wide">
                <CheckCircle2 className="h-3 w-3" /> Saved
              </span>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/configure")}
              className="border-white/10 bg-white/5 hover:bg-white/10 text-white/50 backdrop-blur-md text-xs"
            >
              <Settings2 className="mr-1.5 h-3.5 w-3.5" /> Configure
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/student")}
              className="border-white/10 bg-white/5 hover:bg-white/10 text-white/50 backdrop-blur-md text-xs"
            >
              <GraduationCap className="mr-1.5 h-3.5 w-3.5" /> Student View
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/proctor")}
              className="border-cyan-500/20 bg-cyan-500/5 hover:bg-cyan-500/10 text-cyan-400/70 backdrop-blur-md text-xs"
            >
              <Scan className="mr-1.5 h-3.5 w-3.5" /> Proctor Scanner
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.push("/admin/dashboard")}
              className="border-red-500/20 bg-red-500/5 hover:bg-red-500/10 text-red-400/70 backdrop-blur-md text-xs"
            >
              <Shield className="mr-1.5 h-3.5 w-3.5" /> CoE Portal
            </Button>
            <Button
              onClick={() => fileInputRef.current?.click()}
              variant="outline"
              className="border-white/10 bg-white/5 hover:bg-white/10 text-white/80 backdrop-blur-md"
            >
              <UploadCloud className="mr-2 h-4 w-4" /> Upload Script
            </Button>
            <Button
              onClick={startGrading}
              disabled={isGrading && score === null}
              className="bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white shadow-lg shadow-blue-500/25 disabled:opacity-50 disabled:shadow-none"
            >
              {isGrading && score === null ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Evaluating…
                </>
              ) : (
                <>
                  <Zap className="mr-2 h-4 w-4" /> Run AI Evaluator
                </>
              )}
            </Button>

            {/* Auth: Sign In / User Badge */}
            {authLoading ? (
              <div className="h-9 w-9 rounded-xl bg-white/5 animate-pulse" />
            ) : user ? (
              <UserBadge />
            ) : (
              <Link href="/login">
                <Button
                  variant="outline"
                  size="sm"
                  className="border-white/10 bg-white/5 hover:bg-white/10 text-white/60 backdrop-blur-md text-xs"
                >
                  Sign In
                </Button>
              </Link>
            )}
          </div>
        </header>

        {/* ========== STUDENT / ASSESSMENT SELECTORS ========== */}
        {dbConnected && (
          <div className="mb-6 flex flex-wrap items-center gap-4 rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl px-6 py-4">
            <div className="flex items-center gap-2 flex-1 min-w-[220px]">
              <Database className="h-4 w-4 text-white/30" />
              <Select value={studentRegNo} onValueChange={setStudentRegNo}>
                <SelectTrigger className="flex-1 border-white/10 bg-white/5 text-white/80 focus:ring-blue-500/40">
                  <SelectValue placeholder="Select Student" />
                </SelectTrigger>
                <SelectContent className="border-white/10 bg-slate-900 text-white/80">
                  {students.map((s) => (
                    <SelectItem key={s.id} value={s.reg_no}>
                      {s.reg_no} — {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <Separator orientation="vertical" className="hidden sm:block h-8 bg-white/10" />

            <div className="flex items-center gap-2 flex-1 min-w-[220px]">
              <FileText className="h-4 w-4 text-white/30" />
              <Select value={selectedAssessment} onValueChange={setSelectedAssessment}>
                <SelectTrigger className="flex-1 border-white/10 bg-white/5 text-white/80 focus:ring-blue-500/40">
                  <SelectValue placeholder="Select Assessment" />
                </SelectTrigger>
                <SelectContent className="border-white/10 bg-slate-900 text-white/80">
                  {assessments.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.subject} — {a.title}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        {/* ========== MAIN GRID ========== */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[calc(100vh-280px)] min-h-[520px]">
          {/* ---------- LEFT: Scanned Paper with Annotation Overlay ---------- */}
          <Card className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl group flex flex-col">
            {/* File badge */}
            <div className="absolute top-12 left-4 z-30">
              <Badge className="bg-black/50 backdrop-blur-xl border-white/10 text-white/70 text-[11px]">
                {selectedFile ? selectedFile.name : "Original Script"}
              </Badge>
            </div>

            {/* Progress HUD — pass tracker overlay */}
            {isGrading && (
              <div className="absolute top-4 right-4 z-30 flex gap-2">
                <div
                  className={`px-3 py-1.5 rounded-lg border backdrop-blur-md transition-all duration-300 ${
                    currentPass === 1
                      ? "border-cyan-500 bg-cyan-500/20 shadow-lg shadow-cyan-500/20"
                      : "border-white/10 bg-black/40"
                  }`}
                >
                  <p className="text-[9px] text-white/50 uppercase tracking-wider">
                    Pass 1
                  </p>
                  <p className="text-[11px] font-bold text-white flex items-center gap-1">
                    {currentPass === 1 && (
                      <Loader2 className="h-3 w-3 animate-spin text-cyan-400" />
                    )}
                    {currentPass > 1 && (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    )}
                    Vision Grader
                  </p>
                </div>
                <div
                  className={`px-3 py-1.5 rounded-lg border backdrop-blur-md transition-all duration-300 ${
                    currentPass === 2
                      ? "border-amber-500 bg-amber-500/20 shadow-lg shadow-amber-500/20"
                      : "border-white/10 bg-black/40"
                  }`}
                >
                  <p className="text-[9px] text-white/50 uppercase tracking-wider">
                    Pass 2
                  </p>
                  <p className="text-[11px] font-bold text-white flex items-center gap-1">
                    {currentPass === 2 && (
                      <Loader2 className="h-3 w-3 animate-spin text-amber-400" />
                    )}
                    {currentPass >= 3 && (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    )}
                    Professor Audit
                  </p>
                </div>
              </div>
            )}

            {previewUrl ? (
              <AnnotationOverlay
                imageSrc={previewUrl}
                annotations={annotations}
                isScanning={isGrading && score === null}
                onAnnotationClick={(a) =>
                  setFeedback((prev) => [
                    ...prev,
                    `🔎 ${a.label}: ${a.description}`,
                  ])
                }
              />
            ) : (
              <div className="flex-1 flex items-center justify-center">
                <div
                  className="flex flex-col items-center justify-center py-24 text-white/30 cursor-pointer hover:text-white/50 transition-colors"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <UploadCloud className="h-16 w-16 mb-4 opacity-40" />
                  <p className="text-base font-medium">
                    Click to upload an answer script
                  </p>
                  <p className="text-xs text-white/20 mt-1">
                    PNG, JPG — or use the Upload button
                  </p>
                </div>
              </div>
            )}
          </Card>

          {/* ---------- RIGHT: AI Intelligence Panel ---------- */}
          <Card className="flex flex-col rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
            {/* Panel Header */}
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
              <span className="flex items-center gap-2 text-sm font-semibold text-white/90">
                <Cpu className="h-4 w-4 text-cyan-400" />
                Agentic Reasoning Loop
              </span>
              <Badge className="border-none bg-cyan-500/15 text-cyan-300 text-[10px] font-semibold tracking-wide">
                Gemini 3 Flash
              </Badge>
            </div>

            {/* Feedback stream */}
            <ScrollArea className="flex-1">
              <div className="space-y-3 p-5">
                <AnimatePresence>
                  {feedback.map((item, index) => (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, x: 24, filter: "blur(6px)" }}
                      animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
                      transition={{ duration: 0.4 }}
                      className={`rounded-xl border px-4 py-3 text-sm leading-relaxed ${
                        item.includes("⚠️") || item.includes("🚩")
                          ? "border-amber-500/20 bg-amber-500/10 text-amber-200"
                          : item.includes("❌")
                            ? "border-red-500/20 bg-red-500/10 text-red-200"
                            : item.includes("💯")
                              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-200"
                              : item.includes("💾")
                                ? "border-cyan-500/20 bg-cyan-500/10 text-cyan-200"
                                : "border-white/5 bg-white/[0.03] text-white/70"
                      }`}
                    >
                      {item}
                    </motion.div>
                  ))}
                </AnimatePresence>

                {/* Empty state */}
                {!isGrading && feedback.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-20 text-white/20 space-y-3">
                    <Cpu className="h-12 w-12 opacity-30" />
                    <p className="text-sm">Upload a script to begin evaluation</p>
                  </div>
                )}

                <div ref={feedbackEndRef} />
              </div>
            </ScrollArea>

            {/* ---------- Bottom Stats & Actions ---------- */}
            <div className="border-t border-white/10 bg-black/20 backdrop-blur-xl px-5 py-4 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-4">
                {/* Metrics row */}
                <div className="flex items-center gap-5">
                  {/* Confidence */}
                  <div className="text-center">
                    <p className="text-[9px] uppercase tracking-[0.15em] text-white/30 mb-0.5">
                      Confidence
                    </p>
                    <p className={`text-base font-bold ${confidenceColor}`}>
                      {confidencePct !== null ? `${confidencePct}%` : "--"}
                    </p>
                  </div>

                  <div className="h-8 w-px bg-white/10" />

                  {/* AI Marks */}
                  <div className="text-center">
                    <p className="text-[9px] uppercase tracking-[0.15em] text-white/30 mb-0.5">
                      AI Marks
                    </p>
                    <p className="text-base font-bold text-blue-400">
                      {score !== null ? `${score} / 10` : "-- / 10"}
                    </p>
                  </div>

                  {/* Flagged indicator */}
                  {isFlagged && (
                    <>
                      <div className="h-8 w-px bg-white/10" />
                      <div className="text-center">
                        <p className="text-[9px] uppercase tracking-[0.15em] text-white/30 mb-0.5">
                          Flag
                        </p>
                        <p className="text-sm font-bold text-amber-400 flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" /> Review
                        </p>
                      </div>
                    </>
                  )}

                  {/* DB status */}
                  {savedToDb && (
                    <>
                      <div className="h-8 w-px bg-white/10" />
                      <div className="text-center">
                        <p className="text-[9px] uppercase tracking-[0.15em] text-white/30 mb-0.5">
                          Status
                        </p>
                        <p
                          className={`text-sm font-bold ${
                            profStatus === "Approved"
                              ? "text-emerald-400"
                              : profStatus === "Flagged"
                                ? "text-amber-400"
                                : profStatus === "Overridden"
                                  ? "text-purple-400"
                                  : "text-white/50"
                          }`}
                        >
                          {profStatus}
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {/* Action buttons */}
                <div className="flex gap-2">
                  {gradeId && profStatus === "Pending" && (
                    <>
                      <Button
                        onClick={handleApprove}
                        className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs shadow-lg shadow-emerald-500/20"
                      >
                        <Gavel className="mr-1.5 h-3.5 w-3.5" /> Approve
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setShowAppealInput(!showAppealInput)}
                        className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10 text-xs"
                      >
                        <ShieldAlert className="mr-1.5 h-3.5 w-3.5" /> Appeal
                      </Button>
                    </>
                  )}
                  {!gradeId && score !== null && (
                    <Button
                      variant="outline"
                      className="border-white/10 text-white/50 text-xs"
                      disabled
                    >
                      Approve Grade
                    </Button>
                  )}
                </div>
              </div>

              {/* Appeal input */}
              <AnimatePresence>
                {showAppealInput && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex gap-2"
                  >
                    <input
                      type="text"
                      value={appealReason}
                      onChange={(e) => setAppealReason(e.target.value)}
                      placeholder="Reason for appeal…"
                      className="flex-1 rounded-lg border border-amber-500/20 bg-white/5 px-3 py-1.5 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-amber-500/50"
                    />
                    <Button
                      onClick={handleAppeal}
                      disabled={!appealReason.trim()}
                      className="bg-amber-600 hover:bg-amber-500 text-white text-xs disabled:opacity-50"
                    >
                      Submit
                    </Button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </Card>
        </div>

        {/* ========== FOOTER ATTRIBUTION ========== */}
        <footer className="mt-6 text-center text-[11px] text-white/20 tracking-wide">
          AuraGrade v1.0 · Powered by Gemini 3 Flash · Supabase PostgreSQL ·
          Built with Next.js&nbsp;16
        </footer>
      </div>

      {/* Error toast */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 30 }}
            className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 backdrop-blur-xl px-4 py-3 text-sm text-red-300 shadow-2xl"
          >
            <AlertCircle className="h-4 w-4" />
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-red-400 hover:text-red-200"
            >
              ✕
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── AuraVoice — Hands-free grading control ── */}
      <AuraVoiceControl
        gradeId={gradeId}
        authFetch={authFetch}
        onCommandExecuted={(cmd: VoiceCommand, ok: boolean, msg: string) => {
          if (ok) {
            setFeedback((prev) => [...prev, `🎙️ Voice: ${msg}`]);
            if (cmd.intent === "OVERRIDE_SCORE" && cmd.value !== undefined) {
              setScore(cmd.value);
              setProfStatus("Overridden");
            } else if (cmd.intent === "APPROVE") {
              setProfStatus("Approved");
            } else if (cmd.intent === "FLAG") {
              setProfStatus("Flagged");
              setIsFlagged(true);
            }
          } else {
            setFeedback((prev) => [...prev, `❌ Voice: ${msg}`]);
          }
        }}
      />
    </div>
  );
};

export default GradingDashboard;
