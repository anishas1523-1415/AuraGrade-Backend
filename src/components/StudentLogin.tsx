"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useAuthFetch } from "@/lib/use-auth-fetch";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Fingerprint,
  ArrowRight,
  ShieldAlert,
  GraduationCap,
  Shield,
  Cpu,
  CheckCircle2,
  Database,
  Lock,
  Sparkles,
} from "lucide-react";
import { useRouter } from "next/navigation";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface StudentInfo {
  id: string;
  reg_no: string;
  name: string;
  email: string;
}

interface GradeEntry {
  id: string;
  ai_score: number;
  confidence: number;
  is_flagged: boolean;
  prof_status: string;
  graded_at: string;
  assessments: { subject: string; title: string };
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Terminal scan phases shown during the lookup animation */
const SCAN_PHASES = [
  { text: "INITIATING SECURE CONNECTION…", delay: 0 },
  { text: "QUERYING BLOCKCHAIN LEDGER…", delay: 400 },
  { text: "VERIFYING SHA-256 INTEGRITY…", delay: 900 },
  { text: "MATCHING STUDENT PROFILE…", delay: 1400 },
  { text: "DECRYPTING GRADE PAYLOAD…", delay: 1900 },
  { text: "VALIDATING AUTH TOKEN…", delay: 2300 },
];

/* ------------------------------------------------------------------ */
/*  Terminal Line                                                      */
/* ------------------------------------------------------------------ */

const TerminalLine: React.FC<{
  text: string;
  delay: number;
  done: boolean;
  isLast: boolean;
}> = ({ text, delay, done, isLast }) => {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(t);
  }, [delay]);

  if (!visible) return null;

  return (
    <motion.div
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-2 font-mono text-[10px]"
    >
      {done ? (
        <CheckCircle2 className="h-3 w-3 text-emerald-400 shrink-0" />
      ) : isLast ? (
        <motion.span
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ repeat: Infinity, duration: 0.8 }}
          className="h-3 w-3 text-cyan-400 shrink-0 flex items-center justify-center"
        >
          ▸
        </motion.span>
      ) : (
        <CheckCircle2 className="h-3 w-3 text-emerald-400/50 shrink-0" />
      )}
      <span
        className={
          done
            ? "text-emerald-400/70"
            : isLast
              ? "text-cyan-400 animate-pulse"
              : "text-white/30"
        }
      >
        {text}
      </span>
    </motion.div>
  );
};

/* ------------------------------------------------------------------ */
/*  Main Component                                                     */
/* ------------------------------------------------------------------ */

