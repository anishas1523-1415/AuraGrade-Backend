"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Info, XCircle, ZoomIn, ZoomOut, Layers, Eye, EyeOff, ShieldCheck, ShieldAlert, RefreshCw } from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface Annotation {
  id: string;
  type: "key_term" | "error" | "diagram" | "partial" | "correction" | "penalty";
  label: string;
  description: string;
  points?: number;
  x: number;      // Percentage 0-100
  y: number;      // Percentage 0-100
  width: number;  // Percentage 0-100
  height: number; // Percentage 0-100
  /** Tracks Pass-2 audit state for predictive UI streaming */
  reviewState?: "pending" | "reviewing" | "confirmed" | "adjusted" | "rejected";
  /** Note from Pass-2 audit verdict */
  verdictNote?: string;
}

interface AnnotationOverlayProps {
  imageSrc: string;
  annotations: Annotation[];
  isScanning: boolean;
  /** Optional callback when an annotation is clicked */
  onAnnotationClick?: (annotation: Annotation) => void;
}

/* ------------------------------------------------------------------ */
/*  Colour helpers                                                     */
/* ------------------------------------------------------------------ */

const typeStyles: Record<Annotation["type"], { border: string; bg: string; text: string; ring: string; dot: string }> = {
  key_term:   { border: "border-emerald-500", bg: "bg-emerald-500/10", text: "text-emerald-400", ring: "ring-emerald-400/30", dot: "bg-emerald-500" },
  error:      { border: "border-rose-500",    bg: "bg-rose-500/10",    text: "text-rose-400",    ring: "ring-rose-400/30",    dot: "bg-rose-500" },
  diagram:    { border: "border-blue-500",    bg: "bg-blue-500/10",    text: "text-blue-400",    ring: "ring-blue-400/30",    dot: "bg-blue-500" },
  partial:    { border: "border-amber-500",   bg: "bg-amber-500/10",   text: "text-amber-400",   ring: "ring-amber-400/30",   dot: "bg-amber-500" },
  correction: { border: "border-purple-500",  bg: "bg-purple-500/10",  text: "text-purple-400",  ring: "ring-purple-400/30",  dot: "bg-purple-500" },
  penalty:    { border: "border-rose-500",    bg: "bg-rose-500/10",    text: "text-rose-400",    ring: "ring-rose-400/30",    dot: "bg-rose-500" },
};

const typeLabels: Record<Annotation["type"], string> = {
  key_term: "Key Term",
  error: "Error",
  diagram: "Diagram",
  partial: "Partial Credit",
  correction: "Correction",
  penalty: "Deduction",
};

/**
 * Per-annotation review-state overrides.
 * When an annotation is being audited by Pass 2, these styles take precedence.
 */
const reviewStyles: Record<
  NonNullable<Annotation["reviewState"]>,
  { border: string; bg: string; ring: string; icon: React.ReactNode; label: string } | null
