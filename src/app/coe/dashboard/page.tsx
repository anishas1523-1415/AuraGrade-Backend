"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useCoeAuth } from "@/lib/coe-auth";
import { Edit3, LogOut, Plus, Save, Shield, Trash2, Users } from "lucide-react";

type StaffProfile = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  subjects: string[];
  departments: string[];
  years: string[];
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
};

type Summary = {
  office_members: number;
  active_office_members: number;
  staff_profiles: number;
  active_staff_profiles: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const splitValues = (value: string) =>
  value
    .split(/[,\n;]/)
    .map((item) => item.trim())
    .filter(Boolean);

const joinValues = (items: string[] | undefined) => (items || []).join(", ");

const extractApiErrorMessage = (payload: any, fallback: string) => {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (typeof payload.message === "string") return payload.message;

  if (Array.isArray(payload.detail)) {
    const detailMessage = payload.detail
      .map((item: any) => {
        if (typeof item === "string") return item;
        if (item && typeof item.msg === "string") return item.msg;
        return null;
      })
      .filter(Boolean)
      .join("; ");
    return detailMessage || fallback;
  }

  if (payload.detail && typeof payload.detail === "object") {
    if (typeof payload.detail.message === "string") return payload.detail.message;
    return fallback;
  }

  return fallback;
};

export default function CoeDashboardPage() {
  const router = useRouter();
  const { member, loading, logout, authFetch } = useCoeAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [profiles, setProfiles] = useState<StaffProfile[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("EVALUATOR");
  const [subjects, setSubjects] = useState("");
  const [departments, setDepartments] = useState("");
  const [years, setYears] = useState("");
  const [password, setPassword] = useState("");
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (!loading && !member) {
      router.replace("/coe/login");
    }
  }, [loading, member, router]);

  const loadData = async () => {
    if (!member) return;
    setPageLoading(true);
    setError(null);
    try {
      const [summaryRes, profilesRes] = await Promise.all([
        authFetch(`${API_URL}/api/coe/summary`),
        authFetch(`${API_URL}/api/coe/staff-profiles`),
      ]);

      if (!summaryRes.ok) {
        const payload = await summaryRes.json().catch(() => ({}));
        throw new Error(extractApiErrorMessage(payload, "Failed to load summary"));
      }
      if (!profilesRes.ok) {
        const payload = await profilesRes.json().catch(() => ({}));
        throw new Error(extractApiErrorMessage(payload, "Failed to load staff profiles"));
      }

      const summaryData = await summaryRes.json();
      const profilesData = await profilesRes.json();
      setSummary((summaryData.data || null) as Summary | null);
      setProfiles((profilesData.data || []) as StaffProfile[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load COE dashboard");
    } finally {
      setPageLoading(false);
    }
  };

  useEffect(() => {
    if (member) {
      void loadData();
    }
  }, [member]);

  const resetForm = () => {
    setEditingId(null);
    setFullName("");
    setEmail("");
    setRole("EVALUATOR");
    setSubjects("");
    setDepartments("");
    setYears("");
    setPassword("");
    setIsActive(true);
  };

  const beginEdit = (profile: StaffProfile) => {
    setEditingId(profile.id);
    setFullName(profile.full_name);
    setEmail(profile.email);
    setRole(profile.role);
    setSubjects(joinValues(profile.subjects));
    setDepartments(joinValues(profile.departments));
    setYears(joinValues(profile.years));
    setPassword("");
    setIsActive(profile.is_active);
  };

  const saveProfile = async () => {
    const trimmedPassword = password.trim();
    if (!editingId && trimmedPassword.length < 8) {
      setError("Password must be at least 8 characters for new profiles.");
      return;
    }
    if (editingId && trimmedPassword.length > 0 && trimmedPassword.length < 8) {
      setError("Password must be at least 8 characters when updating it.");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const payload = {
        full_name: fullName,
        email,
        role,
        subjects: splitValues(subjects),
        departments: splitValues(departments),
        years: splitValues(years),
        password: trimmedPassword || undefined,
        is_active: isActive,
      };

      const res = editingId
        ? await authFetch(`${API_URL}/api/coe/staff-profiles/${editingId}`, {
            method: "PUT",
            body: JSON.stringify(payload),
          })
        : await authFetch(`${API_URL}/api/coe/staff-profiles`, {
            method: "POST",
            body: JSON.stringify(payload),
          });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(extractApiErrorMessage(data, "Unable to save profile"));
      }

      await loadData();
      resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save profile");
    } finally {
      setSaving(false);
    }
  };

  const deleteProfile = async (profileId: string) => {
    const confirmed = window.confirm("Delete this staff profile? This cannot be undone.");
    if (!confirmed) return;

    setSaving(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/api/coe/staff-profiles/${profileId}`, {
        method: "DELETE",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(extractApiErrorMessage(data, "Unable to delete profile"));
      }
      await loadData();
      if (editingId === profileId) {
        resetForm();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete profile");
    } finally {
      setSaving(false);
    }
  };

  if (loading || pageLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
        Loading COE portal...
      </div>
    );
  }

  if (!member) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,197,94,0.14),_transparent_30%),linear-gradient(180deg,#020617_0%,#09111f_45%,#030712_100%)] text-slate-100">
      <div className="mx-auto max-w-7xl px-6 py-6">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-[1.75rem] border border-emerald-400/15 bg-white/5 px-6 py-4 backdrop-blur-2xl">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-emerald-200">
              <Shield className="h-3.5 w-3.5" /> COE Control Center
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight">AuraGrade COE App</h1>
            <p className="text-sm text-slate-400">Manage evaluators, HODs, subject allocations, and office credentials.</p>
          </div>

          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-right">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Signed in as</div>
              <div className="text-sm font-semibold text-white">{member.full_name}</div>
              <div className="text-xs text-slate-400">{member.email}</div>
            </div>
            <Button variant="outline" onClick={logout} className="border-white/10 bg-white/5 text-white hover:bg-white/10">
              <LogOut className="mr-2 h-4 w-4" /> Logout
            </Button>
          </div>
        </header>

        {error && (
          <div className="mb-5 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        <div className="mb-6 grid gap-4 md:grid-cols-4">
          <Card className="border-white/10 bg-slate-950/70 text-white backdrop-blur-xl">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Office Members</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.office_members ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-slate-950/70 text-white backdrop-blur-xl">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Active Office Members</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.active_office_members ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-slate-950/70 text-white backdrop-blur-xl">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Staff Profiles</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.staff_profiles ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-slate-950/70 text-white backdrop-blur-xl">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Active Staff Profiles</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.active_staff_profiles ?? 0}</div>
            </CardContent>
          </Card>
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="h-[520px] border-white/10 bg-slate-950/80 text-white backdrop-blur-xl">
            <CardHeader className="border-b border-white/10">
              <CardTitle className="flex items-center gap-2 text-lg sm:text-xl">
                <Plus className="h-5 w-5 text-emerald-300" /> {editingId ? "Edit Staff Profile" : "Create Staff Profile"}
              </CardTitle>
            </CardHeader>
            <CardContent className="h-[calc(520px-84px)] space-y-4 overflow-y-auto p-5 sm:p-6">
              <div className="grid gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Full Name</label>
                  <Input value={fullName} onChange={(event) => setFullName(event.target.value)} className="h-10 border-white/10 bg-white/5 text-white" placeholder="Evaluator or HOD name" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Email</label>
                  <Input value={email} onChange={(event) => setEmail(event.target.value)} className="h-10 border-white/10 bg-white/5 text-white" placeholder="name@college.edu.in" />
                </div>
              </div>

              <div className="grid gap-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Role</label>
                  <Select value={role} onValueChange={setRole}>
                    <SelectTrigger className="h-10 border-white/10 bg-white/5 text-white">
                      <SelectValue placeholder="Select role" />
                    </SelectTrigger>
                    <SelectContent className="border-white/10 bg-slate-950 text-white">
                      <SelectItem value="EVALUATOR">Evaluator</SelectItem>
                      <SelectItem value="HOD_AUDITOR">HOD</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Password {editingId ? "(leave blank to keep current)" : ""}</label>
                  <Input value={password} onChange={(event) => setPassword(event.target.value)} type="password" className="h-10 border-white/10 bg-white/5 text-white" placeholder="Temporary or permanent password" />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">Subjects</label>
                <Textarea value={subjects} onChange={(event) => setSubjects(event.target.value)} className="min-h-[76px] border-white/10 bg-white/5 text-white" placeholder="Comma-separated subjects. Example: AI, DBMS, Python" />
              </div>

              <div className="grid gap-3">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Departments</label>
                  <Textarea value={departments} onChange={(event) => setDepartments(event.target.value)} className="min-h-[76px] border-white/10 bg-white/5 text-white" placeholder="Comma-separated departments" />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-300">Years</label>
                  <Textarea value={years} onChange={(event) => setYears(event.target.value)} className="min-h-[76px] border-white/10 bg-white/5 text-white" placeholder="Comma-separated years, e.g. I, II, III" />
                </div>
              </div>

              <div className="flex items-center gap-3 text-sm text-slate-300">
                <input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} className="h-4 w-4 rounded border-white/20 bg-white/10" />
                <span>Profile is active</span>
              </div>

              <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:flex-wrap">
                <Button onClick={saveProfile} disabled={saving} className="w-full bg-emerald-500 text-slate-950 hover:bg-emerald-400 sm:w-auto">
                  <Save className="mr-2 h-4 w-4" /> {saving ? "Saving..." : editingId ? "Update Profile" : "Create Profile"}
                </Button>
                <Button variant="outline" onClick={resetForm} className="w-full border-white/10 bg-white/5 text-white hover:bg-white/10 sm:w-auto">
                  Reset
                </Button>
              </div>
              <p className="hidden text-xs text-slate-500 sm:block">Multiple subjects, departments, and years can be stored together for each evaluator or HOD.</p>
            </CardContent>
          </Card>

          <Card className="min-h-[520px] border-white/10 bg-slate-950/80 text-white backdrop-blur-xl">
            <CardHeader className="flex flex-row items-center justify-between border-b border-white/10">
              <CardTitle className="flex items-center gap-2 text-xl">
                <Users className="h-5 w-5 text-cyan-300" /> Managed Profiles
              </CardTitle>
              <Badge className="bg-cyan-500/15 text-cyan-200">{profiles.length} records</Badge>
            </CardHeader>
            <CardContent className="p-0">
              <Table className="min-w-[980px] table-auto">
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-white/0">
                    <TableHead className="min-w-[220px] text-slate-400">Name</TableHead>
                    <TableHead className="min-w-[120px] text-slate-400">Role</TableHead>
                    <TableHead className="min-w-[220px] text-slate-400">Subjects</TableHead>
                    <TableHead className="min-w-[180px] text-slate-400">Departments</TableHead>
                    <TableHead className="min-w-[110px] text-slate-400">Years</TableHead>
                    <TableHead className="min-w-[110px] text-slate-400">Status</TableHead>
                    <TableHead className="min-w-[110px] text-slate-400">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {profiles.length === 0 ? (
                    <TableRow className="border-white/10">
                      <TableCell colSpan={7} className="py-10 text-center text-slate-500">
                        No staff profiles created yet.
                      </TableCell>
                    </TableRow>
                  ) : (
                    profiles.map((profile) => (
                      <TableRow key={profile.id} className="border-white/10 hover:bg-white/5">
                        <TableCell className="align-top whitespace-normal">
                          <div className="font-medium text-white">{profile.full_name}</div>
                          <div className="text-xs text-slate-500">{profile.email}</div>
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge className="bg-white/10 text-white">{profile.role === "HOD_AUDITOR" ? "HOD" : profile.role}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[220px] align-top whitespace-normal break-words text-slate-300">{joinValues(profile.subjects)}</TableCell>
                        <TableCell className="max-w-[180px] align-top whitespace-normal break-words text-slate-300">{joinValues(profile.departments)}</TableCell>
                        <TableCell className="max-w-[140px] align-top whitespace-normal break-words text-slate-300">{joinValues(profile.years)}</TableCell>
                        <TableCell className="align-top">
                          <Badge className={profile.is_active ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300"}>
                            {profile.is_active ? "Active" : "Disabled"}
                          </Badge>
                        </TableCell>
                        <TableCell className="align-top whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <Button variant="outline" size="sm" onClick={() => beginEdit(profile)} className="border-white/10 bg-white/5 text-white hover:bg-white/10">
                              <Edit3 className="h-4 w-4" />
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => deleteProfile(profile.id)} className="border-rose-500/20 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
