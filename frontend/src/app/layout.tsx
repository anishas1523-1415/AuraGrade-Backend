import type { Metadata, Viewport } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Toaster } from "react-hot-toast";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";

export const metadata: Metadata = {
  title: {
    default: "AuraGrade AI Engine",
    template: "%s | AuraGrade",
  },
  description:
    "Enterprise AI-powered exam grading platform with digital seals, audit trails, and role-based access control.",
  keywords: ["AI grading", "exam evaluation", "education technology", "AuraGrade"],
  authors: [{ name: "AuraGrade Team" }],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0f172a",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <ErrorBoundary>
          <AuthProvider>{children}</AuthProvider>
        </ErrorBoundary>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#0f172a",
              color: "#e2e8f0",
              border: "1px solid rgba(37,99,235,0.4)",
              fontWeight: 600,
            },
            success: {
              iconTheme: { primary: "#2563eb", secondary: "#e2e8f0" },
              duration: 5000,
            },
            error: {
              iconTheme: { primary: "#ef4444", secondary: "#e2e8f0" },
              duration: 6000,
            },
          }}
        />
      </body>
    </html>
  );
}