> = {
  pending: null, // use type-based styles
  reviewing: {
    border: "border-yellow-400",
    bg: "bg-yellow-400/15",
    ring: "ring-yellow-400/40",
    icon: <RefreshCw className="h-3 w-3 text-yellow-400 animate-spin" />,
    label: "Reviewing…",
  },
  confirmed: {
    border: "border-emerald-400",
    bg: "bg-emerald-400/15",
    ring: "ring-emerald-400/40",
    icon: <ShieldCheck className="h-3 w-3 text-emerald-400" />,
    label: "Confirmed",
  },
  adjusted: {
    border: "border-purple-400",
    bg: "bg-purple-400/15",
    ring: "ring-purple-400/40",
    icon: <ShieldAlert className="h-3 w-3 text-purple-400" />,
    label: "Adjusted",
  },
  rejected: {
    border: "border-rose-400",
    bg: "bg-rose-400/15",
    ring: "ring-rose-400/40",
    icon: <XCircle className="h-3 w-3 text-rose-400" />,
    label: "Rejected",
  },
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const AnnotationOverlay: React.FC<AnnotationOverlayProps> = ({
  imageSrc,
  annotations,
  isScanning,
  onAnnotationClick,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [showAnnotations, setShowAnnotations] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  /* ---------- zoom / pan ---------- */
  const handleZoomIn = useCallback(() => setZoom((z) => Math.min(z + 0.25, 3)), []);
  const handleZoomOut = useCallback(() => {
    setZoom((z) => {
      const next = Math.max(z - 0.25, 1);
      if (next === 1) setPan({ x: 0, y: 0 });
      return next;
    });
  }, []);

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        if (e.deltaY < 0) handleZoomIn();
        else handleZoomOut();
      }
    },
    [handleZoomIn, handleZoomOut],
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      setIsPanning(true);
      setPanStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    },
    [pan],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!isPanning) return;
      setPan({ x: e.clientX - panStart.x, y: e.clientY - panStart.y });
    },
    [isPanning, panStart],
  );

  const handlePointerUp = useCallback(() => setIsPanning(false), []);

  /* reset pan when zoom resets */
  useEffect(() => {
    if (zoom === 1) setPan({ x: 0, y: 0 });
  }, [zoom]);

  /* ---------- annotation counts ---------- */
  const counts = annotations.reduce(
    (acc, a) => {
      acc[a.type] = (acc[a.type] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );

  /* ---------- render ---------- */
  return (
    <div className="relative flex h-full min-h-0 w-full select-none flex-col">
      {/* ─── Toolbar ─── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-black/30 backdrop-blur-xl z-30 shrink-0">
        {/* Left: Legend chips */}
        <div className="flex items-center gap-2 flex-wrap">
          {(Object.keys(typeStyles) as Annotation["type"][]).map((t) =>
            (counts[t] ?? 0) > 0 ? (
              <span
                key={t}
                className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-semibold tracking-wide ${typeStyles[t].border} ${typeStyles[t].bg} ${typeStyles[t].text}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${typeStyles[t].dot}`} />
                {typeLabels[t]}: {counts[t]}
              </span>
            ) : null,
          )}
          {annotations.length === 0 && !isScanning && (
            <span className="text-[10px] text-white/30">No annotations</span>
          )}
        </div>

        {/* Right: Controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowAnnotations((v) => !v)}
            className="p-1.5 rounded-md hover:bg-white/10 transition-colors text-white/40 hover:text-white/70"
            title={showAnnotations ? "Hide annotations" : "Show annotations"}
          >
            {showAnnotations ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={handleZoomOut}
            disabled={zoom <= 1}
            className="p-1.5 rounded-md hover:bg-white/10 transition-colors text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Zoom out"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <span className="text-[10px] text-white/30 font-mono w-10 text-center">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={handleZoomIn}
            disabled={zoom >= 3}
            className="p-1.5 rounded-md hover:bg-white/10 transition-colors text-white/40 hover:text-white/70 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Zoom in"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <div className="h-4 w-px bg-white/10 mx-1" />
          <span className="text-[9px] text-white/20 flex items-center gap-1">
            <Layers className="h-3 w-3" /> {annotations.length}
          </span>
        </div>
      </div>

      {/* ─── Canvas area ─── */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-0 overflow-auto cursor-grab active:cursor-grabbing bg-black/10"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <div
          className="relative min-h-full w-full transition-transform duration-150 origin-center"
          style={{
            transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
          }}
        >
          {/* The scanned document image */}
          <img
            src={imageSrc}
            alt="Student Script"
            className="block w-full h-auto max-w-none pointer-events-none"
            draggable={false}
          />

          {/* ─── Real-time Laser Scan Line ─── */}
          <AnimatePresence>
            {isScanning && (
              <motion.div
                initial={{ top: "0%" }}
                animate={{ top: "100%" }}
                exit={{ opacity: 0 }}
                transition={{ duration: 3.5, repeat: Infinity, ease: "linear" }}
                className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_20px_rgba(34,211,238,0.8)] z-10 pointer-events-none"
              />
            )}
          </AnimatePresence>

          {/* ─── Annotation Boxes ─── */}
          <div className="absolute inset-0 pointer-events-none">
            <AnimatePresence>
              {showAnnotations &&
                !isScanning &&
                annotations.map((note, idx) => {
                  const baseS = typeStyles[note.type] || typeStyles.key_term;
                  const rs = note.reviewState && note.reviewState !== "pending"
                    ? reviewStyles[note.reviewState]
                    : null;
                  const isHovered = hoveredId === note.id;
                  const isReviewing = note.reviewState === "reviewing";

                  // Use review-state styles when available, otherwise type-based
                  const borderCls = rs ? rs.border : baseS.border;
                  const bgCls = rs ? rs.bg : baseS.bg;
                  const ringCls = rs ? rs.ring : baseS.ring;

                  return (
                    <motion.div
                      key={note.id}
                      initial={{ opacity: 0, scale: 0.85 }}
                      animate={{
                        opacity: 1,
                        scale: isReviewing ? [1, 1.02, 1] : 1,
                        borderColor: isReviewing ? ["rgba(250,204,21,0.6)", "rgba(250,204,21,1)", "rgba(250,204,21,0.6)"] : undefined,
                      }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      transition={isReviewing
                        ? { duration: 1.2, repeat: Infinity, ease: "easeInOut" }
                        : { delay: idx * 0.06, type: "spring", stiffness: 300, damping: 24 }
                      }
                      className={`absolute border-2 rounded-sm pointer-events-auto cursor-help transition-all duration-300 ${borderCls} ${bgCls} ${isHovered ? `z-30 ring-4 ${ringCls}` : "z-20"} ${isReviewing ? "shadow-[0_0_12px_rgba(250,204,21,0.4)]" : ""}`}
                      style={{
                        left: `${note.x}%`,
                        top: `${note.y}%`,
                        width: `${note.width}%`,
                        height: `${note.height}%`,
                      }}
                      onMouseEnter={() => setHoveredId(note.id)}
                      onMouseLeave={() => setHoveredId(null)}
                      onClick={() => onAnnotationClick?.(note)}
                    >
                      {/* ── Tag badge with review state icon ── */}
                      <div
                        className={`absolute -top-5 left-0 text-[9px] font-bold px-1.5 py-0.5 rounded tracking-wider whitespace-nowrap backdrop-blur-sm flex items-center gap-1 ${bgCls} ${baseS.text} border ${borderCls}`}
                      >
                        {rs?.icon}
                        {note.label}
                        {note.points !== undefined && (
                          <span className="ml-1 opacity-80">
                            ({note.points > 0 ? "+" : ""}
                            {note.points})
                          </span>
                        )}
                        {rs && (
                          <span className="ml-1 text-[8px] opacity-70 uppercase">
                            {rs.label}
                          </span>
                        )}
                      </div>

                      {/* Inline reason strip on the box itself */}
                      {note.description && (
                        <div
                          className={`absolute left-0 right-0 bottom-0 px-1.5 py-0.5 text-[9px] leading-tight border-t truncate ${note.points !== undefined && note.points < 0
                            ? "bg-rose-500/25 text-rose-100 border-rose-400/40"
                            : "bg-emerald-500/20 text-emerald-100 border-emerald-400/30"}`}
                          title={note.description}
                        >
                          {note.description}
                        </div>
                      )}

                      {/* ── Tooltip on hover ── */}
                      <AnimatePresence>
                        {isHovered && (
                          <motion.div
                            initial={{ opacity: 0, y: 8, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: 4 }}
                            transition={{ duration: 0.15 }}
                            className="absolute top-full mt-2 left-0 w-64 p-3 bg-slate-900/95 backdrop-blur-xl border border-white/20 rounded-lg shadow-2xl z-40"
                          >
                            <div className="flex items-start gap-2">
                              {note.type === "error" ? (
                                <XCircle className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                              ) : (
                                <Info className="w-4 h-4 text-cyan-400 mt-0.5 shrink-0" />
                              )}
                              <div>
                                <h4 className="text-xs font-bold text-white mb-1">
                                  {note.label}
                                </h4>
                                <p className="text-[11px] text-slate-300 leading-relaxed">
                                  {note.description}
                                </p>
                                {note.points !== undefined && (
                                  <p
                                    className={`mt-1.5 text-[10px] font-semibold ${note.points >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                                  >
                                    Mark impact: {note.points > 0 ? "+" : ""}
                                    {note.points}
                                  </p>
                                )}
                                {note.verdictNote && (
                                  <p className="mt-1 text-[10px] text-white/50 italic">
                                    Audit: {note.verdictNote}
                                  </p>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  );
                })}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ─── Bottom status bar ─── */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-white/10 bg-black/30 backdrop-blur-xl z-30 shrink-0">
        <div className="flex items-center gap-2">
          <div
            className={`h-2 w-2 rounded-full ${isScanning ? "bg-cyan-500 animate-pulse" : annotations.length > 0 ? "bg-emerald-500" : "bg-white/20"}`}
          />
          <span className="text-[10px] text-white/50 font-medium tracking-wide uppercase">
            {isScanning
              ? "AI Analyzing Script…"
              : annotations.length > 0
                ? `Analysis Complete · ${annotations.length} region${annotations.length !== 1 ? "s" : ""} detected`
                : "Upload a script to begin"}
          </span>
        </div>
        {!isScanning && annotations.length > 0 && (
          <span className="text-[10px] text-white/30">
            Ctrl+Scroll to zoom · Drag to pan
          </span>
        )}
      </div>
    </div>
  );
};

export default AnnotationOverlay;
