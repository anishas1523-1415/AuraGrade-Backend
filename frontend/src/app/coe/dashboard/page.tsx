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
import { Edit3, LogOut, Plus, Save, Trash2 } from "lucide-react";

type StaffProfile = {
  id: string;
  full_name: string;
  email: string;
  role: string;
  subjects: string[];
  departments: string[];
  years: string[];
  is_active: boolean;
};

type Summary = {
  office_members: number;
  active_office_members: number;
  staff_profiles: number;
  active_staff_profiles: number;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const splitValues = (value: string) => value.split(/[\n,;]/).map(v => v.trim()).filter(Boolean);
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
  const [busy, setBusy] = useState(false);
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
    if (!loading && !member) router.replace("/coe/login");
  }, [loading, member, router]);

  const loadProfiles = async () => {
    if (!member) return;
    setBusy(true);
    setError(null);
    try {
      const [summaryRes, profilesRes] = await Promise.all([
        authFetch(`${API_URL}/api/coe/summary`),
        authFetch(`${API_URL}/api/coe/staff-profiles`),
      ]);

      const summaryData = await summaryRes.json().catch(() => ({}));
      const profilesData = await profilesRes.json().catch(() => ({}));
      if (!summaryRes.ok) throw new Error(extractApiErrorMessage(summaryData, "Failed to load summary"));
      if (!profilesRes.ok) throw new Error(extractApiErrorMessage(profilesData, "Failed to load profiles"));
      setSummary((summaryData.data || null) as Summary | null);
      setProfiles((profilesData.data || []) as StaffProfile[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profiles");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (member) void loadProfiles();
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

    setBusy(true);
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
        ? await authFetch(`${API_URL}/api/coe/staff-profiles/${editingId}`, { method: "PUT", body: JSON.stringify(payload) })
        : await authFetch(`${API_URL}/api/coe/staff-profiles`, { method: "POST", body: JSON.stringify(payload) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(extractApiErrorMessage(data, "Failed to save"));
      resetForm();
      await loadProfiles();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const editProfile = (profile: StaffProfile) => {
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

  const deleteProfile = async (id: string) => {
    if (!window.confirm("Delete this profile?")) return;
    setBusy(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/api/coe/staff-profiles/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(extractApiErrorMessage(data, "Delete failed"));
      await loadProfiles();
      if (editingId === id) resetForm();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  if (loading || busy) return <div className="min-h-screen bg-slate-950 text-white flex items-center justify-center">Loading COE dashboard...</div>;
  if (!member) return null;

  return (
    <div className="min-h-screen bg-slate-950 p-6 text-white">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-white/5 p-4">
          <div>
            <h1 className="text-2xl font-semibold">AuraGrade COE Dashboard</h1>
            <p className="text-sm text-white/60">Manage evaluator and HOD accounts</p>
          </div>
          <div className="flex items-center gap-3">
            <Badge className="bg-white/10 text-white">{member.full_name}</Badge>
            <Button variant="outline" onClick={logout} className="border-white/20 bg-white/5">
              <LogOut className="mr-1 h-4 w-4" /> Logout
            </Button>
          </div>
        </header>

        {error && <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

        <div className="grid gap-4 md:grid-cols-4">
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-white/50">Office Members</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.office_members ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-white/50">Active Office Members</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.active_office_members ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-white/50">Staff Profiles</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.staff_profiles ?? 0}</div>
            </CardContent>
          </Card>
          <Card className="border-white/10 bg-white/5">
            <CardContent className="p-5">
              <div className="text-xs uppercase tracking-[0.2em] text-white/50">Active Staff Profiles</div>
              <div className="mt-2 text-3xl font-semibold">{summary?.active_staff_profiles ?? 0}</div>
            </CardContent>
          </Card>
        </div>

        <div className="grid items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="h-[520px] border-white/10 bg-white/5">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-white">
                <Plus className="h-4 w-4" /> {editingId ? "Edit" : "Create"} Staff Profile
              </CardTitle>
            </CardHeader>
            <CardContent className="h-[calc(520px-84px)] space-y-3 overflow-y-auto">
              <Input placeholder="Full name" value={fullName} onChange={(e) => setFullName(e.target.value)} className="border-white/10 bg-white/5 text-white" />
              <Input placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} className="border-white/10 bg-white/5 text-white" />
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger className="border-white/10 bg-white/5 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-white/10 bg-slate-900 text-white">
                  <SelectItem value="EVALUATOR">Evaluator</SelectItem>
                  <SelectItem value="HOD_AUDITOR">HOD</SelectItem>
                </SelectContent>
              </Select>
              <Textarea placeholder="Subjects (comma separated)" value={subjects} onChange={(e) => setSubjects(e.target.value)} className="border-white/10 bg-white/5 text-white" />
              <Textarea placeholder="Departments (comma separated)" value={departments} onChange={(e) => setDepartments(e.target.value)} className="border-white/10 bg-white/5 text-white" />
              <Textarea placeholder="Years (comma separated)" value={years} onChange={(e) => setYears(e.target.value)} className="border-white/10 bg-white/5 text-white" />
              <Input type="password" placeholder={editingId ? "Password (leave blank to keep)" : "Password"} value={password} onChange={(e) => setPassword(e.target.value)} className="border-white/10 bg-white/5 text-white" />

              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> Active
              </label>

              <div className="flex gap-2">
                <Button onClick={saveProfile} disabled={busy} className="bg-cyan-400 text-black hover:bg-cyan-300">
                  <Save className="mr-1 h-4 w-4" /> {editingId ? "Update" : "Create"}
                </Button>
                <Button variant="outline" onClick={resetForm} className="border-white/20 bg-white/5">Reset</Button>
              </div>
            </CardContent>
          </Card>

          <Card className="min-h-[520px] border-white/10 bg-white/5">
            <CardHeader>
              <CardTitle className="text-white">Staff Profiles ({profiles.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <Table className="min-w-[760px]">
                <TableHeader>
                  <TableRow className="border-white/10">
                    <TableHead className="text-white/70">Name</TableHead>
                    <TableHead className="text-white/70">Role</TableHead>
                    <TableHead className="text-white/70">Subjects</TableHead>
                    <TableHead className="text-white/70">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {profiles.length === 0 ? (
                    <TableRow className="border-white/10">
                      <TableCell className="text-white/60" colSpan={4}>No profiles yet</TableCell>
                    </TableRow>
                  ) : (
                    profiles.map((p) => (
                      <TableRow key={p.id} className="border-white/10">
                        <TableCell>
                          {p.full_name}
                          <div className="text-xs text-white/50">{p.email}</div>
                        </TableCell>
                        <TableCell>{p.role}</TableCell>
                        <TableCell className="max-w-[220px] truncate">{joinValues(p.subjects)}</TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={() => editProfile(p)} className="border-white/20 bg-white/5">
                              <Edit3 className="h-3 w-3" />
                            </Button>
                            <Button size="sm" variant="outline" onClick={() => deleteProfile(p.id)} className="border-rose-500/40 bg-rose-500/10 text-rose-200">
                              <Trash2 className="h-3 w-3" />
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
