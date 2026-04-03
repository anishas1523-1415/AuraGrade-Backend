"use client";

import dynamic from "next/dynamic";
import type { ComponentType } from "react";

function ProctorLoading() {
  return (
    <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center px-6">
      <div className="max-w-sm rounded-2xl border border-white/10 bg-white/5 px-6 py-8 text-center backdrop-blur-xl">
        <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
        <p className="text-sm font-semibold">Loading proctor scanner...</p>
        <p className="mt-2 text-xs text-white/40">Preparing camera and secure capture tools.</p>
      </div>
    </div>
  );
}

/* SSR-unsafe (camera + vibrate APIs) → client-only dynamic import */
const MobileScanner = dynamic(
  () => import("@/components/MobileScanner"),
  { ssr: false, loading: () => <ProctorLoading /> },
);

export default function ProctorPage() {
  return <MobileScanner />;
}
