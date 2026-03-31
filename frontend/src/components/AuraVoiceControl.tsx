"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic,
  MicOff,
  Command,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Flag,
  MessageSquarePlus,
  ArrowUpCircle,
  X,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface VoiceCommand {
  intent: "OVERRIDE_SCORE" | "ADD_COMMENT" | "FLAG" | "APPROVE" | "UNKNOWN";
  value?: number;
  payload?: string;
  raw: string;
}

interface AuraVoiceControlProps {
  /** grade id currently open in the dashboard */
  gradeId: string | null;
  /** authenticated fetch wrapper (sends Bearer token) */
  authFetch: (url: string, init?: RequestInit) => Promise<Response>;
  /** callback after a command is successfully executed against the API */
  onCommandExecuted: (cmd: VoiceCommand, success: boolean, message: string) => void;
}

/* ------------------------------------------------------------------ */
/*  Speech Recognition type shim (WebkitSpeechRecognition)             */
/* ------------------------------------------------------------------ */

interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Intent regex parser                                                */
/* ------------------------------------------------------------------ */

function parseIntent(raw: string): VoiceCommand {
  const text = raw.toLowerCase().trim();

  // 1. Override score — "set marks to 15", "change score to 8", "update marks 7.5"
  const scoreMatch = text.match(
    /(?:set|change|update|make|give|assign)\s+(?:marks?|score|grade|point)s?\s+(?:to|as|at|equals?)?\s*(\d+(?:\.\d+)?)/
  );
  if (scoreMatch) {
    return { intent: "OVERRIDE_SCORE", value: parseFloat(scoreMatch[1]), raw };
  }

  // 1b. Alternate: "marks 15", "score 9"
  const shortScore = text.match(/^(?:marks?|score|grade)\s+(\d+(?:\.\d+)?)$/);
  if (shortScore) {
    return { intent: "OVERRIDE_SCORE", value: parseFloat(shortScore[1]), raw };
  }

  // 2. Add comment — "add comment excellent diagram", "note student missed step 3"
  const commentMatch = text.match(
    /(?:add\s+comment|comment|note|remark|feedback)\s+(.+)/
  );
  if (commentMatch) {
    return { intent: "ADD_COMMENT", payload: commentMatch[1].trim(), raw };
  }

  // 3. Flag — "flag this", "flag for review", "mark as suspicious"
  if (/(?:flag|mark\s+(?:as\s+)?suspicious|needs?\s+review)/.test(text)) {
    return { intent: "FLAG", raw };
  }

  // 4. Approve — "approve this", "looks good", "accept grade"
  if (
    /(?:approve|accept|confirm|looks?\s+good|lgtm|stamp|pass\s+this)/.test(text)
  ) {
    return { intent: "APPROVE", raw };
  }

  return { intent: "UNKNOWN", raw };
}

/* ------------------------------------------------------------------ */
/*  Intent icons & colors                                              */
/* ------------------------------------------------------------------ */

