"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import imageCompression from "browser-image-compression";
import { useDropzone } from "react-dropzone";
import { downloadCSV, downloadPDF, type ReportRow } from "@/lib/report-export";
import toast from "react-hot-toast";
import { useAuthFetch } from "@/lib/use-auth-fetch";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Mermaid Renderer (client-side only, React 19 compatible)           */
/* ------------------------------------------------------------------ */

function MermaidChart({ chart }: { chart: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "neutral",
          securityLevel: "strict",
          fontFamily: "ui-monospace, monospace",
        });
        const id = `mermaid-${Date.now()}`;
        const { svg: rendered } = await mermaid.render(id, chart);
        if (!cancelled) setSvg(rendered);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to render diagram");
      }
    }

    render();
    return () => { cancelled = true; };
  }, [chart]);

  if (error) {
    return (
      <div className="text-red-500 text-sm p-4 font-mono bg-red-50 rounded-lg">
        Diagram render error: {error}
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="flex items-center justify-center p-8 text-slate-400">
        <svg className="animate-spin h-5 w-5 mr-2" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Rendering diagram…
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="overflow-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface LogicFlaw {
  flaw: string;
}

interface DiagramAnalysis {
  mermaid_code: string;
  is_valid: boolean;
  logic_flaws: LogicFlaw[];
}

interface PerQuestionScores {
  q1_score: number;
  q2_score: number;
  q3_score: number;
}

interface EvaluationData {
  score: number;
  registration_number: string;
  per_question_scores: PerQuestionScores;
  penalties_applied: string[];
  justification_note: string;
  audit_notes: string;
  diagram_analysis: DiagramAnalysis;
  confidence?: number;
  confidence_score?: number;
  human_review_required?: boolean;
  sentinel_triggered?: boolean;
  max_similarity_score?: number;
  pass1_score?: number;
  pass2_score?: number;
  deterministic_score?: number;
  self_corrected?: boolean;
}

interface StreamStep {
  icon: string;
  text: string;
  phase: string;
}

/* ------------------------------------------------------------------ */
/*  Score colour helpers                                               */
/* ------------------------------------------------------------------ */

function scoreColor(score: number, max: number): string {
  const pct = score / max;
  if (pct >= 0.8) return "text-emerald-600";
  if (pct >= 0.5) return "text-amber-600";
  return "text-red-600";
}

function headerScoreColor(score: number): string {
  if (score >= 12) return "text-emerald-400";
  if (score >= 8) return "text-amber-400";
  return "text-red-400";
}

/* ------------------------------------------------------------------ */
/*  Score bar (visual progress indicator)                              */
/* ------------------------------------------------------------------ */

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = Math.min((score / max) * 100, 100);
  const bg =
    pct >= 80
      ? "bg-emerald-500"
      : pct >= 50
        ? "bg-amber-500"
        : "bg-red-500";

  return (
    <div className="w-full bg-slate-200 rounded-full h-2 mt-1">
      <div
        className={`${bg} h-2 rounded-full transition-all duration-700`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SSE Parser: handles chunked event: / data: frames                  */
/* ------------------------------------------------------------------ */

function parseSSEFrames(raw: string): Array<{ event: string; data: string }> {
  const frames: Array<{ event: string; data: string }> = [];
  const blocks = raw.split("\n\n");
  for (const block of blocks) {
    if (!block.trim()) continue;
    let eventType = "message";
    let dataLine = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event: ")) eventType = line.slice(7).trim();
      else if (line.startsWith("data: ")) dataLine = line.slice(6);
    }
    if (dataLine) frames.push({ event: eventType, data: dataLine });
  }
  return frames;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function EvaluationDashboard() {
  const authFetch = useAuthFetch();
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluationData, setEvaluationData] = useState<EvaluationData | null>(null);
  const [streamLog, setStreamLog] = useState<StreamStep[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // ── Batch mode state ────────────────────────────────────────
  const [batchFiles, setBatchFiles] = useState<File[]>([]);
  const [batchMode, setBatchMode] = useState(false);
  const [batchJobId, setBatchJobId] = useState<string | null>(null);
  const [batchProgress, setBatchProgress] = useState<number>(0);
  const [batchTotal, setBatchTotal] = useState<number>(0);
  const [batchResult, setBatchResult] = useState<Record<string, unknown> | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isPdfPreview = !!file && (file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));

  // ── react-dropzone for batch mode ───────────────────────────
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (acceptedFiles) => {
      if (acceptedFiles.length > 0) {
        setBatchFiles((prev) => [...prev, ...acceptedFiles].slice(0, 20));
        setBatchMode(true);
        setEvaluationData(null);
        setBatchResult(null);
        setStreamLog([]);
      }
    },
    accept: { "image/*": [], "application/pdf": [] },
    multiple: true,
    maxFiles: 20,
    maxSize: 15 * 1024 * 1024, // 15 MB per file
    noClick: false,
    noKeyboard: false,
  });

  const removeBatchFile = useCallback((index: number) => {
    setBatchFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // Auto-scroll the terminal log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamLog]);

  // Handle file selection + preview (single mode)
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      // Revoke previous blob URL to prevent memory leak
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(URL.createObjectURL(selected));
      setEvaluationData(null);
      setBatchResult(null);
      setStreamLog([]);
      setCurrentPhase("");
      setBatchMode(false);
    }
  }, [previewUrl]);



  // The core SSE streaming evaluation call
  const startEvaluation = useCallback(async () => {
    if (!file) return;

    setIsEvaluating(true);
    setEvaluationData(null);
    setStreamLog([{ icon: "🚀", text: "Initializing AuraGrade Engine…", phase: "init" }]);
    setCurrentPhase("init");

    // ── Client-side image compression (Network Savior) ──────────
    // Smartphone cameras produce 5-10 MB photos. Compressing to
    // ≤500 KB before upload makes it 10x faster on poor Wi-Fi.
    // Gemini Vision reads handwriting perfectly at this resolution.
    let uploadFile: File = file;
    try {
      setStreamLog(prev => [...prev, { icon: "📦", text: "Compressing image for fast upload…", phase: "init" }]);
      const compressed = await imageCompression(file, {
        maxSizeMB: 0.5,
        maxWidthOrHeight: 1920,
        useWebWorker: true,
      });
      const origMB = (file.size / 1024 / 1024).toFixed(2);
      const compMB = (compressed.size / 1024 / 1024).toFixed(2);
      setStreamLog(prev => [...prev, { icon: "✅", text: `Compressed from ${origMB}MB to ${compMB}MB`, phase: "init" }]);
      uploadFile = compressed;
    } catch (compErr) {
      console.warn("⚠️ Image compression failed, uploading original:", compErr);
      setStreamLog(prev => [...prev, { icon: "⚠️", text: "Compression skipped — uploading original", phase: "init" }]);
    }

    const formData = new FormData();
    formData.append("file", uploadFile);

    const idempotencyKey = [
      file.name,
      String(file.size),
      String(file.lastModified),
      "quick-evaluate",
    ].join("|");

    try {
      const response = await authFetch(`${API_URL}/api/evaluate?idempotency_key=${encodeURIComponent(idempotencyKey)}`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Server error: ${response.status} ${response.statusText}`);
      }
      if (!response.body) throw new Error("No response body from server.");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });

          // Only process complete frames (ending with \n\n)
          const lastDoubleNewline = buffer.lastIndexOf("\n\n");
          if (lastDoubleNewline === -1) continue;

          const completePart = buffer.slice(0, lastDoubleNewline + 2);
          buffer = buffer.slice(lastDoubleNewline + 2);

          const frames = parseSSEFrames(completePart);

          for (const frame of frames) {
            try {
              const payload = JSON.parse(frame.data);

              switch (frame.event) {
                case "step":
                  setStreamLog((prev) => [...prev, payload as StreamStep]);
                  setCurrentPhase(payload.phase || "");
                  break;

                case "result":
                  setEvaluationData(payload as EvaluationData);
                  setStreamLog((prev) => [
                    ...prev,
                    { icon: "✅", text: "Evaluation Complete!", phase: "done" },
                  ]);
                  break;

                case "error":
                  setStreamLog((prev) => [
                    ...prev,
                    { icon: "❌", text: payload.message || "Unknown error", phase: "error" },
                  ]);
                  break;

                case "done":
                  setIsEvaluating(false);
                  break;

                // Silently consume other events (pass1, pass2, rag, annotations, etc.)
                default:
                  break;
              }
            } catch {
              // Skip malformed JSON frames
            }
          }
        }
      }
    } catch (error) {
      console.error("Evaluation failed:", error);
      setStreamLog((prev) => [
        ...prev,
        { icon: "❌", text: `Connection failed: ${error instanceof Error ? error.message : "Unknown error"}`, phase: "error" },
      ]);
    } finally {
      setIsEvaluating(false);
    }
  }, [file, authFetch]);

  // ── Batch evaluation with job polling ───────────────────────
  const startBatchEvaluation = useCallback(async () => {
    if (batchFiles.length === 0) return;

    setIsEvaluating(true);
    setBatchResult(null);
    setEvaluationData(null);
    setBatchProgress(0);
    setStreamLog([
      { icon: "🚀", text: `Starting batch evaluation for ${batchFiles.length} file(s)…`, phase: "init" },
    ]);

    const formData = new FormData();
    for (const f of batchFiles) {
      formData.append("files", f);
    }

    try {
      const response = await authFetch(`${API_URL}/api/evaluate-batch`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(err.detail || `Server error: ${response.status}`);
      }

      const data = await response.json();
      const jobId = data.job_id;
      setBatchJobId(jobId);
      setBatchTotal(data.total_pages);

      // Show auto-detected student if header parser found one
      const detectedReg =
        data.detected_student?.student?.reg_no ??
        data.detected_student?.header?.reg_no;
      const detectedName = data.detected_student?.student?.name;

      setStreamLog((prev) => [
        ...prev,
        { icon: "📋", text: `Job ${jobId} created — ${data.total_pages} pages queued`, phase: "batch" },
        ...(detectedReg && detectedReg !== "FLAG_FOR_MANUAL"
          ? [{
              icon: "🔍",
              text: `Auto-detected student: ${detectedReg}${detectedName ? ` — ${detectedName}` : ""}`,
              phase: "batch" as const,
            }]
          : []),
      ]);

      // ── Poll for progress ────────────────────────────────
      pollingRef.current = setInterval(async () => {
        try {
          const statusRes = await authFetch(`${API_URL}/api/batch-status/${jobId}`);
          if (!statusRes.ok) return;
          const status = await statusRes.json();

          setBatchProgress(status.processed_pages);
          setStreamLog((prev) => {
            // Update the last progress line instead of appending
            const filtered = prev.filter((s) => s.phase !== "progress");
            return [
              ...filtered,
              {
                icon: "⏳",
                text: `Progress: ${status.processed_pages}/${status.total_pages} pages (${status.progress_percent}%)`,
                phase: "progress",
              },
            ];
          });

          if (status.status === "completed" || status.status === "failed") {
            if (pollingRef.current) clearInterval(pollingRef.current);
            pollingRef.current = null;

            if (status.status === "completed" && status.result) {
              setBatchResult(status.result);
              setStreamLog((prev) => [
                ...prev.filter((s) => s.phase !== "progress"),
                { icon: "✅", text: `Batch complete — ${status.result.pages_graded} pages graded`, phase: "done" },
              ]);
              // Success toast
              const syncedName =
                status.result.student_name ||
                status.result.registration_number ||
                "Student";
              if (status.result.synced_to_supabase) {
                toast.success(`Grade for ${syncedName} synced to Supabase!`);
              } else {
                toast.success(`Batch grading complete — ${status.result.pages_graded} pages graded`);
              }
            } else {
              setStreamLog((prev) => [
                ...prev,
                { icon: "❌", text: `Batch failed: ${status.errors?.join(", ") || "Unknown error"}`, phase: "error" },
              ]);
              toast.error("Batch grading failed. Check logs for details.");
            }

            setIsEvaluating(false);
          }
        } catch {
          // Polling error — keep trying
        }
      }, 3000);
    } catch (error) {
      console.error("Batch evaluation failed:", error);
      setStreamLog((prev) => [
        ...prev,
        { icon: "❌", text: `Batch failed: ${error instanceof Error ? error.message : "Unknown error"}`, phase: "error" },
      ]);
      setIsEvaluating(false);
    }
  }, [batchFiles, authFetch]);

  return (
    <div className="min-h-screen bg-gray-50 p-4 sm:p-8 font-sans">
      <div className="max-w-5xl mx-auto bg-white shadow-xl rounded-2xl overflow-hidden border border-gray-100">
        {/* ── Header ───────────────────────────────────────────── */}
        <div className="bg-slate-900 px-6 sm:px-8 py-6 flex flex-col sm:flex-row justify-between items-start sm:items-center text-white gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              AuraGrade Evaluation Report
            </h1>
            <p className="text-slate-400 mt-1 text-sm">
              {evaluationData ? (
                <>
                  Reg No:{" "}
                  <span className="font-mono text-blue-400 font-semibold">
                    {evaluationData.registration_number}
                  </span>
                </>
              ) : batchResult ? (
                <>
                  Reg No:{" "}
                  <span className="font-mono text-blue-400 font-semibold">
                    {(batchResult as Record<string, unknown>).registration_number as string}
                  </span>{" "}
                  | Batch Mode ({(batchResult as Record<string, unknown>).pages_graded as number} pages)
                </>
              ) : (
                "Sovereign AI-Powered Examination Grading"
              )}
            </p>
          </div>
          {evaluationData && (
            <div className="text-left sm:text-right">
              <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Final Score
              </div>
              <div
                className={`text-5xl font-black ${headerScoreColor(evaluationData.score)}`}
              >
                {evaluationData.score}
                <span className="text-2xl text-slate-500">/15</span>
              </div>
            </div>
          )}
          {batchResult && !evaluationData && (
            <div className="text-left sm:text-right">
              <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
                Aggregated Score
              </div>
              <div className="text-5xl font-black text-emerald-400">
                {(batchResult as Record<string, unknown>).score as number}
                <span className="text-2xl text-slate-500">/{(batchResult as Record<string, unknown>).max_marks as number}</span>
              </div>
            </div>
          )}
        </div>

        {/* ── Upload Controls ──────────────────────────────────── */}
        <div className="p-6 sm:p-8 border-b border-gray-200 bg-gray-50">
          {/* Mode toggle */}
          <div className="flex items-center gap-3 mb-4">
            <button
              onClick={() => { setBatchMode(false); setBatchFiles([]); setBatchResult(null); }}
              className={`px-3 py-1 text-sm font-semibold rounded-lg transition ${!batchMode ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-600 hover:bg-slate-300"}`}
            >
              Single Image
            </button>
            <button
              onClick={() => { setBatchMode(true); setFile(null); setEvaluationData(null); }}
              className={`px-3 py-1 text-sm font-semibold rounded-lg transition ${batchMode ? "bg-blue-600 text-white" : "bg-slate-200 text-slate-600 hover:bg-slate-300"}`}
            >
              Batch Upload
            </button>
          </div>

          {!batchMode ? (
            /* ── Single file mode ─────────────────────────────── */
            <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
              <input
                type="file"
                accept="image/*,.pdf"
                className="hidden"
                ref={fileInputRef}
                onChange={handleFileChange}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-2 bg-slate-200 text-slate-800 font-semibold rounded-lg hover:bg-slate-300 transition text-sm"
              >
                {file ? `📄 ${file.name}` : "Select Exam Image"}
              </button>
              <button
                onClick={startEvaluation}
                disabled={!file || isEvaluating}
                className="px-6 py-2 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed transition text-sm"
              >
                {isEvaluating ? (
                  <span className="flex items-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Evaluating…
                  </span>
                ) : (
                  "Run AI Evaluation"
                )}
              </button>
              {currentPhase && isEvaluating && (
                <span className="text-xs text-slate-500 font-mono">
                  Phase: {currentPhase}
                </span>
              )}
            </div>
          ) : (
            /* ── Batch upload mode (react-dropzone) ──────────── */
            <div>
              {/* Dropzone powered by react-dropzone */}
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  isDragActive
                    ? "border-blue-500 bg-blue-50 scale-[1.01]"
                    : "border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50"
                }`}
              >
                <input {...getInputProps()} />
                <div className="text-4xl mb-2">{isDragActive ? "📥" : "📄"}</div>
                <p className="text-slate-600 font-medium">
                  {isDragActive ? "Drop files here" : "Drag & drop images or PDFs here"}
                </p>
                <p className="text-slate-400 text-sm mt-1">
                  or click to browse · Max 20 files · 15 MB each
                </p>
              </div>

              {/* File list */}
              {batchFiles.length > 0 && (
                <div className="mt-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-slate-700">
                      {batchFiles.length} file{batchFiles.length !== 1 ? "s" : ""} selected
                    </span>
                    <button
                      onClick={() => setBatchFiles([])}
                      className="text-xs text-red-500 hover:text-red-700 font-medium"
                    >
                      Clear all
                    </button>
                  </div>
                  <div className="max-h-32 overflow-y-auto space-y-1">
                    {batchFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between bg-white px-3 py-1.5 rounded-lg border border-slate-200 text-sm">
                        <span className="truncate text-slate-700">
                          {f.type === "application/pdf" ? "📄" : "🖼️"} {f.name}
                          <span className="text-slate-400 ml-2">({(f.size / 1024 / 1024).toFixed(1)}MB)</span>
                        </span>
                        <button onClick={() => removeBatchFile(i)} className="text-red-400 hover:text-red-600 ml-2 text-lg leading-none">&times;</button>
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={startBatchEvaluation}
                    disabled={isEvaluating}
                    className="px-6 py-2 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 disabled:bg-blue-300 disabled:cursor-not-allowed transition text-sm w-full sm:w-auto"
                  >
                    {isEvaluating ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Grading {batchProgress}/{batchTotal} pages…
                      </span>
                    ) : (
                      `Grade ${batchFiles.length} File${batchFiles.length !== 1 ? "s" : ""}`
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Image preview (single mode) */}
          {!batchMode && previewUrl && !evaluationData && (
            <div className="mt-4">
              {isPdfPreview ? (
                <iframe
                  src={previewUrl}
                  title="Selected exam PDF"
                  className="w-full h-64 rounded-lg border border-slate-200 shadow-sm bg-white"
                />
              ) : (
                <img
                  src={previewUrl}
                  alt="Selected exam script"
                  className="max-h-48 rounded-lg border border-slate-200 shadow-sm"
                />
              )}
            </div>
          )}
        </div>

        {/* ── Live Terminal / Stream Logs ───────────────────────── */}
        {streamLog.length > 0 && !evaluationData && !batchResult && (
          <div className="bg-slate-950 text-green-400 font-mono text-sm p-6 max-h-72 overflow-y-auto">
            {streamLog.map((step, index) => (
              <div key={index} className="py-0.5 flex items-start gap-2">
                <span className="flex-shrink-0">{step.icon}</span>
                <span>{step.text}</span>
              </div>
            ))}
            <div ref={logEndRef} />
            {isEvaluating && (
              <div className="flex items-center gap-2 mt-2 text-slate-500">
                <span className="animate-pulse">▌</span>
              </div>
            )}
          </div>
        )}

        {/* ── Batch Progress Bar ───────────────────────────────── */}
        {batchMode && isEvaluating && batchTotal > 0 && (
          <div className="w-full max-w-md mx-auto mt-0 p-6 bg-white border-b border-slate-100">
            <div className="flex justify-between mb-2">
              <span className="text-sm font-semibold text-slate-700">
                AI Analyzing Pages…
              </span>
              <span className="text-sm font-bold text-blue-600">
                {batchTotal > 0 ? Math.round((batchProgress / batchTotal) * 100) : 0}%
              </span>
            </div>

            {/* Track */}
            <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
              {/* Moving bar */}
              <div
                className="bg-blue-600 h-full rounded-full transition-all duration-500 ease-out shadow-[0_0_10px_rgba(37,99,235,0.5)]"
                style={{ width: `${batchTotal > 0 ? Math.round((batchProgress / batchTotal) * 100) : 0}%` }}
              >
                {/* Animated shine effect */}
                <div className="w-full h-full animate-pulse bg-gradient-to-r from-transparent via-white/30 to-transparent" />
              </div>
            </div>

            <p className="mt-3 text-xs text-slate-500 text-center italic">
              Converting PDFs and running Vision OCR… ({batchProgress}/{batchTotal} pages)
            </p>
          </div>
        )}

        {/* ── Results Dashboard ────────────────────────────────── */}
        {evaluationData && (
          <>
            <div className="p-4 sm:p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* ─── Left Column: Scores & Penalties ─────────────── */}
              <div className="space-y-6">
                {/* Per-Question Breakdown */}
                <div className="bg-slate-50 p-6 rounded-xl border border-slate-200">
                  <h3 className="text-lg font-bold text-slate-800 mb-4 border-b pb-2">
                    Score Breakdown
                  </h3>
                  <ul className="space-y-4">
                    {[
                      {
                        label: "Q1. Neural Networks",
                        score: evaluationData.per_question_scores?.q1_score ?? 0,
                        max: 2,
                      },
                      {
                        label: "Q2. Python Pandas",
                        score: evaluationData.per_question_scores?.q2_score ?? 0,
                        max: 5,
                      },
                      {
                        label: "Q3. CNN Architecture",
                        score: evaluationData.per_question_scores?.q3_score ?? 0,
                        max: 8,
                      },
                    ].map((q) => (
                      <li key={q.label}>
                        <div className="flex justify-between text-sm font-mono text-slate-700">
                          <span>{q.label}</span>
                          <span className={`font-bold ${scoreColor(q.score, q.max)}`}>
                            {q.score} / {q.max.toFixed(1)}
                          </span>
                        </div>
                        <ScoreBar score={q.score} max={q.max} />
                      </li>
                    ))}
                  </ul>
                  <div className="mt-4 pt-4 border-t flex justify-between font-bold text-lg text-slate-900">
                    <span>Total Score</span>
                    <span className="text-blue-600">{evaluationData.score} / 15.0</span>
                  </div>
                  {evaluationData.deterministic_score !== undefined && (
                    <div className="text-xs text-slate-400 mt-1 text-right font-mono">
                      Deterministic sum: {evaluationData.deterministic_score}
                    </div>
                  )}
                </div>

                {/* Critical Penalties */}
                {evaluationData.penalties_applied && evaluationData.penalties_applied.length > 0 && (
                  <div className="bg-red-50 border-l-4 border-red-500 p-5 rounded-r-xl">
                    <h3 className="text-red-800 font-bold flex items-center mb-2">
                      <span className="mr-2">🚨</span> Critical Penalties Applied
                    </h3>
                    <ul className="list-disc pl-5 text-red-700 text-sm space-y-1">
                      {evaluationData.penalties_applied.map((penalty, idx) => (
                        <li key={idx}>{penalty}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* AI Justification */}
                {evaluationData.justification_note && (
                  <div>
                    <h3 className="text-lg font-bold text-slate-800 mb-2">
                      AI Justification
                    </h3>
                    <p className="text-slate-600 text-sm leading-relaxed bg-blue-50 p-4 rounded-xl border border-blue-100">
                      {evaluationData.justification_note}
                    </p>
                  </div>
                )}
              </div>

              {/* ─── Right Column: Diagram Analysis ──────────────── */}
              <div className="space-y-6">
                {/* Diagram Section */}
                {evaluationData.diagram_analysis?.mermaid_code && (
                  <>
                    <h3 className="text-lg font-bold text-slate-800 mb-2">
                      Diagram Extraction &amp; Logic Validation
                    </h3>

                    {/* Mermaid Diagram */}
                    <div className="bg-white border-2 border-dashed border-slate-300 rounded-xl p-6 flex justify-center items-center min-h-[160px]">
                      <MermaidChart
                        chart={evaluationData.diagram_analysis.mermaid_code}
                      />
                    </div>

                    {/* Validity Badge */}
                    <div className="flex items-center gap-2">
                      {evaluationData.diagram_analysis.is_valid ? (
                        <span className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-800 text-xs font-semibold px-3 py-1 rounded-full">
                          ✅ Structurally Valid
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 bg-red-100 text-red-800 text-xs font-semibold px-3 py-1 rounded-full">
                          ❌ Structural Issues Detected
                        </span>
                      )}
                    </div>

                    {/* Logic Flaws */}
                    {evaluationData.diagram_analysis.logic_flaws?.length > 0 && (
                      <div className="bg-orange-50 border border-orange-200 p-5 rounded-xl">
                        <h4 className="text-orange-800 font-bold mb-2">
                          Diagram Logic Flaws Detected:
                        </h4>
                        <ul className="list-disc pl-5 text-orange-700 text-sm">
                          {evaluationData.diagram_analysis.logic_flaws.map(
                            (flaw, idx) => (
                              <li key={idx}>{flaw.flaw}</li>
                            )
                          )}
                        </ul>
                      </div>
                    )}
                  </>
                )}

                {/* Score audit trail */}
                {evaluationData.self_corrected && (
                  <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl text-sm">
                    <span className="font-bold text-amber-800">✏️ Score Corrected by Audit:</span>{" "}
                    <span className="text-amber-700">
                      Pass 1 scored {evaluationData.pass1_score} → Audit adjusted to {evaluationData.pass2_score}
                    </span>
                  </div>
                )}

                {/* Professor Audit Notes */}
                {evaluationData.audit_notes && (
                  <div className="bg-slate-800 text-slate-300 p-5 rounded-xl text-sm border border-slate-700">
                    <span className="font-bold text-white block mb-1">
                      🎓 Pass 2: Professor Audit Agent
                    </span>
                    {evaluationData.audit_notes}
                  </div>
                )}

                {/* Confidence */}
                {evaluationData.confidence !== undefined && (
                  <div className="text-xs text-slate-500 font-mono text-right">
                    AI Confidence: {(evaluationData.confidence * 100).toFixed(1)}%
                    {evaluationData.confidence_score !== undefined && (
                      <span className="ml-2">(Score: {evaluationData.confidence_score}%)</span>
                    )}
                  </div>
                )}

                {/* Human Review Required Badge */}
                {evaluationData.human_review_required && (
                  <div className="flex items-center gap-2 mt-2 bg-red-50 border border-red-300 rounded-xl px-4 py-3">
                    <span className="text-xl">⚠️</span>
                    <div>
                      <p className="text-red-800 font-bold text-sm">Requires Human Review</p>
                      <p className="text-red-600 text-xs">
                        AI confidence is below 80% — this script has been flagged for manual verification to ensure grading accuracy.
                      </p>
                    </div>
                  </div>
                )}

                {/* Similarity Sentinel Warning Badge */}
                {evaluationData.sentinel_triggered && (
                  <div className="flex items-center gap-2 mt-2 bg-orange-50 border border-orange-400 rounded-xl px-4 py-3 shadow-[0_0_15px_rgba(249,115,22,0.1)]">
                    <svg className="w-5 h-5 text-orange-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                    <div>
                      <p className="text-orange-800 font-bold text-sm">
                        SENTINEL TRIGGERED: {evaluationData.max_similarity_score}% MATCH
                      </p>
                      <p className="text-orange-600 text-xs">
                        This submission has suspiciously high similarity to another graded script. Flagged for plagiarism review.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* ── Footer + Export buttons ──────────────────────── */}
            <div className="bg-slate-50 border-t border-slate-200 px-8 py-4 flex flex-wrap justify-between items-center gap-3 text-xs text-slate-400">
              <span>AuraGrade v2 • Sovereign AI Grading Engine</span>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    const row: ReportRow = {
                      studentId: evaluationData.registration_number,
                      assessment: "Single Evaluation",
                      totalMarks: evaluationData.score,
                      maxMarks: 15,
                      confidence: evaluationData.confidence != null ? (evaluationData.confidence * 100) : undefined,
                      feedback: evaluationData.justification_note || "",
                      date: new Date().toLocaleDateString(),
                    };
                    downloadCSV([row]);
                  }}
                  className="px-3 py-1.5 bg-slate-200 text-slate-700 font-semibold rounded-lg hover:bg-slate-300 transition text-xs"
                >
                  📥 CSV
                </button>
                <button
                  onClick={() => {
                    const row: ReportRow = {
                      studentId: evaluationData.registration_number,
                      assessment: "Single Evaluation",
                      totalMarks: evaluationData.score,
                      maxMarks: 15,
                      confidence: evaluationData.confidence != null ? (evaluationData.confidence * 100) : undefined,
                      feedback: evaluationData.justification_note || "",
                      date: new Date().toLocaleDateString(),
                    };
                    downloadPDF([row], `Report — ${evaluationData.registration_number}`);
                  }}
                  className="px-3 py-1.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition text-xs"
                >
                  📄 PDF Report
                </button>
              </div>
            </div>
          </>
        )}

        {/* ── Batch Results Dashboard ──────────────────────────── */}
        {batchResult && !evaluationData && (() => {
          const br = batchResult as Record<string, unknown>;
          const questions = (br.questions || []) as Array<Record<string, unknown>>;
          const feedback = (br.feedback || []) as string[];
          return (
            <>
              <div className="p-4 sm:p-8 space-y-6">
                {/* Overview cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-center">
                    <div className="text-2xl font-black text-blue-700">{br.score as number}</div>
                    <div className="text-xs text-blue-500 font-semibold">/ {br.max_marks as number}</div>
                    <div className="text-xs text-slate-500 mt-1">Total Score</div>
                  </div>
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-center">
                    <div className="text-2xl font-black text-emerald-700">{br.pages_graded as number}</div>
                    <div className="text-xs text-slate-500 mt-1">Pages Graded</div>
                  </div>
                  <div className="bg-purple-50 border border-purple-200 rounded-xl p-4 text-center">
                    <div className="text-2xl font-black text-purple-700">
                      {(((br.confidence as number) || 0) * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-slate-500 mt-1">Confidence</div>
                  </div>
                  <div className={`border rounded-xl p-4 text-center ${br.is_flagged ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
                    <div className="text-2xl font-black">{br.is_flagged ? "🚩" : "✅"}</div>
                    <div className="text-xs text-slate-500 mt-1">{br.is_flagged ? "Flagged" : "Clean"}</div>
                  </div>
                </div>

                {/* Questions breakdown */}
                {questions.length > 0 && (
                  <div className="bg-slate-50 p-6 rounded-xl border border-slate-200">
                    <h3 className="text-lg font-bold text-slate-800 mb-4 border-b pb-2">
                      Question Breakdown (All Pages)
                    </h3>
                    <ul className="space-y-3">
                      {questions.map((q, idx) => (
                        <li key={idx} className="flex justify-between items-center text-sm">
                          <span className="text-slate-700 font-medium truncate mr-4">
                            {(q.label as string) || (q.question as string) || `Question ${idx + 1}`}
                          </span>
                          <span className="font-bold text-blue-600 whitespace-nowrap">
                            {q.score as number} / {q.max_marks as number || q.max as number || "?"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Feedback */}
                {feedback.length > 0 && (
                  <div className="bg-blue-50 border border-blue-100 p-5 rounded-xl">
                    <h3 className="text-lg font-bold text-slate-800 mb-2">Feedback</h3>
                    <ul className="list-disc pl-5 text-slate-600 text-sm space-y-1">
                      {feedback.map((fb, idx) => (
                        <li key={idx}>{typeof fb === "string" ? fb : JSON.stringify(fb)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Footer + Batch Export */}
              <div className="bg-slate-50 border-t border-slate-200 px-8 py-4 flex flex-wrap justify-between items-center gap-3 text-xs text-slate-400">
                <span>AuraGrade v2 • Batch ({br.pages_graded as number} pages) • Job: {batchJobId}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      const rows: ReportRow[] = questions.length > 0
                        ? questions.map((q, i) => ({
                            studentId: (br.registration_number as string) || "UNKNOWN",
                            assessment: (q.label as string) || (q.question as string) || `Question ${i + 1}`,
                            totalMarks: (q.score as number) ?? 0,
                            maxMarks: (q.max_marks as number) || (q.max as number) || "?",
                            confidence: br.confidence != null ? (Number(br.confidence) * 100) : undefined,
                            feedback: feedback[i] || "",
                            date: new Date().toLocaleDateString(),
                          }))
                        : [{
                            studentId: (br.registration_number as string) || "UNKNOWN",
                            assessment: "Batch Evaluation",
                            totalMarks: br.score as number,
                            maxMarks: br.max_marks as number,
                            confidence: br.confidence != null ? (Number(br.confidence) * 100) : undefined,
                            feedback: feedback.join("; "),
                            date: new Date().toLocaleDateString(),
                          }];
                      downloadCSV(rows);
                    }}
                    className="px-3 py-1.5 bg-slate-200 text-slate-700 font-semibold rounded-lg hover:bg-slate-300 transition text-xs"
                  >
                    📥 CSV
                  </button>
                  <button
                    onClick={() => {
                      const rows: ReportRow[] = questions.length > 0
                        ? questions.map((q, i) => ({
                            studentId: (br.registration_number as string) || "UNKNOWN",
                            assessment: (q.label as string) || (q.question as string) || `Question ${i + 1}`,
                            totalMarks: (q.score as number) ?? 0,
                            maxMarks: (q.max_marks as number) || (q.max as number) || "?",
                            confidence: br.confidence != null ? (Number(br.confidence) * 100) : undefined,
                            feedback: feedback[i] || "",
                            date: new Date().toLocaleDateString(),
                          }))
                        : [{
                            studentId: (br.registration_number as string) || "UNKNOWN",
                            assessment: "Batch Evaluation",
                            totalMarks: br.score as number,
                            maxMarks: br.max_marks as number,
                            confidence: br.confidence != null ? (Number(br.confidence) * 100) : undefined,
                            feedback: feedback.join("; "),
                            date: new Date().toLocaleDateString(),
                          }];
                      downloadPDF(rows, `Batch Report — ${(br.registration_number as string) || "Unknown"}`);
                    }}
                    className="px-3 py-1.5 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 transition text-xs"
                  >
                    📄 PDF Report
                  </button>
                </div>
              </div>
            </>
          );
        })()}
      </div>
    </div>
  );
}
