import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { Toaster } from "react-hot-toast";

export const metadata: Metadata = {
  title: "AuraGrade AI Engine",
  description: "AI-powered exam grading dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        <AuthProvider>{children}</AuthProvider>
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
