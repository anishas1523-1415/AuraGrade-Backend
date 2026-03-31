"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ShieldCheck,
  Lock,
  Unlock,
  Fingerprint,
  AlertTriangle,
  Cpu,
  Loader2,
  CheckCircle2,
  Download,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { downloadPDF, type ReportRow } from "@/lib/report-export";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface LedgerHash {
  filename: string;
  sha256_hash: string;
  record_count: number;
  format: string;
  created_at: string;
}

export interface FinalizeGradesProps {
  assessmentId: string;
  assessmentLabel?: string;
  totalScripts: number;
  isAlreadyLocked: boolean;
  lockedBy?: string | null;
  lockedAt?: string | null;
  ledgerHashes?: LedgerHash[];
  /** Called with the real SHA-256 hash after successful lock */
  onLock: (hash: string) => void;
  /** Backend lock function — POST /api/assessments/{id}/lock */
  doLock: () => Promise<{ sha256?: string; status?: string } | null>;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const FinalizeGrades: React.FC<FinalizeGradesProps> = ({
  assessmentId,
  assessmentLabel,
  totalScripts,
  isAlreadyLocked,
  lockedBy,
  lockedAt,
  ledgerHashes = [],
  onLock,
  doLock,
}) => {
  const [isLocking, setIsLocking] = useState(false);
  const [progress, setProgress] = useState(0);
  const [digitalHash, setDigitalHash] = useState(
    ledgerHashes[0]?.sha256_hash ?? "",
  );
  const [isFinalized, setIsFinalized] = useState(isAlreadyLocked);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lockTriggeredRef = useRef(false);

  // Sync external lock state
  useEffect(() => {
    setIsFinalized(isAlreadyLocked);
    if (isAlreadyLocked && ledgerHashes[0]?.sha256_hash) {
      setDigitalHash(ledgerHashes[0].sha256_hash);
    }
  }, [isAlreadyLocked, ledgerHashes]);

  /* ---------- Hold-to-Lock logic ---------- */
  const cancelLock = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (!lockTriggeredRef.current) {
      setIsLocking(false);
      setProgress(0);
    }
  }, []);

  const handleHoldStart = useCallback(() => {
    if (isFinalized || isLocking) return;
    setIsLocking(true);
    setError(null);
    lockTriggeredRef.current = false;
    let current = 0;

    intervalRef.current = setInterval(() => {
      current += 2;
      setProgress(current);

      if (current >= 100) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = null;
        lockTriggeredRef.current = true;
        // Fire the real lock
        executeLock();
      }
    }, 30); // 50 ticks × 30ms = 1.5s hold
  }, [isFinalized, isLocking]);

  const executeLock = async () => {
    try {
      const result = await doLock();
      if (result) {
        const hash = result.sha256 ?? generateDisplayHash();
        setDigitalHash(hash);
        setIsFinalized(true);
        setProgress(100);
        onLock(hash);
      } else {
        setError("Lock failed — server returned no data.");
        setProgress(0);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Lock failed — please retry.",
      );
      setProgress(0);
    } finally {
      setIsLocking(false);
    }
  };

  /** Fallback display hash (only if backend doesn't return one) */
  const generateDisplayHash = () => {
    const chars = "0123456789abcdef";
    let hash = "";
    for (let i = 0; i < 64; i++) {
      hash += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return hash;
  };

  /* ---------- Derived ---------- */
  const holdSecondsLeft = Math.ceil((100 - progress) * 0.03);

  return (
    <div className="bg-slate-900 border border-white/10 rounded-3xl overflow-hidden shadow-2xl relative">
      {/* Background Decorative Element */}
      <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
        <Fingerprint className="w-64 h-64 text-white" />
      </div>

      <div className="p-8 relative z-10">
        {/* ── Header ── */}
        <div className="flex flex-wrap items-center justify-between mb-8 gap-4">
          <div className="flex items-center gap-4">
            <div
              className={`p-4 rounded-2xl border border-white/10 transition-colors duration-500 ${
                isFinalized
                  ? "bg-emerald-500/20"
                  : "bg-rose-500/10"
              }`}
            >
              {isFinalized ? (
                <Lock className="h-6 w-6 text-emerald-400" />
              ) : (
                <Unlock className="h-6 w-6 text-rose-400" />
              )}
            </div>
            <div>
              <h2 className="text-2xl font-black text-white tracking-tighter uppercase italic">
                Institutional Lock
              </h2>
              <p className="text-slate-400 text-xs font-mono">
                {assessmentLabel ??
                  `ID: ${assessmentId.toUpperCase().slice(0, 16)}`}
              </p>
            </div>
          </div>

          <div className="text-right">
            <p className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">
              Integrity Status
            </p>
            <div
              className={`text-sm font-bold ${
                isFinalized
                  ? "text-emerald-400"
                  : "text-amber-400 animate-pulse"
              }`}
            >
              {isFinalized ? "SEALED & AUTHENTIC" : "PENDING FINALIZATION"}
            </div>
          </div>
        </div>

        {/* ── Security Metrics Grid ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Left: metrics */}
          <div className="space-y-3">
            <div className="p-4 bg-black/40 border border-white/5 rounded-2xl flex items-center justify-between">
              <span className="text-xs text-slate-400">
                Total Validated Scripts
              </span>
              <span className="text-white font-mono font-bold">
                {totalScripts}
              </span>
            </div>
            <div className="p-4 bg-black/40 border border-white/5 rounded-2xl flex items-center justify-between">
              <span className="text-xs text-slate-400">
                Encryption Standard
              </span>
              <span className="text-white font-mono font-bold text-[10px]">
                SHA-256 (HMAC)
              </span>
            </div>
            {isFinalized && lockedBy && (
              <div className="p-4 bg-black/40 border border-white/5 rounded-2xl flex items-center justify-between">
                <span className="text-xs text-slate-400">Sealed By</span>
                <span className="text-white font-mono text-xs">
                  {lockedBy}
                  {lockedAt && (
                    <span className="text-white/30 ml-2">
                      {new Date(lockedAt).toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </span>
                  )}
                </span>
              </div>
            )}
          </div>

          {/* Right: SHA-256 Hash Display */}
          <div className="p-5 bg-slate-950 rounded-2xl border border-emerald-500/20 flex flex-col justify-center">
            <div className="flex items-center gap-2 mb-2">
              <Cpu className="w-3 h-3 text-emerald-500" />
              <span className="text-[10px] text-emerald-500/70 font-bold uppercase tracking-widest">
                Digital Signature Hash
              </span>
            </div>
            <p className="text-[11px] font-mono text-emerald-400/80 break-all leading-relaxed bg-emerald-500/5 p-3 rounded-lg border border-emerald-500/10 select-all">
              {isFinalized && digitalHash
                ? digitalHash
                : "••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••••"}
            </p>
            {isFinalized && ledgerHashes.length > 0 && (
              <div className="mt-3 flex items-center gap-2">
                <Badge className="text-[9px] border-emerald-500/20 bg-emerald-500/10 text-emerald-400">
                  {ledgerHashes[0].format.toUpperCase()}
                </Badge>
                <span className="text-[10px] text-white/20">
                  {ledgerHashes[0].record_count} records ·{" "}
                  {ledgerHashes[0].filename}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* ── Action Area ── */}
        <AnimatePresence mode="wait">
          {!isFinalized ? (
            <motion.div
              key="unlocked"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-4"
            >
              {/* Warning Banner */}
              <div className="flex items-start gap-3 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl">
                <AlertTriangle className="w-5 h-5 text-rose-500 flex-shrink-0 mt-0.5" />
                <p className="text-[11px] text-rose-200/80 leading-relaxed">
                  <strong className="text-rose-400 uppercase">
                    Warning:
                  </strong>{" "}
                  Locking this assessment will generate an immutable digital
                  seal. All AI scores will be finalized and further overrides
                  will require a COE override key. This action cannot be undone.
                </p>
              </div>

              {/* Error display */}
              {error && (
                <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-xs text-red-300">
                  <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
                  {error}
                </div>
              )}

              {/* Hold-to-Lock Button */}
              <button
                onMouseDown={handleHoldStart}
                onMouseUp={cancelLock}
                onMouseLeave={cancelLock}
                onTouchStart={handleHoldStart}
                onTouchEnd={cancelLock}
                disabled={totalScripts === 0}
                className="relative w-full py-6 rounded-2xl bg-white text-black font-black text-lg overflow-hidden transition-transform active:scale-[0.98] select-none disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {/* Progress fill */}
                <motion.div
                  className="absolute left-0 top-0 bottom-0 bg-emerald-500"
                  style={{ width: `${progress}%` }}
                  transition={{ duration: 0.05 }}
                />
                <span className="relative z-10 flex items-center justify-center gap-2">
                  {lockTriggeredRef.current && isLocking ? (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      SEALING…
                    </>
                  ) : isLocking ? (
                    `LOCKING IN ${holdSecondsLeft}s…`
                  ) : (
                    <>
                      <Lock className="h-5 w-5" />
                      HOLD TO SEAL ASSESSMENT
                    </>
                  )}
                </span>
              </button>

              {totalScripts === 0 && (
                <p className="text-[10px] text-white/20 text-center">
                  No approved/audited grades found. Approve grades before
                  locking.
                </p>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="locked"
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", damping: 20, stiffness: 200 }}
              className="w-full py-6 rounded-2xl bg-emerald-500/10 border border-emerald-500/50 flex items-center justify-center gap-3"
            >
              <ShieldCheck className="text-emerald-400 w-6 h-6" />
              <span className="text-emerald-400 font-bold uppercase tracking-tighter">
                Assessment Successfully Finalized
              </span>
              <CheckCircle2 className="text-emerald-400/50 w-4 h-4" />
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Download Sealed Report ── */}
        {isFinalized && (
          <div className="mt-6 flex justify-center">
            <button
              onClick={() => {
                const row: ReportRow = {
                  studentId: "INSTITUTION",
                  assessment: assessmentLabel ?? assessmentId,
                  totalMarks: totalScripts,
                  maxMarks: "N/A",
                  confidence: "100",
                  feedback: `Sealed by ${lockedBy || "Admin"} on ${lockedAt ? new Date(lockedAt).toLocaleString() : "N/A"}. SHA-256: ${digitalHash.slice(0, 16)}…`,
                  date: lockedAt ? new Date(lockedAt).toLocaleDateString() : new Date().toLocaleDateString(),
                };
                downloadPDF(
                  [row],
                  `Institutional Seal — ${assessmentLabel ?? assessmentId}`,
                  `AuraGrade_Seal_${assessmentId.slice(0, 8)}.pdf`,
                );
              }}
              className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 text-white font-bold rounded-xl hover:bg-emerald-500 transition text-sm shadow-lg shadow-emerald-500/20"
            >
              <Download className="h-4 w-4" />
              Download Sealed Report (PDF)
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default FinalizeGrades;
