export interface AuditNotes {
  verdict: "Upheld" | "Adjusted Up" | "Adjusted Down";
  recommendation: string;
  rubric_breakdown: Record<string, { original: number; audited: number; note: string }>;
  original_score: number;
}

export interface AuditStep {
  icon: string;
  text: string;
  phase: string;
}

export interface GradeData {
  id: string;
  ai_score: number;
  confidence: number;
  feedback: string[];
  is_flagged: boolean;
  prof_status: string;
  appeal_reason: string | null;
  graded_at: string;
  reviewed_at: string | null;
  audit_feedback: string[] | null;
  audit_score: number | null;
  audit_notes: string | null;
  students: {
    reg_no: string;
    name: string;
    email: string;
  };
  assessments: {
    subject: string;
    title: string;
    rubric_json: Record<string, { max_marks: number; description: string }> | null;
  };
}
