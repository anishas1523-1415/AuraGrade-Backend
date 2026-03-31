"use client";

import React, { useRef } from "react";
import { motion, useScroll, useTransform, useInView } from "framer-motion";
import {
  Sparkles,
  ShieldCheck,
  Zap,
  BarChart3,
  ChevronRight,
  Globe,
  Mic,
  ScanLine,
  Brain,
  Lock,
  FileSpreadsheet,
  ShieldAlert,
  GraduationCap,
  Users,
  Eye,
  Cpu,
  ArrowRight,
  CheckCircle2,
  Activity,
} from "lucide-react";
import Link from "next/link";

/* ------------------------------------------------------------------ */
/*  Stat Counter — animated number on scroll                           */
/* ------------------------------------------------------------------ */

const StatCounter: React.FC<{
  value: string;
  label: string;
  suffix?: string;
}> = ({ value, label, suffix = "" }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={inView ? { opacity: 1, y: 0 } : {}}
      transition={{ duration: 0.6 }}
      className="text-center"
    >
      <p className="text-4xl md:text-5xl font-black italic text-white tracking-tighter">
        {value}
        <span className="text-cyan-400">{suffix}</span>
      </p>
      <p className="text-[10px] text-slate-500 font-bold uppercase tracking-[0.2em] mt-2">
        {label}
      </p>
    </motion.div>
  );
};

/* ------------------------------------------------------------------ */
/*  Architecture Layer — for the pipeline section                      */
/* ------------------------------------------------------------------ */

const ArchLayer: React.FC<{
  step: number;
  title: string;
  desc: string;
  icon: React.ReactNode;
  color: string;
  delay: number;
}> = ({ step, title, desc, icon, color, delay }) => {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, x: -30 }}
      animate={inView ? { opacity: 1, x: 0 } : {}}
      transition={{ duration: 0.5, delay }}
      className="flex items-start gap-5 group"
    >
      <div className="relative flex flex-col items-center">
        <div
          className={`w-12 h-12 rounded-2xl border flex items-center justify-center shrink-0 transition-colors ${color}`}
        >
          {icon}
        </div>
        <div className="w-px h-full bg-white/5 absolute top-14" />
      </div>
      <div className="pb-10">
        <p className="text-[9px] font-black text-white/20 uppercase tracking-[0.3em] mb-1">
          Pass {step}
        </p>
        <h4 className="text-lg font-black italic uppercase tracking-tighter text-white mb-1.5">
          {title}
        </h4>
        <p className="text-sm text-slate-400 leading-relaxed max-w-sm">
          {desc}
        </p>
      </div>
    </motion.div>
  );
};

/* ------------------------------------------------------------------ */
/*  Main Landing Page                                                  */
/* ------------------------------------------------------------------ */

