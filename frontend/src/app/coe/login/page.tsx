"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Shield, User, Mail, LockKeyhole, CalendarDays } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCoeAuth } from "@/lib/coe-auth";

export default function CoeLoginPage() {
  const router = useRouter();
  const { member, loading, login } = useCoeAuth();
  const [fullName, setFullName] = useState("");
  const [dob, setDob] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && member) {
      router.replace("/coe/dashboard");
    }
  }, [loading, member, router]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const result = await login({
      full_name: fullName,
      dob,
      email,
      password,
    });

    setSubmitting(false);
    if (!result.ok) {
      setError(result.message || "Login failed");
      return;
    }

    router.push("/coe/dashboard");
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.18),_transparent_35%),linear-gradient(180deg,#020617_0%,#07111f_50%,#030712_100%)] text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-7xl items-center px-6 py-10">
        <div className="grid w-full gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="flex flex-col justify-between rounded-[2rem] border border-cyan-400/15 bg-white/5 p-8 shadow-2xl shadow-cyan-950/20 backdrop-blur-2xl">
            <div className="space-y-6">
              <div className="inline-flex items-center gap-3 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-200">
                <Shield className="h-4 w-4" /> AuraGrade COE Portal
              </div>
              <div className="space-y-4">
                <h1 className="max-w-xl text-5xl font-semibold tracking-tight text-white md:text-6xl">
                  Exclusive access for COE office members.
                </h1>
                <p className="max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
                  Authenticate with your official name, date of birth, college email, and password. Manage evaluator and HOD profiles, define subject ownership, and keep COE records aligned with AuraGrade.
                </p>
              </div>
            </div>
            <div className="mt-10 text-sm text-slate-400">
              Need the initial COE office account loaded? Run COE migration and seed SQL in Supabase.
            </div>
          </div>

          <Card className="border-white/10 bg-slate-950/80 text-white shadow-2xl shadow-black/40 backdrop-blur-xl">
            <CardHeader className="space-y-2 border-b border-white/10 pb-6">
              <CardTitle className="text-2xl">COE Sign In</CardTitle>
              <p className="text-sm text-slate-400">Use your office credentials to open the administrative portal.</p>
            </CardHeader>
            <CardContent className="space-y-4 p-6">
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-400">Full Name</label>
                  <div className="relative">
                    <User className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" />
                    <Input value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Enter official name" className="border-white/10 bg-white/5 pl-10 text-white placeholder:text-slate-500" required />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-400">Date of Birth</label>
                  <div className="relative">
                    <CalendarDays className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" />
                    <Input type="date" value={dob} onChange={(event) => setDob(event.target.value)} className="border-white/10 bg-white/5 pl-10 text-white" required />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-400">College Email</label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" />
                    <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@college.edu.in" className="border-white/10 bg-white/5 pl-10 text-white placeholder:text-slate-500" required />
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-xs uppercase tracking-[0.2em] text-slate-400">Password</label>
                  <div className="relative">
                    <LockKeyhole className="absolute left-3 top-3.5 h-4 w-4 text-slate-500" />
                    <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Office password" className="border-white/10 bg-white/5 pl-10 text-white placeholder:text-slate-500" required />
                  </div>
                </div>

                {error && <div className="rounded-xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}

                <Button type="submit" disabled={submitting} className="w-full bg-cyan-500 text-slate-950 hover:bg-cyan-400">
                  {submitting ? "Signing in..." : "Enter COE Portal"}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </form>

              <div className="pt-4 text-center text-xs text-slate-500">
                Back to AuraGrade? <Link href="/" className="text-cyan-300 hover:text-cyan-200">Return home</Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
