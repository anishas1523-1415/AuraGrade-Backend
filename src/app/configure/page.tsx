"use client";

import React, { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  BookOpen,
  Scale,
  Save,
  Plus,
  Trash2,
  ArrowLeft,
  Cpu,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Upload,
  FileText,
  Database,
  Layers,
  Sparkles,
  Image as ImageIcon,
  LogIn,
  Shield,
} from "lucide-react";
import Link from "next/link";
import { UserBadge } from "@/components/UserBadge";
import { useAuth } from "@/lib/auth-context";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface RubricItem {
  criteria: string;
  max_marks: number;
  description: string;
}

interface Assessment {
  id: string;
  subject: string;
  title: string;
  model_answer: string | null;
  rubric_json: Record<string, { max_marks: number; description: string }> | null;
  created_at: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Auth Button (Sign In / User Badge)                                 */
/* ------------------------------------------------------------------ */

function AuthButton() {
  const { user, loading } = useAuth();
  if (loading) return <div className="h-9 w-9 rounded-xl bg-white/5 animate-pulse" />;
  if (user) return <UserBadge />;
  return (
    <Link href="/login">
      <Button variant="outline" size="sm" className="border-white/10 bg-white/5 hover:bg-white/10 text-white/60 backdrop-blur-md text-xs">
        <LogIn className="mr-1.5 h-3.5 w-3.5" /> Sign In
      </Button>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function RubricUploadPage() {
  const router = useRouter();

  // Assessment state
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedAssessment, setSelectedAssessment] = useState<string>("");
  const [newSubject, setNewSubject] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Model answer state
  const [modelAnswerText, setModelAnswerText] = useState("");
  const [modelAnswerFile, setModelAnswerFile] = useState<File | null>(null);
  const [modelAnswerPreview, setModelAnswerPreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // PDF Answer Key upload state
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfParsing, setPdfParsing] = useState(false);
  const [pdfResult, setPdfResult] = useState<{
    success: boolean;
    message: string;
    rubric?: Record<string, unknown>;
    totalMarks?: number;
    questionsDetected?: number;
    extractionMethod?: string;
  } | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  // Rubric state
  const [rubricItems, setRubricItems] = useState<RubricItem[]>([
    { criteria: "", max_marks: 0, description: "" },
  ]);

  // Sync state
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [creatingAssessment, setCreatingAssessment] = useState(false);

  /* ---------- Load assessments ---------- */
  useEffect(() => {
    const fetchAssessments = async () => {
      try {
        const res = await fetch(`${API_URL}/api/assessments`);
        if (res.ok) {
          const data = await res.json();
          setAssessments(data);
        }
      } catch (err) {
        console.error("Failed to load assessments:", err);
        setSyncResult({ success: false, message: `Cannot reach backend at ${API_URL}. Is NEXT_PUBLIC_API_URL set?` });
      }
    };
    fetchAssessments();
  }, []);

  /* ---------- When assessment selection changes, populate existing data ---------- */
  useEffect(() => {
    if (!selectedAssessment) {
      setModelAnswerText("");
      setRubricItems([{ criteria: "", max_marks: 0, description: "" }]);
      return;
    }
    const assessment = assessments.find((a) => a.id === selectedAssessment);
    if (!assessment) return;

    // Populate model answer
    setModelAnswerText(assessment.model_answer || "");

    // Populate rubric
    if (assessment.rubric_json && Object.keys(assessment.rubric_json).length > 0) {
      const items: RubricItem[] = Object.entries(assessment.rubric_json).map(
        ([key, val]) => ({
          criteria: key,
          max_marks: val.max_marks,
          description: val.description,
        })
      );
      setRubricItems(items);
    } else {
      setRubricItems([{ criteria: "", max_marks: 0, description: "" }]);
    }
  }, [selectedAssessment, assessments]);

  /* ---------- Rubric handlers ---------- */
  const addCriteria = () =>
    setRubricItems([...rubricItems, { criteria: "", max_marks: 0, description: "" }]);

  const removeCriteria = (index: number) => {
    if (rubricItems.length <= 1) return;
    setRubricItems(rubricItems.filter((_, i) => i !== index));
  };

  const updateCriteria = (index: number, field: keyof RubricItem, value: string | number) => {
    const updated = [...rubricItems];
    if (field === "max_marks") {
      updated[index][field] = Number(value) || 0;
    } else {
      updated[index][field] = value as string;
    }
    setRubricItems(updated);
  };

  /* ---------- File handler ---------- */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setModelAnswerFile(file);
    if (file.type.startsWith("image/")) {
      setModelAnswerPreview(URL.createObjectURL(file));
    } else {
      setModelAnswerPreview(null);
      // Read text files
      const reader = new FileReader();
      reader.onload = () => {
        setModelAnswerText(reader.result as string);
      };
      reader.readAsText(file);
    }
  };

  /* ---------- PDF Answer Key upload handler ---------- */
  const handlePdfUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPdfFile(file);

    if (!selectedAssessment) {
      setPdfResult({ success: false, message: "Select an assessment first before uploading a PDF." });
      return;
    }

    setPdfParsing(true);
    setPdfResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const selectedObj = assessments.find((a) => a.id === selectedAssessment);
      const subjectHint = selectedObj?.subject || "";

      const url = `${API_URL}/api/rubric/upload-pdf?assessment_id=${encodeURIComponent(selectedAssessment)}&auto_sync=true${subjectHint ? `&subject_hint=${encodeURIComponent(subjectHint)}` : ""}`;

      const res = await fetch(url, { method: "POST", body: formData });

      if (res.ok) {
        const data = await res.json();
        setPdfResult({
          success: true,
          message: data.message || "Answer key parsed and synced successfully.",
          rubric: data.rubric,
          totalMarks: data.total_marks,
          questionsDetected: data.questions_detected,
          extractionMethod: data.extraction_method,
        });

        // Auto-populate rubric items from the parsed result
        if (data.rubric && Object.keys(data.rubric).length > 0) {
          const items: RubricItem[] = Object.entries(data.rubric).map(
            ([key, val]: [string, unknown]) => {
              const v = val as { max_marks?: number; title?: string; breakdown?: string[] };
              return {
                criteria: v.title || key,
                max_marks: v.max_marks || 0,
                description: v.breakdown ? v.breakdown.join("; ") : "",
              };
            }
          );
          setRubricItems(items);
        }

        // Reload assessments to reflect new rubric
        const listRes = await fetch(`${API_URL}/api/assessments`);
        if (listRes.ok) setAssessments(await listRes.json());
      } else {
        const err = await res.json().catch(() => ({}));
        setPdfResult({
          success: false,
          message: err.detail || "Failed to parse the PDF answer key.",
        });
      }
    } catch (err) {
      setPdfResult({
        success: false,
        message: err instanceof Error ? err.message : "Upload failed.",
      });
    } finally {
      setPdfParsing(false);
    }
  };

  /* ---------- Create new assessment ---------- */
  const handleCreateAssessment = async () => {
    if (!newSubject.trim() || !newTitle.trim()) return;
    setCreatingAssessment(true);
    try {
      const res = await fetch(`${API_URL}/api/assessments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject: newSubject.trim(), title: newTitle.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        const newId = data.id || data[0]?.id;
        // Reload assessments
        const listRes = await fetch(`${API_URL}/api/assessments`);
        if (listRes.ok) setAssessments(await listRes.json());
        if (newId) setSelectedAssessment(newId);
        setNewSubject("");
        setNewTitle("");
        setShowCreateForm(false);
      } else {
        const err = await res.json().catch(() => ({}));
        setSyncResult({ success: false, message: `Create failed: ${err.detail || res.statusText}` });
      }
    } catch (err) {
      console.error("Create assessment failed:", err);
      setSyncResult({ success: false, message: `Cannot reach backend at ${API_URL}. Check your connection.` });
    } finally {
      setCreatingAssessment(false);
    }
  };

  /* ---------- SYNC to Pinecone & Supabase ---------- */
  const handleSync = async () => {
    if (!selectedAssessment) {
      setSyncResult({ success: false, message: "Select an assessment first" });
      return;
    }

    const validRubric = rubricItems.filter((r) => r.criteria.trim());
    if (validRubric.length === 0 && !modelAnswerText.trim() && !modelAnswerFile) {
      setSyncResult({
        success: false,
        message: "Provide at least a model answer or rubric criteria",
      });
      return;
    }

    setSyncing(true);
    setSyncResult(null);

    try {
      const results: string[] = [];

      // 1. Sync rubric JSON to Supabase
      if (validRubric.length > 0) {
        const rubricJson: Record<string, { max_marks: number; description: string }> = {};
        validRubric.forEach((item) => {
          const key = item.criteria
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_|_$/g, "");
          rubricJson[key] = {
            max_marks: item.max_marks,
            description: item.description || item.criteria,
          };
        });

        const rubricRes = await fetch(
          `${API_URL}/api/sync-rubric?assessment_id=${encodeURIComponent(selectedAssessment)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              rubric_json: rubricJson,
              model_text: modelAnswerText.trim() || null,
            }),
          }
        );
        if (rubricRes.ok) {
          const data = await rubricRes.json();
          results.push(data.message);
        } else {
          const err = await rubricRes.json().catch(() => ({}));
          results.push(`Rubric sync failed: ${err.detail || "Unknown error"}`);
        }
      }

      // 2. If image file, upload model answer image via separate endpoint
      if (modelAnswerFile && modelAnswerFile.type.startsWith("image/")) {
        const formData = new FormData();
        formData.append("file", modelAnswerFile);
        const imgRes = await fetch(
          `${API_URL}/api/model-answer?assessment_id=${encodeURIComponent(selectedAssessment)}`,
          { method: "POST", body: formData }
        );
        if (imgRes.ok) {
          const data = await imgRes.json();
          results.push(data.message);
        }
      }
      // 3. If text only (no rubric sync already handled it), sync text model answer
      else if (modelAnswerText.trim() && validRubric.length === 0) {
        const formData = new FormData();
        formData.append("text", modelAnswerText.trim());
        const textRes = await fetch(
          `${API_URL}/api/model-answer?assessment_id=${encodeURIComponent(selectedAssessment)}`,
          { method: "POST", body: formData }
        );
        if (textRes.ok) {
          const data = await textRes.json();
          results.push(data.message);
        }
      }

      // Reload assessment to show updated state
      const listRes = await fetch(`${API_URL}/api/assessments`);
      if (listRes.ok) setAssessments(await listRes.json());

      setSyncResult({
        success: true,
        message: results.join(" · ") || "Synced successfully",
      });
    } catch (err) {
      setSyncResult({
        success: false,
        message: err instanceof Error ? err.message : "Sync failed",
      });
    } finally {
      setSyncing(false);
    }
  };

  /* ---------- Derived ---------- */
  const totalMarks = rubricItems.reduce((sum, r) => sum + (r.max_marks || 0), 0);
  const validCriteria = rubricItems.filter((r) => r.criteria.trim()).length;
  const selectedAssessmentObj = assessments.find((a) => a.id === selectedAssessment);

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-[#0b1120] to-black text-white font-sans">
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.txt,.md,.pdf"
        multiple
        className="hidden"
        onChange={handleFileSelect}
      />
      <input
        ref={pdfInputRef}
        type="file"
        accept=".pdf,application/pdf,image/*"
        multiple
        className="hidden"
        onChange={handlePdfUpload}
      />

      <div className="mx-auto max-w-[1440px] px-6 py-6">
        {/* ========== TOP BAR ========== */}
        <div className="flex items-center justify-between gap-3 mb-6">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/")}
            className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 backdrop-blur-md"
          >
            <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Staff Dashboard
          </Button>
          <AuthButton />
        </div>

        {/* ========== HEADER ========== */}
        <motion.header
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-10"
        >
          <h1 className="text-4xl font-black tracking-tight bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-500 bg-clip-text text-transparent">
            Exam Configuration Portal
          </h1>
          <p className="text-white/40 mt-2 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            Define the Ground Truth for AuraGrade AI — Semantic Anchors &amp; Weighted Rubrics
          </p>
        </motion.header>

        {/* ========== ASSESSMENT SELECTOR ========== */}
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mb-8"
        >
          <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl">
            <CardContent className="py-5 px-6">
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2 text-sm text-white/50">
                  <Layers className="h-4 w-4 text-blue-400" />
                  Assessment:
                </div>

                <select
                  value={selectedAssessment}
                  onChange={(e) => setSelectedAssessment(e.target.value)}
                  className="flex-1 min-w-[260px] rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white/80 focus:outline-none focus:ring-1 focus:ring-blue-500/40 appearance-none cursor-pointer"
                >
                  <option value="" className="bg-slate-900">
                    Select an assessment…
                  </option>
                  {assessments.map((a) => (
                    <option key={a.id} value={a.id} className="bg-slate-900">
                      {a.subject} — {a.title}
                    </option>
                  ))}
                </select>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCreateForm(!showCreateForm)}
                  className="border-white/10 bg-white/5 text-white/60 hover:bg-white/10 text-xs"
                >
                  <Plus className="mr-1 h-3.5 w-3.5" /> New Assessment
                </Button>
              </div>

              {/* Create new assessment inline form */}
              <AnimatePresence>
                {showCreateForm && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="mt-4 flex flex-wrap gap-3 items-end border-t border-white/5 pt-4">
                      <div className="flex-1 min-w-[200px]">
                        <label className="text-[10px] uppercase tracking-wider text-white/30 mb-1 block">
                          Subject
                        </label>
                        <Input
                          value={newSubject}
                          onChange={(e) => setNewSubject(e.target.value)}
                          placeholder="e.g. AI & Data Science"
                          className="bg-black/20 border-white/10 text-white/80 placeholder:text-white/20"
                        />
                      </div>
                      <div className="flex-1 min-w-[200px]">
                        <label className="text-[10px] uppercase tracking-wider text-white/30 mb-1 block">
                          Title
                        </label>
                        <Input
                          value={newTitle}
                          onChange={(e) => setNewTitle(e.target.value)}
                          placeholder="e.g. Internal Assessment II"
                          className="bg-black/20 border-white/10 text-white/80 placeholder:text-white/20"
                        />
                      </div>
                      <Button
                        onClick={handleCreateAssessment}
                        disabled={!newSubject.trim() || !newTitle.trim() || creatingAssessment}
                        className="bg-blue-600 hover:bg-blue-500 text-white text-xs disabled:opacity-50"
                      >
                        {creatingAssessment ? (
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Plus className="mr-1.5 h-3.5 w-3.5" />
                        )}
                        Create
                      </Button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </CardContent>
          </Card>
        </motion.div>

        {/* ========== PDF ANSWER KEY UPLOAD (CLOSED-BOOK PIPELINE) ========== */}
        {selectedAssessment && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
            className="mb-8"
          >
            <Card className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.03] backdrop-blur-2xl overflow-hidden">
              <CardHeader className="border-b border-amber-500/10 px-6 py-4">
                <CardTitle className="flex items-center justify-between text-sm font-semibold">
                  <span className="flex items-center gap-2 text-amber-400">
                    <Upload className="w-4 h-4" />
                    Upload PDF Answer Key (Closed-Book Pipeline)
                  </span>
                  <Badge className="border-amber-500/20 bg-amber-500/10 text-amber-300 text-[10px]">
                    AI-Powered Extraction
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row gap-6">
                  {/* Upload zone */}
                  <div
                    onClick={() => !pdfParsing && pdfInputRef.current?.click()}
                    className={`flex-1 border-2 border-dashed rounded-xl p-8 text-center transition-all cursor-pointer group ${
                      pdfParsing
                        ? "border-amber-500/30 bg-amber-500/5"
                        : "border-white/10 hover:border-amber-500/40 hover:bg-white/[0.02]"
                    }`}
                  >
                    {pdfParsing ? (
                      <div className="space-y-3">
                        <Loader2 className="h-8 w-8 text-amber-400 animate-spin mx-auto" />
                        <p className="text-sm text-amber-300">Extracting rubric from PDF…</p>
                        <p className="text-[10px] text-white/30">
                          Gemini is reading the answer key and structuring your rubric
                        </p>
                      </div>
                    ) : pdfFile ? (
                      <div className="space-y-2">
                        <FileText className="h-8 w-8 text-amber-400 mx-auto" />
                        <p className="text-sm text-amber-300">{pdfFile.name}</p>
                        <p className="text-[10px] text-white/30">Click to upload a different file</p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <Upload className="h-8 w-8 text-white/10 group-hover:text-amber-400/60 transition-colors mx-auto" />
                        <p className="text-sm text-white/40">
                          Drop your Answer Key PDF here
                        </p>
                        <p className="text-[10px] text-white/20">
                          PDF, scanned image, or handwritten answer key — AI extracts the rubric automatically
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Info panel */}
                  <div className="flex-1 space-y-3">
                    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 space-y-2">
                      <h3 className="text-xs font-semibold text-white/50 flex items-center gap-1.5">
                        <Shield className="h-3.5 w-3.5 text-amber-400" />
                        How Closed-Book Grading Works
                      </h3>
                      <ul className="space-y-1.5 text-[11px] text-white/30">
                        <li className="flex items-start gap-1.5">
                          <span className="text-amber-400 mt-0.5">1.</span>
                          Upload your Answer Key / Rubric PDF
                        </li>
                        <li className="flex items-start gap-1.5">
                          <span className="text-amber-400 mt-0.5">2.</span>
                          AI extracts questions, marks, and model answers
                        </li>
                        <li className="flex items-start gap-1.5">
                          <span className="text-amber-400 mt-0.5">3.</span>
                          Rubric auto-populates below for your review
                        </li>
                        <li className="flex items-start gap-1.5">
                          <span className="text-amber-400 mt-0.5">4.</span>
                          Grading uses ONLY this rubric — no external knowledge
                        </li>
                      </ul>
                    </div>

                    {/* PDF result */}
                    <AnimatePresence>
                      {pdfResult && (
                        <motion.div
                          initial={{ opacity: 0, y: 8 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -8 }}
                          className={`rounded-xl border px-4 py-3 text-sm ${
                            pdfResult.success
                              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                              : "border-red-500/20 bg-red-500/10 text-red-300"
                          }`}
                        >
                          <div className="flex items-start gap-2">
                            {pdfResult.success ? (
                              <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                            ) : (
                              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                            )}
                            <div className="space-y-1">
                              <p className="text-xs">{pdfResult.message}</p>
                              {pdfResult.success && (
                                <div className="flex gap-3 text-[10px] text-white/40">
                                  <span>{pdfResult.questionsDetected} questions</span>
                                  <span>{pdfResult.totalMarks} marks</span>
                                  <span>via {pdfResult.extractionMethod}</span>
                                </div>
                              )}
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* ========== MAIN GRID ========== */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* ─── LEFT: Model Answer Input ─── */}
          <motion.div
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 }}
          >
            <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden h-full">
              <CardHeader className="border-b border-white/10 px-6 py-4">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold text-white/80">
                  <BookOpen className="text-blue-400 w-4 h-4" />
                  Model Answer (Semantic Reference)
                </CardTitle>
              </CardHeader>
              <CardContent className="p-6 space-y-5">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-white/30 mb-2 block">
                    Ideal Answer Text
                  </label>
                  <Textarea
                    value={modelAnswerText}
                    onChange={(e) => setModelAnswerText(e.target.value)}
                    placeholder="Paste the ideal answer here. The AI uses this as the Semantic Anchor for concept matching — the closer a student's answer is to this embedding, the higher the semantic similarity score."
                    className="min-h-[280px] bg-black/20 border-white/10 text-white/70 placeholder:text-white/15 resize-none rounded-xl focus:ring-1 focus:ring-blue-500/40"
                  />
                  <p className="text-[10px] text-white/20 mt-1.5">
                    {modelAnswerText.length > 0
                      ? `${modelAnswerText.length} chars · ~${Math.ceil(modelAnswerText.length / 500)} Pinecone chunks`
                      : "Text will be split into chunks and embedded via llama-text-embed-v2"}
                  </p>
                </div>

                {/* File upload zone */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-white/10 rounded-xl p-6 text-center hover:border-blue-500/40 hover:bg-white/[0.02] transition-all cursor-pointer group"
                >
                  {modelAnswerPreview ? (
                    <div className="space-y-3">
                      <img
                        src={modelAnswerPreview}
                        alt="Model answer scan"
                        className="max-h-40 mx-auto rounded-lg border border-white/10"
                      />
                      <p className="text-xs text-blue-400">
                        {modelAnswerFile?.name} — click to replace
                      </p>
                    </div>
                  ) : modelAnswerFile ? (
                    <div className="flex items-center justify-center gap-2 text-blue-400">
                      <FileText className="h-5 w-5" />
                      <span className="text-sm">{modelAnswerFile.name}</span>
                    </div>
                  ) : (
                    <>
                      <div className="flex justify-center mb-2">
                        <ImageIcon className="h-8 w-8 text-white/10 group-hover:text-blue-400/40 transition-colors" />
                      </div>
                      <p className="text-sm text-white/30">
                        Or upload a handwritten Model Answer scan
                      </p>
                      <p className="text-[10px] text-white/15 mt-1">
                        Gemini 3 Flash extracts text &amp; compares diagram structures
                      </p>
                    </>
                  )}
                </div>

                {/* Stats */}
                {selectedAssessmentObj?.model_answer && (
                  <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                    <p className="text-xs text-emerald-300/70">
                      Existing model answer found ({selectedAssessmentObj.model_answer.length} chars) — editing will overwrite
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>

          {/* ─── RIGHT: Smart Rubric Builder ─── */}
          <motion.div
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
          >
            <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden h-full flex flex-col">
              <CardHeader className="border-b border-white/10 px-6 py-4">
                <CardTitle className="flex items-center justify-between text-sm font-semibold">
                  <span className="flex items-center gap-2 text-emerald-400">
                    <Scale className="w-4 h-4" />
                    Evaluation Rubric
                  </span>
                  <Badge className="border-white/10 bg-white/5 text-white/40 text-[10px]">
                    {validCriteria} criteria · {totalMarks} marks
                  </Badge>
                </CardTitle>
              </CardHeader>

              <CardContent className="p-6 space-y-4 flex-1 flex flex-col">
                {/* Column labels */}
                <div className="grid grid-cols-[1fr_80px_1fr_36px] gap-3 text-[10px] uppercase tracking-wider text-white/30 px-1">
                  <span>Marking Criteria</span>
                  <span>Marks</span>
                  <span>Description</span>
                  <span />
                </div>

                {/* Rubric rows */}
                <div className="space-y-3 flex-1">
                  <AnimatePresence>
                    {rubricItems.map((item, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        transition={{ delay: 0.03 * index }}
                        className="grid grid-cols-[1fr_80px_1fr_36px] gap-3 items-center"
                      >
                        <Input
                          value={item.criteria}
                          onChange={(e) => updateCriteria(index, "criteria", e.target.value)}
                          placeholder="e.g. Newton's 2nd Law mention"
                          className="bg-black/20 border-white/10 text-white/70 placeholder:text-white/15 text-sm rounded-lg"
                        />
                        <Input
                          type="number"
                          value={item.max_marks || ""}
                          onChange={(e) => updateCriteria(index, "max_marks", e.target.value)}
                          placeholder="0"
                          className="bg-black/20 border-white/10 text-white/70 text-sm text-center rounded-lg"
                        />
                        <Input
                          value={item.description}
                          onChange={(e) => updateCriteria(index, "description", e.target.value)}
                          placeholder="Brief grading note"
                          className="bg-black/20 border-white/10 text-white/70 placeholder:text-white/15 text-sm rounded-lg"
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => removeCriteria(index)}
                          disabled={rubricItems.length <= 1}
                          className="border-white/5 bg-transparent text-white/20 hover:text-red-400 hover:bg-red-500/10 h-9 w-9 p-0 disabled:opacity-20"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </motion.div>
                    ))}
                  </AnimatePresence>
                </div>

                {/* Add criteria button */}
                <Button
                  onClick={addCriteria}
                  variant="outline"
                  className="w-full border-dashed border-white/10 text-white/40 hover:bg-white/5 hover:text-white/60"
                >
                  <Plus className="w-4 h-4 mr-2" /> Add Marking Criteria
                </Button>

                {/* Total marks summary */}
                {totalMarks > 0 && (
                  <div className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 flex items-center justify-between">
                    <span className="text-xs text-white/30">Total Marks</span>
                    <span className="text-lg font-black text-cyan-400">{totalMarks}</span>
                  </div>
                )}

                {/* Sync button */}
                <div className="pt-4 border-t border-white/5 space-y-3">
                  <Button
                    onClick={handleSync}
                    disabled={syncing || !selectedAssessment}
                    className="w-full bg-gradient-to-r from-blue-600 to-cyan-500 hover:from-blue-500 hover:to-cyan-400 text-white shadow-lg shadow-blue-500/20 disabled:opacity-50 disabled:shadow-none py-3 text-sm font-semibold"
                  >
                    {syncing ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Syncing…
                      </>
                    ) : (
                      <>
                        <Save className="mr-2 h-4 w-4" /> Sync to Pinecone &amp; Supabase
                      </>
                    )}
                  </Button>

                  {/* How it works */}
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    <div className="flex items-start gap-1.5 text-white/20 bg-white/[0.02] rounded-lg p-2">
                      <Database className="h-3 w-3 text-emerald-400 mt-0.5 shrink-0" />
                      <span>Rubric JSON → Supabase assessment row</span>
                    </div>
                    <div className="flex items-start gap-1.5 text-white/20 bg-white/[0.02] rounded-lg p-2">
                      <Layers className="h-3 w-3 text-blue-400 mt-0.5 shrink-0" />
                      <span>Model Answer → Pinecone vector embeddings (RAG)</span>
                    </div>
                  </div>
                </div>

                {/* Sync result toast */}
                <AnimatePresence>
                  {syncResult && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      className={`flex items-center gap-2 rounded-xl border px-4 py-3 text-sm ${
                        syncResult.success
                          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300"
                          : "border-red-500/20 bg-red-500/10 text-red-300"
                      }`}
                    >
                      {syncResult.success ? (
                        <CheckCircle2 className="h-4 w-4 shrink-0" />
                      ) : (
                        <AlertCircle className="h-4 w-4 shrink-0" />
                      )}
                      {syncResult.message}
                    </motion.div>
                  )}
                </AnimatePresence>
              </CardContent>
            </Card>
          </motion.div>
        </div>

        {/* ========== FOOTER ========== */}
        <footer className="mt-10 flex items-center justify-center gap-2 text-[11px] text-white/15 tracking-wide">
          <Cpu className="h-3 w-3" />
          AuraGrade · Ground Truth Configuration · Pinecone + Supabase
        </footer>
      </div>
    </div>
  );
}