export const LandingPage = () => {
  const { scrollY } = useScroll();
  const heroY = useTransform(scrollY, [0, 600], [0, -120]);
  const heroRotateX = useTransform(scrollY, [0, 600], [12, 0]);
  const heroScale = useTransform(scrollY, [0, 600], [0.95, 1]);
  const heroOpacity = useTransform(scrollY, [0, 800], [1, 0.6]);

  return (
    <div className="min-h-screen bg-[#020617] text-white selection:bg-cyan-500/30 overflow-x-hidden">
      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  NAVIGATION                                                */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <nav className="fixed top-0 w-full z-50 border-b border-white/5 bg-[#020617]/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Zap className="w-5 h-5 text-black fill-current" />
            </div>
            <span className="text-xl font-black italic tracking-tighter uppercase">
              AuraGrade
            </span>
          </div>

          <div className="hidden md:flex items-center gap-8 text-[10px] font-black uppercase tracking-[0.15em] text-slate-500">
            <a
              href="#pipeline"
              className="hover:text-cyan-400 transition-colors"
            >
              Agents
            </a>
            <a
              href="#security"
              className="hover:text-cyan-400 transition-colors"
            >
              Integrity
            </a>
            <a
              href="#features"
              className="hover:text-cyan-400 transition-colors"
            >
              Features
            </a>
            <a href="#stack" className="hover:text-cyan-400 transition-colors">
              Stack
            </a>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="hidden sm:inline-flex text-[10px] font-black uppercase tracking-wider text-slate-400 hover:text-white transition-colors px-3 py-2"
            >
              Staff Login
            </Link>
            <Link
              href="/configure"
              className="px-5 py-2.5 bg-white text-black text-[10px] font-black uppercase italic rounded-full hover:bg-cyan-400 hover:shadow-lg hover:shadow-cyan-500/20 transition-all"
            >
              Launch Portal
            </Link>
          </div>
        </div>
      </nav>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  HERO SECTION                                              */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section className="relative pt-36 pb-10 px-6 flex flex-col items-center">
        {/* Ambient glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[600px] bg-cyan-500/8 blur-[150px] rounded-full pointer-events-none" />
        <div className="absolute top-40 right-1/4 w-[300px] h-[300px] bg-violet-500/5 blur-[100px] rounded-full pointer-events-none" />

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
          className="text-center z-10 max-w-5xl"
        >
          {/* Pill badge */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3 }}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/[0.04] border border-white/10 text-[9px] font-black text-cyan-400 uppercase tracking-[0.2em] mb-8"
          >
            <Sparkles className="w-3 h-3" />
            Powered by Gemini 2.5 Flash · Pinecone · Supabase
          </motion.div>

          {/* Main Headline */}
          <h1 className="text-5xl sm:text-7xl md:text-8xl lg:text-[6.5rem] font-black italic tracking-[-0.04em] uppercase leading-[0.88] mb-8">
            The Future of{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500">
              Institutional
            </span>{" "}
            Grading
          </h1>

          {/* Tagline */}
          <p className="text-base sm:text-lg text-slate-400 max-w-2xl mx-auto mb-12 font-medium leading-relaxed">
            A 3-pass agentic AI system with multimodal vision, SHA-256 digital
            seals, cross-script collusion detection, and real-time semantic gap
            analysis — built for universities that demand absolute integrity.
          </p>

          {/* CTAs */}
          <div className="flex flex-wrap justify-center gap-4 mb-24">
            <Link
              href="/configure"
              className="group px-8 py-4 bg-cyan-500 text-black font-black uppercase italic rounded-2xl flex items-center gap-2 hover:scale-[1.03] hover:shadow-xl hover:shadow-cyan-500/25 transition-all text-sm"
            >
              Start Grading
              <ChevronRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="/grading"
              className="px-8 py-4 bg-blue-500 text-white font-black uppercase italic rounded-2xl hover:bg-blue-600 transition-all text-sm flex items-center gap-2"
            >
              <Cpu className="w-4 h-4" />
              Staff Grading
            </Link>
            <Link
              href="/student"
              className="px-8 py-4 bg-white/[0.04] border border-white/10 text-white font-black uppercase italic rounded-2xl hover:bg-white/[0.08] hover:border-white/20 transition-all text-sm flex items-center gap-2"
            >
              <GraduationCap className="w-4 h-4" />
              Student Portal
            </Link>
          </div>
        </motion.div>

        {/* ── 3D Floating Dashboard Preview ── */}
        <motion.div
          style={{
            rotateX: heroRotateX,
            y: heroY,
            scale: heroScale,
            opacity: heroOpacity,
          }}
          className="relative w-full max-w-5xl z-10"
        >
          <div className="w-full aspect-[16/9] bg-slate-900/80 rounded-3xl border border-white/10 shadow-[0_0_120px_rgba(6,182,212,0.12)] overflow-hidden relative group backdrop-blur-sm">
            {/* Mock Dashboard UI */}
            <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-900 to-black p-6 md:p-8">
              <div className="flex gap-4 h-full">
                {/* Left panel — grading area */}
                <div className="w-2/3 bg-black/40 rounded-2xl border border-white/5 relative overflow-hidden">
                  {/* Scan line animation */}
                  <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-cyan-500/60 to-transparent animate-scan" />
                  <div className="p-4 border-b border-white/5 flex justify-between items-center">
                    <div className="flex items-center gap-2">
                      <ScanLine className="w-3.5 h-3.5 text-cyan-500" />
                      <div className="w-20 h-2 bg-white/10 rounded-full" />
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                      <div className="w-16 h-2 bg-cyan-500/30 rounded-full" />
                    </div>
                  </div>
                  {/* Mock annotations */}
                  <div className="p-4 space-y-3">
                    {[75, 55, 85, 40, 65].map((w, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <div
                          className="h-2 bg-white/[0.06] rounded-full"
                          style={{ width: `${w}%` }}
                        />
                        {i === 1 && (
                          <div className="w-4 h-4 rounded border border-amber-500/30 bg-amber-500/10 flex items-center justify-center">
                            <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                          </div>
                        )}
                        {i === 3 && (
                          <div className="w-4 h-4 rounded border border-emerald-500/30 bg-emerald-500/10 flex items-center justify-center">
                            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-400" />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right panels */}
                <div className="w-1/3 flex flex-col gap-4">
                  {/* Score card */}
                  <div className="flex-1 bg-white/[0.03] rounded-2xl border border-white/5 p-4 flex flex-col justify-between">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-cyan-500" />
                      <span className="text-[9px] font-bold text-white/20 uppercase tracking-wider">
                        AI Score
                      </span>
                    </div>
                    <div>
                      <p className="text-3xl font-black italic text-white tracking-tighter">
                        8.5
                        <span className="text-sm text-white/20 font-normal">
                          /10
                        </span>
                      </p>
                      <div className="w-full h-1.5 rounded-full bg-white/[0.06] mt-2 overflow-hidden">
                        <div className="h-full w-[85%] rounded-full bg-gradient-to-r from-cyan-500 to-blue-500" />
                      </div>
                    </div>
                  </div>

                  {/* Sentinel card */}
                  <div className="flex-1 bg-rose-500/[0.06] rounded-2xl border border-rose-500/15 p-4 flex flex-col justify-between">
                    <div className="flex items-center gap-2">
                      <ShieldAlert className="w-4 h-4 text-rose-500" />
                      <span className="text-[9px] font-bold text-rose-400/40 uppercase tracking-wider">
                        Sentinel
                      </span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-emerald-500" />
                        <span className="text-[10px] text-emerald-400 font-bold">
                          CLEAR
                        </span>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-rose-500/10 mt-2" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Hover overlay */}
            <div className="absolute inset-0 bg-cyan-500/[0.03] opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
          </div>

          {/* Reflection */}
          <div className="w-[80%] h-20 mx-auto bg-cyan-500/[0.04] blur-3xl rounded-full -mt-6 pointer-events-none" />
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  STATS BAR                                                 */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 border border-white/5 rounded-3xl bg-white/[0.015] p-8 md:p-12">
          <StatCounter value="3" suffix="-Pass" label="Agentic Pipeline" />
          <StatCounter value="SHA" suffix="-256" label="Digital Seals" />
          <StatCounter value="99.9" suffix="%" label="Grading Accuracy" />
          <StatCounter value="<2" suffix="s" label="Per Answer Sheet" />
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  AGENTIC PIPELINE                                          */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section id="pipeline" className="max-w-5xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mb-16 text-center"
        >
          <p className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em] mb-3">
            Architecture
          </p>
          <h2 className="text-4xl md:text-5xl font-black italic uppercase tracking-tighter">
            3-Pass Agentic Engine
          </h2>
          <p className="text-sm text-slate-500 mt-4 max-w-xl mx-auto leading-relaxed">
            Every answer sheet passes through three independent AI agents — a
            Grader, an Auditor, and an HOD Review — mimicking a real university
            evaluation committee.
          </p>
        </motion.div>

        <div className="max-w-xl mx-auto">
          <ArchLayer
            step={1}
            title="Vision Grader"
            desc="Gemini 2.5 Flash scans the handwritten answer via multimodal OCR, extracts text + diagrams, and grades each sub-question against the model answer rubric."
            icon={<Eye className="w-5 h-5 text-cyan-400" />}
            color="bg-cyan-500/10 border-cyan-500/20"
            delay={0}
          />
          <ArchLayer
            step={2}
            title="Audit Agent"
            desc="A second AI agent re-examines flagged annotations and confidence deltas, adjusting scores where the Grader was uncertain — like a built-in internal moderator."
            icon={<Brain className="w-5 h-5 text-violet-400" />}
            color="bg-violet-500/10 border-violet-500/20"
            delay={0.15}
          />
          <ArchLayer
            step={3}
            title="HOD Finaliser"
            desc="The third pass generates a verdict summary with a confidence-weighted consensus score. Professors can override with one click — or one voice command."
            icon={<ShieldCheck className="w-5 h-5 text-emerald-400" />}
            color="bg-emerald-500/10 border-emerald-500/20"
            delay={0.3}
          />
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  SECURITY & INTEGRITY                                      */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section
        id="security"
        className="relative py-20 overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-rose-500/[0.02] to-transparent pointer-events-none" />

        <div className="max-w-6xl mx-auto px-6">
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            viewport={{ once: true }}
            className="mb-16 text-center"
          >
            <p className="text-[10px] font-black text-rose-400 uppercase tracking-[0.3em] mb-3">
              Integrity Layer
            </p>
            <h2 className="text-4xl md:text-5xl font-black italic uppercase tracking-tighter">
              Zero-Trust Security
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Sentinel card */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="p-8 bg-rose-500/[0.04] border border-rose-500/10 rounded-[2rem] group hover:border-rose-500/25 transition-all"
            >
              <div className="w-14 h-14 bg-rose-500/10 rounded-2xl flex items-center justify-center mb-6">
                <ShieldAlert className="w-7 h-7 text-rose-500" />
              </div>
              <h3 className="text-xl font-black italic uppercase tracking-tighter mb-3">
                Similarity Sentinel
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Every graded script is vectorised into Pinecone and compared
                against all peers in the same assessment. Not keyword
                matching — <strong className="text-white/70">semantic cosine similarity</strong> via
                llama-text-embed-v2 catches students who paraphrase from each
                other.
              </p>
              <div className="flex items-center gap-3">
                <div className="flex -space-x-2">
                  {["A", "B"].map((l) => (
                    <div
                      key={l}
                      className="w-8 h-8 rounded-full bg-rose-500/10 border-2 border-[#020617] flex items-center justify-center text-[9px] font-bold text-rose-400"
                    >
                      {l}
                    </div>
                  ))}
                </div>
                <div className="h-px flex-1 bg-rose-500/20" />
                <span className="text-[10px] font-black text-rose-400 bg-rose-500/10 px-2 py-1 rounded-lg">
                  96% MATCH
                </span>
              </div>
            </motion.div>

            {/* Digital seal card */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="p-8 bg-white/[0.02] border border-white/10 rounded-[2rem] group hover:border-cyan-500/20 transition-all"
            >
              <div className="w-14 h-14 bg-cyan-500/10 rounded-2xl flex items-center justify-center mb-6">
                <Lock className="w-7 h-7 text-cyan-400" />
              </div>
              <h3 className="text-xl font-black italic uppercase tracking-tighter mb-3">
                SHA-256 Digital Seal
              </h3>
              <p className="text-sm text-slate-400 leading-relaxed mb-4">
                Every exported marks ledger is hashed with SHA-256 and stamped
                into the Excel footer. If anyone edits even one cell, the hash
                breaks — providing{" "}
                <strong className="text-white/70">
                  cryptographic tamper detection
                </strong>{" "}
                for the Controller of Examinations.
              </p>
              <div className="bg-black/40 rounded-xl px-4 py-2.5 font-mono text-[10px] text-cyan-400/60 tracking-wide overflow-hidden">
                a3b2c1…f9e8d7 <span className="text-white/15">| SHA-256</span>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  FEATURE GRID                                              */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section id="features" className="max-w-7xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mb-16 text-center"
        >
          <p className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em] mb-3">
            Capabilities
          </p>
          <h2 className="text-4xl md:text-5xl font-black italic uppercase tracking-tighter">
            Full-Spectrum Platform
          </h2>
        </motion.div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[
            {
              icon: <Zap className="w-5 h-5" />,
              title: "3-Pass Agentic",
              desc: "Grader → Auditor → HOD agents ensure consensus-grade accuracy on every answer sheet.",
              color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/15",
            },
            {
              icon: <Globe className="w-5 h-5" />,
              title: "RAG Knowledge Base",
              desc: "Model answers embedded in Pinecone for retrieval-augmented grading with contextual rubrics.",
              color: "text-blue-400 bg-blue-500/10 border-blue-500/15",
            },
            {
              icon: <BarChart3 className="w-5 h-5" />,
              title: "Semantic Gap Analysis",
              desc: "Class-wide knowledge mapping with radar charts and AI-generated remediation plans.",
              color: "text-violet-400 bg-violet-500/10 border-violet-500/15",
            },
            {
              icon: <ScanLine className="w-5 h-5" />,
              title: "Diagram Validation",
              desc: "Handwritten flowcharts and ER diagrams auto-converted to Mermaid.js and structurally validated.",
              color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/15",
            },
            {
              icon: <Mic className="w-5 h-5" />,
              title: "AuraVoice Control",
              desc: "\"Set marks to 15\" — hands-free grading via Web Speech API with regex intent parsing.",
              color: "text-amber-400 bg-amber-500/10 border-amber-500/15",
            },
            {
              icon: <FileSpreadsheet className="w-5 h-5" />,
              title: "Institutional Export",
              desc: "Styled Excel ledgers with sentinel flags, openpyxl formatting, and a tamper-proof SHA-256 footer.",
              color: "text-rose-400 bg-rose-500/10 border-rose-500/15",
            },
          ].map((feature, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07 }}
              whileHover={{ y: -8 }}
              className="p-7 bg-white/[0.02] border border-white/[0.06] rounded-[1.5rem] hover:border-white/15 transition-all group"
            >
              <div
                className={`w-11 h-11 rounded-xl border flex items-center justify-center mb-5 ${feature.color}`}
              >
                {feature.icon}
              </div>
              <h3 className="text-base font-black italic uppercase tracking-tighter mb-2 group-hover:text-white transition-colors">
                {feature.title}
              </h3>
              <p className="text-[13px] text-slate-500 leading-relaxed">
                {feature.desc}
              </p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  TECH STACK                                                */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section id="stack" className="max-w-5xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mb-12 text-center"
        >
          <p className="text-[10px] font-black text-cyan-400 uppercase tracking-[0.3em] mb-3">
            Under the Hood
          </p>
          <h2 className="text-4xl md:text-5xl font-black italic uppercase tracking-tighter">
            Built With
          </h2>
        </motion.div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {[
            { name: "Next.js 15", icon: <Globe className="w-4 h-4" /> },
            { name: "React 19", icon: <Cpu className="w-4 h-4" /> },
            { name: "FastAPI", icon: <Zap className="w-4 h-4" /> },
            { name: "Google Gemini", icon: <Sparkles className="w-4 h-4" /> },
            { name: "Pinecone", icon: <Brain className="w-4 h-4" /> },
            { name: "Supabase", icon: <Lock className="w-4 h-4" /> },
            { name: "Framer Motion", icon: <Activity className="w-4 h-4" /> },
            { name: "Tailwind CSS", icon: <Eye className="w-4 h-4" /> },
          ].map((tech, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05 }}
              className="flex items-center gap-3 px-5 py-4 bg-white/[0.02] border border-white/[0.06] rounded-xl hover:border-white/15 transition-all"
            >
              <span className="text-white/25">{tech.icon}</span>
              <span className="text-xs font-bold text-white/50">
                {tech.name}
              </span>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  CTA SECTION                                               */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <section className="max-w-4xl mx-auto px-6 py-20">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="relative rounded-[2rem] bg-gradient-to-br from-cyan-500/10 via-transparent to-violet-500/10 border border-white/10 p-12 md:p-16 text-center overflow-hidden"
        >
          <div className="absolute -top-20 -left-20 w-60 h-60 bg-cyan-500/10 blur-[100px] rounded-full pointer-events-none" />
          <div className="absolute -bottom-20 -right-20 w-60 h-60 bg-violet-500/10 blur-[100px] rounded-full pointer-events-none" />

          <h2 className="text-3xl md:text-5xl font-black italic uppercase tracking-tighter mb-4 relative z-10">
            Ready to Transform Grading?
          </h2>
          <p className="text-sm text-slate-400 mb-8 max-w-lg mx-auto relative z-10">
            Upload an answer sheet, choose a rubric, and watch the 3-pass
            agentic pipeline deliver graded, audited, sealed results in under 2
            seconds.
          </p>
          <div className="flex flex-wrap justify-center gap-4 relative z-10">
            <Link
              href="/configure"
              className="group px-8 py-4 bg-cyan-500 text-black font-black uppercase italic rounded-2xl flex items-center gap-2 hover:scale-[1.03] hover:shadow-xl hover:shadow-cyan-500/25 transition-all text-sm"
            >
              Launch AuraGrade
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="/admin/dashboard"
              className="px-8 py-4 bg-white/[0.04] border border-white/10 text-white font-black uppercase italic rounded-2xl hover:bg-white/[0.08] transition-all text-sm flex items-center gap-2"
            >
              <Users className="w-4 h-4" />
              CoE Dashboard
            </Link>
          </div>
        </motion.div>
      </section>

      {/* ═══════════════════════════════════════════════════════════ */}
      {/*  FOOTER                                                    */}
      {/* ═══════════════════════════════════════════════════════════ */}
      <footer className="border-t border-white/5 py-8">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-cyan-500 rounded-lg flex items-center justify-center">
              <Zap className="w-3.5 h-3.5 text-black fill-current" />
            </div>
            <span className="text-sm font-black italic uppercase tracking-tighter text-white/40">
              AuraGrade
            </span>
          </div>
          <p className="text-[10px] text-white/15 font-bold uppercase tracking-wider">
            Agentic AI · Multimodal Vision · Institutional Compliance ·
            SHA-256 Sealed
          </p>
          <div className="flex items-center gap-4 text-[10px] font-bold text-white/20 uppercase tracking-wider">
            <Link href="/login" className="hover:text-white/40 transition-colors">
              Staff
            </Link>
            <Link
              href="/student"
              className="hover:text-white/40 transition-colors"
            >
              Student
            </Link>
            <Link
              href="/admin/dashboard"
              className="hover:text-white/40 transition-colors"
            >
              Admin
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
