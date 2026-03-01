"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";

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
          securityLevel: "loose",
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
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [evaluationData, setEvaluationData] = useState<EvaluationData | null>(null);
  const [streamLog, setStreamLog] = useState<StreamStep[]>([]);
  const [currentPhase, setCurrentPhase] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll the terminal log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamLog]);

  // Handle file selection + preview
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      setPreviewUrl(URL.createObjectURL(selected));
      setEvaluationData(null);
      setStreamLog([]);
      setCurrentPhase("");
    }
  }, []);

  // The core SSE streaming evaluation call
  const startEvaluation = useCallback(async () => {
    if (!file) return;

    setIsEvaluating(true);
    setEvaluationData(null);
    setStreamLog([{ icon: "🚀", text: "Initializing AuraGrade Engine…", phase: "init" }]);
    setCurrentPhase("init");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/evaluate", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`);
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
  }, [file]);

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
                  </span>{" "}
                  | Subject: Data Science
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
        </div>

        {/* ── Upload Controls ──────────────────────────────────── */}
        <div className="p-6 sm:p-8 border-b border-gray-200 bg-gray-50">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <input
              type="file"
              accept="image/*"
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

          {/* Image preview */}
          {previewUrl && !evaluationData && (
            <div className="mt-4">
              <img
                src={previewUrl}
                alt="Selected exam script"
                className="max-h-48 rounded-lg border border-slate-200 shadow-sm"
              />
            </div>
          )}
        </div>

        {/* ── Live Terminal / Stream Logs ───────────────────────── */}
        {streamLog.length > 0 && !evaluationData && (
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
                  </div>
                )}
              </div>
            </div>

            {/* ── Footer ───────────────────────────────────────── */}
            <div className="bg-slate-50 border-t border-slate-200 px-8 py-4 flex justify-between items-center text-xs text-slate-400">
              <span>AuraGrade v2 • Sovereign AI Grading Engine</span>
              <span>3-Pass Agentic Pipeline • Pinecone RAG • Gemini Vision</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
