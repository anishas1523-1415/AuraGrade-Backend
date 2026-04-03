/**
 * Reusable loading skeleton components with shimmer animation.
 * Use these instead of blank screens while data loads.
 */

import React from "react";

const shimmerStyle: React.CSSProperties = {
  background:
    "linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%)",
  backgroundSize: "200% 100%",
  animation: "shimmer 1.5s ease-in-out infinite",
  borderRadius: "0.5rem",
};

export function SkeletonCard({ count = 3 }: { count?: number }) {
  return (
    <>
      <style>{`@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }`}</style>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          style={{
            padding: "1.5rem",
            borderRadius: "0.75rem",
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.06)",
            marginBottom: "1rem",
          }}
        >
          <div style={{ ...shimmerStyle, height: "1.25rem", width: "60%", marginBottom: "1rem" }} />
          <div style={{ ...shimmerStyle, height: "0.875rem", width: "90%", marginBottom: "0.5rem" }} />
          <div style={{ ...shimmerStyle, height: "0.875rem", width: "75%" }} />
        </div>
      ))}
    </>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <>
      <style>{`@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }`}</style>
      <div style={{ borderRadius: "0.75rem", overflow: "hidden", border: "1px solid rgba(255,255,255,0.06)" }}>
        {/* Header */}
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: "1rem", padding: "1rem", background: "rgba(255,255,255,0.03)" }}>
          {Array.from({ length: cols }).map((_, i) => (
            <div key={i} style={{ ...shimmerStyle, height: "1rem" }} />
          ))}
        </div>
        {/* Rows */}
        {Array.from({ length: rows }).map((_, ri) => (
          <div key={ri} style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: "1rem", padding: "1rem", borderTop: "1px solid rgba(255,255,255,0.04)" }}>
            {Array.from({ length: cols }).map((_, ci) => (
              <div key={ci} style={{ ...shimmerStyle, height: "0.875rem" }} />
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <>
      <style>{`@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }`}</style>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          style={{
            ...shimmerStyle,
            height: "0.875rem",
            width: `${70 + Math.random() * 30}%`,
            marginBottom: "0.5rem",
          }}
        />
      ))}
    </>
  );
}
