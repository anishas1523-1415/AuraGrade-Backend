/**
 * AuraGrade Report Export — CSV & PDF generators
 *
 * CSV:  Plain text, opens in Excel / Sheets / Power BI.
 * PDF:  Branded document with autoTable (jsPDF).
 *
 * Both run 100% client-side — no backend round-trip needed.
 */

import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ReportRow {
  studentId: string;
  assessment: string;
  totalMarks: number | string;
  maxMarks?: number | string;
  confidence?: number | string;
  feedback: string;
  date: string;
}

/* ------------------------------------------------------------------ */
/*  CSV Export                                                         */
/* ------------------------------------------------------------------ */

function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function downloadCSV(rows: ReportRow[], filename?: string) {
  const headers = [
    "Student ID",
    "Assessment",
    "Total Marks",
    "Max Marks",
    "Confidence",
    "AI Feedback",
    "Date",
  ];

  const csvRows = rows.map((r) =>
    [
      escapeCsvField(String(r.studentId)),
      escapeCsvField(String(r.assessment)),
      String(r.totalMarks),
      String(r.maxMarks ?? ""),
      r.confidence != null ? String(r.confidence) : "",
      escapeCsvField(String(r.feedback)),
      escapeCsvField(String(r.date)),
    ].join(",")
  );

  const csvContent = [headers.join(","), ...csvRows].join("\n");
  const blob = new Blob(["\uFEFF" + csvContent], {
    type: "text/csv;charset=utf-8;",
  });

  const fname =
    filename ??
    `AuraGrade_Report_${new Date().toISOString().split("T")[0]}.csv`;

  triggerDownload(blob, fname);
}

/* ------------------------------------------------------------------ */
/*  PDF Export                                                         */
/* ------------------------------------------------------------------ */

export function downloadPDF(
  rows: ReportRow[],
  title?: string,
  filename?: string,
) {
  const doc = new jsPDF();

  // ── Branded header ──────────────────────────────────────────
  doc.setFontSize(20);
  doc.setTextColor(37, 99, 235); // AuraGrade Blue
  doc.text("AuraGrade", 14, 18);
  doc.setFontSize(12);
  doc.setTextColor(60, 60, 60);
  doc.text(title ?? "AI Evaluation Report", 14, 26);
  doc.setFontSize(9);
  doc.setTextColor(130, 130, 130);
  doc.text(`Generated: ${new Date().toLocaleString()}`, 14, 32);

  // ── Divider line ────────────────────────────────────────────
  doc.setDrawColor(37, 99, 235);
  doc.setLineWidth(0.5);
  doc.line(14, 35, 196, 35);

  // ── Table ───────────────────────────────────────────────────
  autoTable(doc, {
    startY: 40,
    head: [["Student ID", "Assessment", "Marks", "Max", "Confidence", "AI Reasoning"]],
    body: rows.map((r) => [
      String(r.studentId),
      String(r.assessment),
      String(r.totalMarks),
      String(r.maxMarks ?? "—"),
      r.confidence != null ? `${Number(r.confidence).toFixed(1)}%` : "—",
      String(r.feedback).slice(0, 200), // Truncate for table readability
    ]),
    theme: "grid",
    headStyles: {
      fillColor: [37, 99, 235],
      textColor: 255,
      fontStyle: "bold",
      fontSize: 8,
    },
    bodyStyles: { fontSize: 7, cellPadding: 2 },
    alternateRowStyles: { fillColor: [245, 247, 250] },
    columnStyles: {
      0: { cellWidth: 28 },
      1: { cellWidth: 30 },
      2: { cellWidth: 16, halign: "center" },
      3: { cellWidth: 14, halign: "center" },
      4: { cellWidth: 22, halign: "center" },
      5: { cellWidth: "auto" },
    },
    margin: { left: 14, right: 14 },
  });

  // ── Footer ──────────────────────────────────────────────────
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(7);
    doc.setTextColor(160, 160, 160);
    doc.text(
      `AuraGrade • AI-Powered Examination Grading • Page ${i}/${pageCount}`,
      14,
      doc.internal.pageSize.height - 8,
    );
  }

  const fname =
    filename ??
    `AuraGrade_Report_${new Date().toISOString().split("T")[0]}.pdf`;

  doc.save(fname);
}

/* ------------------------------------------------------------------ */
/*  Shared                                                             */
/* ------------------------------------------------------------------ */

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
