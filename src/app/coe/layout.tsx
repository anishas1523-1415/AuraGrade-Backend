import React from "react";
import { CoeAuthProvider } from "@/lib/coe-auth";

export default function CoeLayout({ children }: { children: React.ReactNode }) {
  return <CoeAuthProvider>{children}</CoeAuthProvider>;
}