export const StudentLogin: React.FC<{
  onAuthenticated: (student: StudentInfo, grades: GradeEntry[]) => void;
}> = ({ onAuthenticated }) => {
  const router = useRouter();

  const [regNo, setRegNo] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [scanPhase, setScanPhase] = useState(-1);
  const [scanDone, setScanDone] = useState(false);
  const [foundName, setFoundName] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Hook must be called at the top level — NOT inside a callback
  const authFetch = useAuthFetch();

  /* Auto-focus on mount */
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /* Advance scan phase ticker */
  useEffect(() => {
    if (!isSearching) return;
    setScanPhase(0);
    const intervals: number[] = [];
    SCAN_PHASES.forEach((phase, i) => {
      intervals.push(setTimeout(() => setScanPhase(i), phase.delay) as unknown as number);
    });
    return () => intervals.forEach((id) => clearTimeout(id));
  }, [isSearching]);

  /* ---------- Real search ---------- */
  const handleSearch = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();

      const cleaned = regNo.trim();
      if (cleaned.length < 3) {
        setError("Please enter a valid Register Number");
        return;
      }

      setError("");
      setIsSearching(true);
      setScanDone(false);
      setFoundName(null);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await authFetch(
          `${API_URL}/api/students/${encodeURIComponent(cleaned)}/grades`,
          { signal: controller.signal },
        );

        if (!res.ok) {
          if (res.status === 404) throw new Error("STUDENT_NOT_FOUND");
          throw new Error("SERVER_ERROR");
        }

        const data = await res.json();
        const student: StudentInfo = data.student;
        const grades: GradeEntry[] = data.grades || [];

        setFoundName(student.name);

        // Wait for the terminal animation to feel satisfying (min 2.6s)
        const minDelay = Math.max(
          0,
          2600 - (Date.now() - performance.now()),
        );
        await new Promise((r) => setTimeout(r, minDelay > 200 ? 300 : minDelay));

        setScanDone(true);

        // Brief pause to show ✅ ALL GREEN state
        await new Promise((r) => setTimeout(r, 800));

        // Navigate
        onAuthenticated(student, grades);
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        const msg = (err as Error).message;
        if (msg === "STUDENT_NOT_FOUND") {
          setError(
            `Register number "${cleaned}" not found in the institutional ledger.`,
          );
        } else {
          setError("Connection to institutional server failed. Try again.");
        }
        setIsSearching(false);
        setScanPhase(-1);
      }
    },
    [regNo, onAuthenticated],
  );

  /* ---------- Render ---------- */
  return (
    <div className="min-h-screen bg-[#020617] flex flex-col items-center justify-center p-6 overflow-hidden relative">
      {/* ── Ambient Gradients ── */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-cyan-500/10 rounded-full blur-[120px] animate-pulse" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-600/10 rounded-full blur-[120px] animate-pulse" />
      <div className="absolute top-[30%] right-[20%] w-[20%] h-[20%] bg-indigo-500/5 rounded-full blur-[100px]" />

      {/* ── Main Container ── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="w-full max-w-md relative z-10"
      >
        {/* Brand Identity */}
        <div className="flex flex-col items-center mb-12">
          <motion.div
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.15, type: "spring", damping: 15 }}
            className="p-4 bg-white/5 border border-white/10 rounded-3xl mb-4 backdrop-blur-xl shadow-2xl shadow-cyan-500/5"
          >
            <GraduationCap className="w-10 h-10 text-cyan-400" />
          </motion.div>
          <h1 className="text-3xl font-black italic text-white tracking-tighter uppercase">
            Aura<span className="text-cyan-500">Grade</span> Portal
          </h1>
          <p className="text-slate-500 text-[10px] font-bold tracking-[0.3em] uppercase mt-2.5">
            Student Intelligence Access
          </p>
        </div>

        {/* ── Login Card ── */}
        <div className="bg-white/[0.04] border border-white/[0.08] p-8 rounded-[2.5rem] backdrop-blur-2xl shadow-2xl shadow-black/50 relative overflow-hidden">
          {/* Subtle grid texture */}
          <div className="absolute inset-0 opacity-[0.03] bg-[repeating-linear-gradient(0deg,transparent,transparent_39px,rgba(255,255,255,0.15)_40px),repeating-linear-gradient(90deg,transparent,transparent_39px,rgba(255,255,255,0.15)_40px)]" />

          <form onSubmit={handleSearch} className="space-y-6 relative z-10">
            {/* Input */}
            <div>
              <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest ml-1 mb-2.5 block flex items-center gap-1.5">
                <Lock className="h-2.5 w-2.5" />
                University Register Number
              </label>
              <div className="relative">
                <input
                  ref={inputRef}
                  type="text"
                  value={regNo}
                  onChange={(e) => {
                    setRegNo(e.target.value.toUpperCase());
                    if (error) setError("");
                  }}
                  placeholder="e.g. 21AD045"
                  className="w-full bg-black/50 border border-white/[0.08] rounded-2xl py-5 px-6 text-xl font-mono font-bold text-white placeholder:text-white/[0.08] outline-none focus:border-cyan-500/40 focus:shadow-[0_0_20px_rgba(6,182,212,0.08)] transition-all pr-14"
                  disabled={isSearching}
                />
                <div className="absolute right-4 top-1/2 -translate-y-1/2 p-2">
                  <Fingerprint
                    className={`w-6 h-6 transition-colors duration-300 ${
                      regNo.length >= 3
                        ? "text-cyan-500"
                        : "text-slate-700"
                    }`}
                  />
                </div>
              </div>
            </div>

            {/* Error */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-start gap-2 text-rose-400 text-xs font-semibold px-1"
                >
                  <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isSearching}
              className="w-full group relative overflow-hidden py-5 rounded-2xl bg-white text-black font-black text-lg italic uppercase transition-all active:scale-[0.97] disabled:opacity-50 disabled:pointer-events-none"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-400 to-blue-500 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <span className="relative z-10 flex items-center justify-center gap-2.5 group-hover:text-white transition-colors duration-300">
                {isSearching ? (
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{
                      repeat: Infinity,
                      duration: 1,
                      ease: "linear",
                    }}
                  >
                    <Search className="w-6 h-6" />
                  </motion.div>
                ) : (
                  <>
                    Retrieve Marks <ArrowRight className="w-5 h-5" />
                  </>
                )}
              </span>
            </button>
          </form>

          {/* ── Terminal Scan Overlay ── */}
          <AnimatePresence>
            {isSearching && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, transition: { duration: 0.3 } }}
                className="absolute inset-0 bg-black/95 backdrop-blur-xl flex flex-col items-center justify-center p-8 z-20"
              >
                {/* Scanning bar */}
                <div className="w-full max-w-[220px] h-1 bg-white/[0.06] rounded-full overflow-hidden mb-6">
                  {scanDone ? (
                    <motion.div
                      initial={{ width: "80%" }}
                      animate={{ width: "100%" }}
                      className="h-full bg-emerald-500 rounded-full shadow-[0_0_12px_rgba(16,185,129,0.5)]"
                    />
                  ) : (
                    <motion.div
                      initial={{ x: "-100%" }}
                      animate={{ x: "200%" }}
                      transition={{
                        repeat: Infinity,
                        duration: 1.2,
                        ease: "linear",
                      }}
                      className="w-[40%] h-full bg-cyan-500 rounded-full shadow-[0_0_15px_rgba(6,182,212,0.6)]"
                    />
                  )}
                </div>

                {/* Terminal lines */}
                <div className="space-y-2 w-full max-w-[260px]">
                  {SCAN_PHASES.map((phase, i) => (
                    <TerminalLine
                      key={phase.text}
                      text={phase.text}
                      delay={phase.delay}
                      done={scanDone}
                      isLast={i === scanPhase && !scanDone}
                    />
                  ))}
                </div>

                {/* Found student name reveal */}
                <AnimatePresence>
                  {scanDone && foundName && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      className="mt-6 flex flex-col items-center"
                    >
                      <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm mb-1">
                        <CheckCircle2 className="h-4 w-4" />
                        Identity Verified
                      </div>
                      <p className="text-white font-black text-lg italic uppercase tracking-tight">
                        {foundName}
                      </p>
                      <p className="text-[10px] text-white/20 font-mono mt-1 uppercase">
                        {regNo}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Status icons */}
                <div className="flex items-center gap-4 mt-6">
                  <Database
                    className={`h-4 w-4 transition-colors duration-500 ${scanPhase >= 1 ? "text-cyan-400/60" : "text-white/10"}`}
                  />
                  <Shield
                    className={`h-4 w-4 transition-colors duration-500 ${scanPhase >= 2 ? "text-cyan-400/60" : "text-white/10"}`}
                  />
                  <Sparkles
                    className={`h-4 w-4 transition-colors duration-500 ${scanPhase >= 4 ? "text-cyan-400/60" : "text-white/10"}`}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* ── Bottom Nav ── */}
        <div className="flex items-center justify-center gap-6 mt-8">
          <button
            onClick={() => router.push("/login")}
            className="text-[10px] text-slate-500 uppercase tracking-[0.2em] font-bold hover:text-white/40 transition-colors"
          >
            Staff Login →
          </button>
          <span className="text-white/5">|</span>
          <button
            onClick={() => router.push("/")}
            className="text-[10px] text-slate-500 uppercase tracking-[0.2em] font-bold hover:text-white/40 transition-colors"
          >
            Main Portal →
          </button>
        </div>

        {/* Footer */}
        <p className="text-center text-slate-600/60 text-[9px] mt-6 uppercase font-bold tracking-[0.4em] flex items-center justify-center gap-2">
          <Cpu className="h-3 w-3" />
          Restricted Access · Institutional Use Only
        </p>
      </motion.div>
    </div>
  );
};

export default StudentLogin;
