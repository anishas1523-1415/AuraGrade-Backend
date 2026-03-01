"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Camera,
  RefreshCcw,
  CheckCircle2,
  Scan,
  Zap,
  Package,
  X,
  AlertTriangle,
  ArrowLeft,
  User,
  BookOpen,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useAuthFetch } from "@/lib/use-auth-fetch";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface ScannedScript {
  id: number;
  regNo: string;
  subjectCode: string;
  confidence: string;
  studentName?: string;
  timestamp: Date;
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const MobileScanner: React.FC = () => {
  const router = useRouter();
  const authFetch = useAuthFetch();

  const [isScanning, setIsScanning] = useState(false);
  const [lastScanned, setLastScanned] = useState<ScannedScript | null>(null);
  const [batchCount, setBatchCount] = useState(0);
  const [batch, setBatch] = useState<ScannedScript[]>([]);
  const [torch, setTorch] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showBatchList, setShowBatchList] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  /* ---------- Camera lifecycle ---------- */
  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "environment",
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraActive(true);
    } catch {
      // Camera not available — fall back to file input
      setCameraActive(false);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setCameraActive(false);
  }, []);

  useEffect(() => {
    startCamera();
    return () => stopCamera();
  }, [startCamera, stopCamera]);

  /* ---------- Torch toggle ---------- */
  useEffect(() => {
    if (!streamRef.current) return;
    const track = streamRef.current.getVideoTracks()[0];
    if (track && "applyConstraints" in track) {
      try {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (track as any).applyConstraints({
          advanced: [{ torch } as MediaTrackConstraintSet],
        });
      } catch {
        // torch not supported on this device
      }
    }
  }, [torch]);

  /* ---------- Capture frame from camera ---------- */
  const captureFrame = useCallback((): Blob | null => {
    if (!videoRef.current || !cameraActive) return null;
    const canvas = document.createElement("canvas");
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(videoRef.current, 0, 0);
    let blob: Blob | null = null;
    canvas.toBlob((b) => {
      blob = b;
    }, "image/jpeg", 0.9);
    // toBlob is async — use synchronous fallback
    const dataUrl = canvas.toDataURL("image/jpeg", 0.9);
    const binary = atob(dataUrl.split(",")[1]);
    const arr = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) arr[i] = binary.charCodeAt(i);
    return new Blob([arr], { type: "image/jpeg" });
  }, [cameraActive]);

  /* ---------- Core scan logic ---------- */
  const processScan = useCallback(
    async (imageBlob: Blob) => {
      setIsScanning(true);
      setError(null);
      setLastScanned(null);

      try {
        const formData = new FormData();
        formData.append("file", imageBlob, "scan.jpg");

        const res = await authFetch(
          `${API_URL}/api/parse-header?match_db=true`,
          { method: "POST", body: formData },
        );

        if (!res.ok) {
          const body = await res
            .json()
            .catch(() => ({ detail: "Server error" }));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        const header = data.header || {};
        const student = data.student || {};

        const regNo = header.reg_no || "UNKNOWN";
        const subjectCode = header.subject_code || "—";
        const confidence = header.confidence || "LOW";
        const studentName = student.name || undefined;

        const scanned: ScannedScript = {
          id: Date.now(),
          regNo,
          subjectCode,
          confidence,
          studentName,
          timestamp: new Date(),
        };

        setLastScanned(scanned);
        setBatchCount((prev) => prev + 1);
        setBatch((prev) => [scanned, ...prev]);

        // Haptic feedback
        if (navigator.vibrate) {
          navigator.vibrate(confidence === "HIGH" ? 50 : [50, 30, 50]);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Scan failed");
        if (navigator.vibrate) navigator.vibrate([100, 50, 100, 50, 100]);
      } finally {
        setIsScanning(false);
      }
    },
    [authFetch],
  );

  /* ---------- Trigger scan ---------- */
  const triggerScan = useCallback(() => {
    if (cameraActive) {
      const blob = captureFrame();
      if (blob) {
        processScan(blob);
        return;
      }
    }
    // Fallback to file picker
    fileInputRef.current?.click();
  }, [cameraActive, captureFrame, processScan]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processScan(file);
      e.target.value = "";
    }
  };

  /* ---------- Render ---------- */
  return (
    <div className="fixed inset-0 bg-black flex flex-col font-sans select-none">
      {/* Hidden file input fallback */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={handleFileSelect}
      />

      {/* ── Top Status Bar ── */}
      <div className="absolute top-0 left-0 right-0 z-30 flex items-center justify-between px-4 py-3 bg-gradient-to-b from-black/80 to-transparent">
        <button
          onClick={() => {
            stopCamera();
            router.push("/");
          }}
          className="p-2 rounded-xl bg-white/10 backdrop-blur-md"
        >
          <ArrowLeft className="h-5 w-5 text-white" />
        </button>

        <div className="flex items-center gap-2">
          {cameraActive ? (
            <span className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-bold uppercase tracking-wider">
              <Wifi className="h-3 w-3" /> Live
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-[10px] text-amber-400 font-bold uppercase tracking-wider">
              <WifiOff className="h-3 w-3" /> File Mode
            </span>
          )}
        </div>

        <button
          onClick={() => setShowBatchList(!showBatchList)}
          className="p-2 rounded-xl bg-white/10 backdrop-blur-md relative"
        >
          <Package className="h-5 w-5 text-white" />
          {batchCount > 0 && (
            <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-cyan-500 text-[10px] text-black font-bold flex items-center justify-center">
              {batchCount}
            </span>
          )}
        </button>
      </div>

      {/* ── Viewfinder Area ── */}
      <div className="relative flex-grow flex items-center justify-center overflow-hidden">
        {/* Camera Feed */}
        {cameraActive ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="absolute inset-0 w-full h-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 bg-slate-900 flex items-center justify-center">
            <div className="w-full h-full opacity-20 bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(255,255,255,0.03)_10px,rgba(255,255,255,0.03)_20px)]" />
            <div className="absolute flex flex-col items-center gap-3">
              <Camera className="h-12 w-12 text-white/20" />
              <p className="text-white/20 font-mono text-xs uppercase tracking-[0.2em]">
                Tap Capture to select image
              </p>
            </div>
          </div>
        )}

        {/* Vision HUD Overlay */}
        <div className="absolute inset-0 pointer-events-none">
          {/* Vignette borders */}
          <div className="absolute inset-0 border-[40px] sm:border-[60px] border-black/60" />

          {/* Scan target zone */}
          <div className="absolute inset-[40px] sm:inset-[60px]">
            <div className="w-full h-full relative border border-white/20">
              {/* Corner Brackets */}
              <div className="absolute top-0 left-0 w-8 h-8 border-t-4 border-l-4 border-cyan-500 rounded-tl-lg" />
              <div className="absolute top-0 right-0 w-8 h-8 border-t-4 border-r-4 border-cyan-500 rounded-tr-lg" />
              <div className="absolute bottom-0 left-0 w-8 h-8 border-b-4 border-l-4 border-cyan-500 rounded-bl-lg" />
              <div className="absolute bottom-0 right-0 w-8 h-8 border-b-4 border-r-4 border-cyan-500 rounded-br-lg" />

              {/* Crosshair center */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
                <div className="w-6 h-px bg-cyan-500/40" />
                <div className="w-px h-6 bg-cyan-500/40 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
              </div>

              {/* Scanning Line */}
              {isScanning && (
                <motion.div
                  initial={{ top: 0 }}
                  animate={{ top: "100%" }}
                  transition={{
                    duration: 1.2,
                    repeat: Infinity,
                    ease: "linear",
                  }}
                  className="absolute left-0 right-0 h-0.5 bg-cyan-400 shadow-[0_0_15px_cyan,0_0_30px_cyan]"
                />
              )}

              {/* Header region hint */}
              <div className="absolute top-0 left-0 right-0 h-[30%] border-b border-dashed border-cyan-500/20 flex items-center justify-center">
                <span className="text-[9px] text-cyan-500/40 font-mono uppercase tracking-widest">
                  Header Detection Zone
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Floating Detection Badge */}
        <AnimatePresence>
          {lastScanned && !isScanning && (
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.9 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
              className="absolute top-24 z-20"
            >
              <div
                className={`px-6 py-3 rounded-2xl font-black text-lg shadow-2xl flex items-center gap-3 ${
                  lastScanned.confidence === "HIGH"
                    ? "bg-emerald-500 text-black shadow-emerald-500/40"
                    : lastScanned.confidence === "MEDIUM"
                      ? "bg-amber-500 text-black shadow-amber-500/40"
                      : "bg-red-500 text-white shadow-red-500/40"
                }`}
              >
                <CheckCircle2 className="w-5 h-5" />
                <div>
                  <p className="text-lg font-black">{lastScanned.regNo}</p>
                  {lastScanned.studentName && (
                    <p className="text-[10px] font-semibold opacity-70">
                      {lastScanned.studentName}
                    </p>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error Badge */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="absolute bottom-4 left-4 right-4 z-20 flex items-center gap-2 px-4 py-3 rounded-xl bg-red-500/20 border border-red-500/30 backdrop-blur-md"
            >
              <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
              <p className="text-xs text-red-300 flex-1">{error}</p>
              <button onClick={() => setError(null)}>
                <X className="h-4 w-4 text-red-400" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Bottom Control Panel ── */}
      <div className="bg-slate-950 border-t border-white/10 p-6 pb-10 rounded-t-[2.5rem] relative z-20">
        {/* Session stats */}
        <div className="flex justify-between items-center mb-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest">
              Current Session
            </span>
            <span className="text-white font-mono text-xl font-bold flex items-center gap-2">
              <Package className="w-4 h-4 text-cyan-500" />
              {batchCount}{" "}
              <span className="text-slate-600 text-sm">SCRIPTS</span>
            </span>
          </div>

          {/* Torch toggle */}
          <button
            onClick={() => setTorch(!torch)}
            className={`p-4 rounded-full border transition-all ${
              torch
                ? "bg-amber-500 border-amber-400 text-black"
                : "bg-white/5 border-white/10 text-white"
            }`}
          >
            <Zap className={`w-6 h-6 ${torch ? "fill-current" : ""}`} />
          </button>
        </div>

        {/* Capture Button */}
        <button
          onClick={triggerScan}
          disabled={isScanning}
          className={`w-full py-6 rounded-2xl flex items-center justify-center gap-4 transition-all active:scale-95 ${
            isScanning
              ? "bg-slate-800 text-slate-500 cursor-not-allowed"
              : "bg-gradient-to-r from-cyan-600 to-blue-600 text-white shadow-lg shadow-cyan-900/30"
          }`}
        >
          {isScanning ? (
            <>
              <RefreshCcw className="w-6 h-6 animate-spin" />
              <span className="text-base font-bold uppercase tracking-tight">
                Detecting Header…
              </span>
            </>
          ) : (
            <>
              <Scan className="w-7 h-7" />
              <span className="text-xl font-black italic tracking-tight uppercase">
                Capture Script
              </span>
            </>
          )}
        </button>

        <p className="text-center text-[10px] text-slate-600 mt-5 uppercase font-bold tracking-[0.3em]">
          Powered by Gemini 3 Flash Vision
        </p>
      </div>

      {/* ── Batch List Drawer ── */}
      <AnimatePresence>
        {showBatchList && (
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="fixed inset-0 z-50 bg-slate-950 flex flex-col"
          >
            {/* Drawer header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-white/10">
              <div>
                <h2 className="text-lg font-black text-white uppercase tracking-tight">
                  Scanned Scripts
                </h2>
                <p className="text-[10px] text-white/30 font-mono">
                  {batch.length} script(s) this session
                </p>
              </div>
              <button
                onClick={() => setShowBatchList(false)}
                className="p-2 rounded-xl bg-white/10"
              >
                <X className="h-5 w-5 text-white" />
              </button>
            </div>

            {/* Script list */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
              {batch.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-white/20">
                  <Package className="h-10 w-10 mb-3 opacity-30" />
                  <p className="text-sm">No scripts scanned yet</p>
                </div>
              ) : (
                batch.map((s, i) => (
                  <motion.div
                    key={s.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.02 * i }}
                    className="flex items-center gap-4 px-4 py-3 rounded-xl border border-white/5 bg-white/[0.03]"
                  >
                    <div
                      className={`h-10 w-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                        s.confidence === "HIGH"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : s.confidence === "MEDIUM"
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {batch.length - i}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <User className="h-3 w-3 text-white/30" />
                        <span className="text-sm font-bold text-white font-mono">
                          {s.regNo}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5">
                        {s.studentName && (
                          <span className="text-[10px] text-white/40 truncate">
                            {s.studentName}
                          </span>
                        )}
                        <span className="text-[10px] text-white/20 flex items-center gap-1">
                          <BookOpen className="h-2.5 w-2.5" />
                          {s.subjectCode}
                        </span>
                      </div>
                    </div>
                    <span
                      className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded-full ${
                        s.confidence === "HIGH"
                          ? "bg-emerald-500/20 text-emerald-400"
                          : s.confidence === "MEDIUM"
                            ? "bg-amber-500/20 text-amber-400"
                            : "bg-red-500/20 text-red-400"
                      }`}
                    >
                      {s.confidence}
                    </span>
                  </motion.div>
                ))
              )}
            </div>

            {/* Bottom: back button */}
            <div className="px-6 py-5 border-t border-white/10">
              <button
                onClick={() => setShowBatchList(false)}
                className="w-full py-4 rounded-2xl bg-white/5 border border-white/10 text-white font-bold uppercase tracking-tight text-sm active:scale-95 transition-transform"
              >
                Back to Scanner
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MobileScanner;
