"use client";

import React, { useState, useRef, useCallback } from "react";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Cpu,
  UploadCloud,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  FileCode2,
  GitBranch,
  Zap,
  Copy,
  Check,
  XCircle,
  Info,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface LogicFlaw {
  flaw: string;
  severity: "critical" | "major" | "minor";
  suggestion: string;
}

interface DiagramResult {
  has_diagram?: boolean;
  diagram_type?: string;
  mermaid_code?: string;
  is_valid?: boolean;
  logic_score?: number;
  logic_flaws?: LogicFlaw[];
  structural_notes?: string;
  student_intent?: string;
  skipped?: boolean;
}

interface StepEvent {
  icon: string;
  text: string;
  phase: string;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const severityStyles: Record<string, { border: string; bg: string; text: string; icon: string }> = {
  critical: {
    border: "border-red-500/30",
    bg: "bg-red-500/10",
    text: "text-red-400",
    icon: "🔴",
  },
  major: {
    border: "border-amber-500/30",
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    icon: "🟡",
  },
  minor: {
    border: "border-blue-500/30",
    bg: "bg-blue-500/10",
    text: "text-blue-400",
    icon: "🟢",
  },
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function DiagramValidator() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [result, setResult] = useState<DiagramResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stepsEndRef = useRef<HTMLDivElement>(null);

  /* ---------- File handler ---------- */
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
      setSteps([]);
      setResult(null);
      setError(null);
    }
  };

  /* ---------- Auto-scroll steps ---------- */
  const scrollToBottom = useCallback(() => {
    stepsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  /* ---------- Run streaming validation ---------- */
  const authFetch = useAuthFetch();
  const handleValidate = async () => {
    if (!selectedFile) return;

    setAnalyzing(true);
    setSteps([]);
    setResult(null);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await authFetch(`${API_URL}/api/diagram/validate/stream`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No stream reader");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split("\n\n");
        buffer = frames.pop() || "";

        for (const frame of frames) {
          if (!frame.trim()) continue;

          let eventType = "";
          let eventData = "";

          for (const line of frame.split("\n")) {
            if (line.startsWith("event: ")) eventType = line.slice(7).trim();
            else if (line.startsWith("data: ")) eventData = line.slice(6);
          }

          if (!eventData) continue;

          try {
            const payload = JSON.parse(eventData);
            if (eventType === "step") {
              setSteps((prev) => [...prev, payload as StepEvent]);
              setTimeout(scrollToBottom, 50);
            } else if (eventType === "diagram_result") {
              setResult(payload as DiagramResult);
            } else if (eventType === "error") {
              setError(payload.message);
            }
          } catch {
            // skip malformed data
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setAnalyzing(false);
    }
  };

  /* ---------- Copy mermaid code ---------- */
  const handleCopyMermaid = async () => {
    if (!result?.mermaid_code) return;
    await navigator.clipboard.writeText(result.mermaid_code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  /* ---------- Score color ---------- */
  const getScoreColor = (score: number) =>
    score >= 7 ? "text-emerald-400" : score >= 4 ? "text-amber-400" : "text-red-400";

  return (
    <div className="space-y-6">
      {/* ========== Upload + Preview ========== */}
      <Card className="rounded-2xl border border-white/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
        <div className="border-b border-white/10 px-6 py-4">
          <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-violet-400" />
            Diagram-to-Code Validation
          </h3>
          <p className="text-[10px] text-white/30 mt-0.5">
            Upload an answer sheet — AI converts diagrams to Mermaid.js code and validates logic
          </p>
        </div>
        <CardContent className="p-6">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFileSelect}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Image preview */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className="relative rounded-xl border border-dashed border-white/10 bg-white/[0.02] overflow-hidden cursor-pointer hover:border-white/20 transition-colors min-h-[240px] flex items-center justify-center"
            >
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt="Uploaded script"
                  className="max-w-full max-h-[300px] rounded-lg opacity-80"
                />
              ) : (
                <div className="flex flex-col items-center gap-3 text-white/20 py-12">
                  <UploadCloud className="h-12 w-12 opacity-40" />
                  <p className="text-sm">Click to upload answer sheet</p>
                  <p className="text-[10px]">PNG, JPG — containing diagrams</p>
                </div>
              )}
            </div>

            {/* Steps panel */}
            <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden flex flex-col">
              <div className="px-4 py-2.5 border-b border-white/5 flex items-center gap-2">
                <Cpu className="h-3.5 w-3.5 text-violet-400" />
                <span className="text-[10px] text-white/40 uppercase tracking-wider font-semibold">
                  Validation Pipeline
                </span>
              </div>
              <ScrollArea className="flex-1 max-h-[260px]">
                <div className="p-3 space-y-2">
                  <AnimatePresence>
                    {steps.map((step, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, x: 16 }}
                        animate={{ opacity: 1, x: 0 }}
                        className={`rounded-lg border px-3 py-2 text-xs ${
                          step.text.includes("flaw") || step.text.includes("⚠")
                            ? "border-amber-500/20 bg-amber-500/5 text-amber-200"
                            : step.text.includes("validated") || step.text.includes("✅")
                              ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-200"
                              : "border-white/5 bg-white/[0.02] text-white/60"
                        }`}
                      >
                        {step.icon} {step.text}
                      </motion.div>
                    ))}
                  </AnimatePresence>
                  {steps.length === 0 && !analyzing && (
                    <p className="text-xs text-white/15 text-center py-8">
                      Upload an image and click &ldquo;Validate&rdquo; to start
                    </p>
                  )}
                  {analyzing && (
                    <div className="flex items-center justify-center py-4 gap-2 text-xs text-white/30">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-400" />
                      Processing…
                    </div>
                  )}
                  <div ref={stepsEndRef} />
                </div>
              </ScrollArea>
            </div>
          </div>

          {/* Validate button */}
          <div className="mt-4 flex justify-end">
            <Button
              onClick={handleValidate}
              disabled={!selectedFile || analyzing}
              className="bg-gradient-to-r from-violet-600 to-purple-500 hover:from-violet-500 hover:to-purple-400 text-white shadow-lg shadow-violet-500/20 disabled:opacity-50"
            >
              {analyzing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Validating…
                </>
              ) : (
                <>
                  <Zap className="mr-2 h-4 w-4" /> Validate Diagram
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ========== Results ========== */}
      <AnimatePresence>
        {result && result.has_diagram && !result.skipped && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="space-y-6"
          >
            {/* Mermaid Code Card */}
            <Card className="rounded-2xl border border-violet-500/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
              <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                  <FileCode2 className="h-4 w-4 text-violet-400" />
                  Generated Mermaid.js Code
                </h3>
                <div className="flex items-center gap-3">
                  <Badge className="text-[10px] border-violet-500/30 bg-violet-500/10 text-violet-400">
                    {result.diagram_type}
                  </Badge>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyMermaid}
                    className="h-7 text-[10px] border-white/10 text-white/40 hover:bg-white/5"
                  >
                    {copied ? (
                      <><Check className="h-3 w-3 mr-1 text-emerald-400" /> Copied</>
                    ) : (
                      <><Copy className="h-3 w-3 mr-1" /> Copy Code</>
                    )}
                  </Button>
                </div>
              </div>
              <CardContent className="p-0">
                <pre className="p-6 text-xs text-violet-300/80 font-mono leading-relaxed overflow-x-auto bg-black/20">
                  {result.mermaid_code || "No code generated"}
                </pre>
              </CardContent>
            </Card>

            {/* Validation Results Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Logic Score */}
              <Card className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-2xl">
                <CardContent className="p-5 text-center">
                  <p className="text-[10px] uppercase tracking-wider text-white/30 mb-2">Logic Score</p>
                  <p className={`text-4xl font-black ${getScoreColor(result.logic_score || 0)}`}>
                    {result.logic_score ?? "—"}
                    <span className="text-lg text-white/20 font-normal">/10</span>
                  </p>
                </CardContent>
              </Card>

              {/* Validity Status */}
              <Card className={`rounded-xl border ${result.is_valid ? "border-emerald-500/20 bg-emerald-500/5" : "border-red-500/20 bg-red-500/5"} backdrop-blur-2xl`}>
                <CardContent className="p-5 flex items-center justify-center gap-3">
                  {result.is_valid ? (
                    <>
                      <CheckCircle2 className="h-8 w-8 text-emerald-400" />
                      <div>
                        <p className="text-sm font-bold text-emerald-400">VALID</p>
                        <p className="text-[10px] text-white/30">Logic is structurally sound</p>
                      </div>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-8 w-8 text-red-400" />
                      <div>
                        <p className="text-sm font-bold text-red-400">FLAWED</p>
                        <p className="text-[10px] text-white/30">{(result.logic_flaws || []).length} issue(s) found</p>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Student Intent */}
              <Card className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-2xl">
                <CardContent className="p-5">
                  <div className="flex items-start gap-2">
                    <Info className="h-4 w-4 text-cyan-400 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-white/30 mb-1">Student Intent</p>
                      <p className="text-xs text-white/60 leading-relaxed">{result.student_intent || "—"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Logic Flaws (if any) */}
            {result.logic_flaws && result.logic_flaws.length > 0 && (
              <Card className="rounded-2xl border border-amber-500/10 bg-white/5 backdrop-blur-2xl overflow-hidden">
                <div className="border-b border-white/10 px-6 py-4">
                  <h3 className="text-sm font-semibold text-amber-400 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" />
                    Logic Flaws Detected
                  </h3>
                </div>
                <div className="p-4 space-y-3">
                  {result.logic_flaws.map((flaw, i) => {
                    const style = severityStyles[flaw.severity] || severityStyles.minor;
                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 * i }}
                        className={`rounded-xl border ${style.border} ${style.bg} p-4`}
                      >
                        <div className="flex items-start gap-3">
                          <span className="text-sm mt-0.5">{style.icon}</span>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <p className={`text-sm font-medium ${style.text}`}>{flaw.flaw}</p>
                              <Badge className={`text-[9px] ${style.border} ${style.bg} ${style.text}`}>
                                {flaw.severity.toUpperCase()}
                              </Badge>
                            </div>
                            <p className="text-xs text-white/40 flex items-center gap-1.5 mt-1">
                              <Zap className="h-3 w-3 text-emerald-400 shrink-0" />
                              <span className="text-emerald-400/70">{flaw.suggestion}</span>
                            </p>
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* Structural Notes */}
            {result.structural_notes && (
              <Card className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-2xl">
                <CardContent className="p-5">
                  <p className="text-[10px] uppercase tracking-wider text-white/30 mb-1">Structural Assessment</p>
                  <p className="text-sm text-white/60 leading-relaxed">{result.structural_notes}</p>
                </CardContent>
              </Card>
            )}
          </motion.div>
        )}

        {/* No diagram detected */}
        {result && result.skipped && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <Card className="rounded-xl border border-white/10 bg-white/5 backdrop-blur-2xl">
              <CardContent className="flex flex-col items-center justify-center py-12 text-white/30">
                <FileCode2 className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">No diagrams detected in this answer sheet</p>
                <p className="text-[10px] mt-1">The script appears to be text-only</p>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error display */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400 flex items-center gap-2"
          >
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
