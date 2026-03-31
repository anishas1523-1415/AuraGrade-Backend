"use client";

import dynamic from "next/dynamic";

/* SSR-unsafe (camera + vibrate APIs) → client-only dynamic import */
const MobileScanner = dynamic(
  () => import("@/components/MobileScanner"),
  { ssr: false },
);

export default function ProctorPage() {
  return <MobileScanner />;
}