function intentMeta(intent: VoiceCommand["intent"]) {
  switch (intent) {
    case "OVERRIDE_SCORE":
      return { icon: ArrowUpCircle, color: "text-cyan-400", bg: "bg-cyan-500", label: "Override Score" };
    case "ADD_COMMENT":
      return { icon: MessageSquarePlus, color: "text-violet-400", bg: "bg-violet-500", label: "Add Comment" };
    case "FLAG":
      return { icon: Flag, color: "text-amber-400", bg: "bg-amber-500", label: "Flag for Review" };
    case "APPROVE":
      return { icon: CheckCircle2, color: "text-emerald-400", bg: "bg-emerald-500", label: "Approve" };
    default:
      return { icon: AlertTriangle, color: "text-white/40", bg: "bg-white/20", label: "Unknown" };
  }
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const AuraVoiceControl: React.FC<AuraVoiceControlProps> = ({
  gradeId,
  authFetch,
  onCommandExecuted,
}) => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [lastCommand, setLastCommand] = useState<VoiceCommand | null>(null);
  const [executing, setExecuting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const recognitionRef = useRef<any>(null);
  const toastTimer = useRef<number | null>(null);

  /* ---------- Initialise SpeechRecognition once ---------- */
  const getSpeechRecognition = useCallback(() => {
    if (recognitionRef.current) return recognitionRef.current;
    if (typeof window === "undefined") return null;

    const SR =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;
    if (!SR) return null;

    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = (event: SpeechRecognitionEvent) => {
      const last = event.results[event.results.length - 1];
      const text = last[0].transcript;
      setTranscript(text);

      // Only parse final results
      if (last.isFinal) {
        const cmd = parseIntent(text);
        if (cmd.intent !== "UNKNOWN") {
          setLastCommand(cmd);
        }
      }
    };

    rec.onerror = () => {
      setIsListening(false);
    };

    rec.onend = () => {
      // If still supposed to be listening, restart (Chrome stops after silence)
      if (recognitionRef.current?._shouldListen) {
        try {
          rec.start();
        } catch {
          /* already started */
        }
      }
    };

    recognitionRef.current = rec;
    return rec;
  }, []);

  /* ---------- Execute voice command against API ---------- */
  const executeCommand = useCallback(
    async (cmd: VoiceCommand) => {
      if (!gradeId) {
        showToast("No grade selected — grade a script first.", false);
        onCommandExecuted(cmd, false, "No grade selected");
        return;
      }

      setExecuting(true);
      try {
        let res: Response;
        let msg: string;

        switch (cmd.intent) {
          case "OVERRIDE_SCORE": {
            res = await authFetch(
              `${API_URL}/api/grades/${gradeId}/override?new_score=${cmd.value}`,
              { method: "PUT" }
            );
            msg = res.ok
              ? `Score overridden → ${cmd.value}`
              : `Override failed: ${(await res.json().catch(() => ({}))).detail || res.status}`;
            break;
          }
          case "ADD_COMMENT": {
            // Use the appeal endpoint with the comment as reason (append to audit log)
            const qp = new URLSearchParams({ reason: cmd.payload || "" });
            res = await authFetch(
              `${API_URL}/api/grades/${gradeId}/appeal?${qp}`,
              { method: "PUT" }
            );
            msg = res.ok
              ? `Comment added: "${cmd.payload}"`
              : `Comment failed`;
            break;
          }
          case "FLAG": {
            const qp = new URLSearchParams({ reason: "Voice-flagged by evaluator" });
            res = await authFetch(
              `${API_URL}/api/grades/${gradeId}/appeal?${qp}`,
              { method: "PUT" }
            );
            msg = res.ok ? "Flagged for review" : "Flag failed";
            break;
          }
          case "APPROVE": {
            res = await authFetch(
              `${API_URL}/api/grades/${gradeId}/approve`,
              { method: "PUT" }
            );
            msg = res.ok ? "Grade approved ✓" : "Approve failed";
            break;
          }
          default:
            msg = "Unrecognised command";
            res = new Response(null, { status: 400 });
        }

        const ok = res.ok;
        showToast(msg, ok);
        onCommandExecuted(cmd, ok, msg);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Command failed";
        showToast(msg, false);
        onCommandExecuted(cmd, false, msg);
      } finally {
        setExecuting(false);
        setLastCommand(null);
      }
    },
    [gradeId, authFetch, onCommandExecuted]
  );

  /* ---------- Toast helper ---------- */
  const showToast = (msg: string, ok: boolean) => {
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    setToast({ msg, ok });
    toastTimer.current = window.setTimeout(() => setToast(null), 3500) as unknown as number;
  };

  /* ---------- Toggle mic ---------- */
  const toggleListening = useCallback(() => {
    const rec = getSpeechRecognition();
    if (!rec) {
      showToast("Speech Recognition not supported in this browser.", false);
      return;
    }

    if (isListening) {
      rec._shouldListen = false;
      rec.stop();
      setIsListening(false);
      setTranscript("");
    } else {
      rec._shouldListen = true;
      try {
        rec.start();
      } catch {
        /* already started */
      }
      setIsListening(true);
      setLastCommand(null);
      setTranscript("");
    }
  }, [isListening, getSpeechRecognition]);

  /* ---------- Cleanup ---------- */
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current._shouldListen = false;
        recognitionRef.current.stop();
      }
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    };
  }, []);

  /* ---------- Render ---------- */
  const meta = lastCommand ? intentMeta(lastCommand.intent) : null;
  const IntentIcon = meta?.icon || Sparkles;

  return (
    <div className="fixed bottom-8 right-8 z-[100] flex flex-col items-end gap-3">
      {/* ── Toast ── */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className={`px-4 py-2.5 rounded-xl backdrop-blur-xl border text-xs font-bold shadow-lg flex items-center gap-2 ${
              toast.ok
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-rose-500/10 border-rose-500/30 text-rose-400"
            }`}
          >
            {toast.ok ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5" />
            )}
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Command Feedback Bubble ── */}
      <AnimatePresence>
        {isListening && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.8 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            className="bg-slate-900/95 backdrop-blur-2xl border border-cyan-500/25 p-5 rounded-2xl shadow-2xl shadow-cyan-500/10 w-80"
          >
            {/* Waveform + Listening header */}
            <div className="flex items-center gap-3 mb-3">
              <div className="flex items-end gap-0.5 h-4">
                {[1, 2, 3, 4, 5].map((i) => (
                  <motion.div
                    key={i}
                    animate={{ height: [3, 14, 3] }}
                    transition={{
                      repeat: Infinity,
                      duration: 0.5 + i * 0.08,
                      delay: i * 0.07,
                    }}
                    className="w-[3px] bg-cyan-500 rounded-full"
                  />
                ))}
              </div>
              <span className="text-[9px] font-black text-cyan-500 uppercase tracking-[0.2em]">
                Listening…
              </span>
              <button
                onClick={toggleListening}
                className="ml-auto p-1 rounded-lg hover:bg-white/5 transition-colors"
              >
                <X className="h-3 w-3 text-white/30" />
              </button>
            </div>

            {/* Live transcript */}
            <div className="bg-black/40 rounded-xl px-3 py-2.5 mb-3 min-h-[2.5rem]">
              <p className="text-sm text-white/70 italic leading-relaxed">
                &ldquo;
                {transcript || (
                  <span className="text-white/25">
                    Try &ldquo;Set marks to 15&rdquo; or &ldquo;Approve
                    this&rdquo;…
                  </span>
                )}
                &rdquo;
              </p>
            </div>

            {/* Detected intent */}
            <AnimatePresence>
              {lastCommand && meta && (
                <motion.div
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="border-t border-white/5 pt-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <IntentIcon className={`h-3.5 w-3.5 ${meta.color}`} />
                      <span className="text-[10px] font-black text-white uppercase tracking-wider">
                        {meta.label}
                      </span>
                      {lastCommand.value !== undefined && (
                        <span
                          className={`${meta.bg} text-black px-2 py-0.5 rounded text-[10px] font-black`}
                        >
                          {lastCommand.value}
                        </span>
                      )}
                    </div>

                    <button
                      onClick={() => executeCommand(lastCommand)}
                      disabled={executing || !gradeId}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 border border-cyan-500/30 text-[10px] font-black text-cyan-400 uppercase tracking-wider transition-all disabled:opacity-30"
                    >
                      {executing ? (
                        <motion.div
                          animate={{ rotate: 360 }}
                          transition={{ repeat: Infinity, duration: 0.8 }}
                          className="w-3 h-3 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full"
                        />
                      ) : (
                        <Sparkles className="h-3 w-3" />
                      )}
                      Execute
                    </button>
                  </div>

                  {lastCommand.payload && (
                    <p className="text-[10px] text-white/30 mt-1.5 truncate">
                      &ldquo;{lastCommand.payload}&rdquo;
                    </p>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Voice guide */}
            <div className="mt-3 pt-3 border-t border-white/5">
              <p className="text-[9px] text-white/15 font-bold uppercase tracking-wider mb-1.5">
                Commands
              </p>
              <div className="grid grid-cols-2 gap-1">
                {[
                  "Set marks to _",
                  "Add comment _",
                  "Flag this",
                  "Approve",
                ].map((hint) => (
                  <span
                    key={hint}
                    className="text-[9px] text-white/20 font-mono bg-white/[0.02] px-1.5 py-0.5 rounded"
                  >
                    {hint}
                  </span>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Main Trigger Button ── */}
      <motion.button
        onClick={toggleListening}
        whileTap={{ scale: 0.9 }}
        className={`group relative p-5 rounded-full shadow-2xl transition-all ${
          isListening
            ? "bg-rose-500 shadow-rose-500/40 ring-4 ring-rose-500/20"
            : "bg-white hover:bg-cyan-500 shadow-cyan-500/20 hover:shadow-cyan-500/30"
        }`}
      >
        {isListening ? (
          <MicOff className="w-7 h-7 text-white" />
        ) : (
          <Mic className="w-7 h-7 text-black group-hover:text-white transition-colors" />
        )}

        {/* Ping indicator */}
        {!isListening && (
          <div className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 bg-cyan-500 rounded-full animate-ping pointer-events-none" />
        )}
      </motion.button>

      {/* ── Tooltip ── */}
      <AnimatePresence>
        {!isListening && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mr-1 px-3 py-1 bg-black/60 backdrop-blur-md rounded-lg border border-white/10 flex items-center gap-2 text-[9px] font-bold text-white/30 uppercase tracking-[0.15em]"
          >
            <Command className="w-3 h-3" /> AuraVoice
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AuraVoiceControl;
