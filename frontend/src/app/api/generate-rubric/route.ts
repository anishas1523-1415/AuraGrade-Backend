import { NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || "");

export async function POST(req: Request) {
  // ── Auth guard ────────────────────────────────────────────
  // Prevent unauthenticated users from burning Gemini quota
  // via this Next.js API route.
  const cookieStore = cookies();
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  // ── End auth guard ────────────────────────────────────────

  try {
    const { transcript } = await req.json();

    if (!transcript || typeof transcript !== "string" || !transcript.trim()) {
      return NextResponse.json(
        { error: "Transcript is empty" },
        { status: 400 }
      );
    }

    const model = genAI.getGenerativeModel({ model: "gemini-2.0-flash" });

    const prompt = `You are an AI assistant helping a teacher build a grading rubric.
Convert the following voice transcript into a structured JSON array.

Transcript: "${transcript}"

Output ONLY a valid JSON array of objects with this exact structure, nothing else:
[
  {
    "criteria": "string (e.g., 'Q1 - Core Definition')",
    "max_marks": number,
    "description": "string (brief grading instruction)"
  }
]

Rules:
- Extract every distinct question or marking criterion mentioned.
- If the teacher says "Question 1 is worth 5 marks", create an entry with max_marks: 5.
- Combine related sub-points under one criterion when logical.
- Use clear, concise labels (e.g. "Q1: Neural Network Definition").
- If the teacher mentions partial credit rules, include them in the description.`;

    const result = await model.generateContent(prompt);
    const responseText = result.response.text();

    const cleanJson = responseText
      .replace(/```json/g, "")
      .replace(/```/g, "")
      .trim();

    const parsed = JSON.parse(cleanJson);
    const criteria = Array.isArray(parsed) ? parsed : parsed.criteria || [];

    return NextResponse.json({
      criteria,
      questions_detected: criteria.length,
      total_marks: criteria.reduce(
        (sum: number, c: { max_marks?: number; marks?: number }) =>
          sum + (c.max_marks ?? c.marks ?? 0),
        0
      ),
      transcript,
    });
  } catch (error) {
    // Log internally, return safe message to client
    console.error("Voice-to-rubric error:", error);
    return NextResponse.json(
      { error: "Failed to generate rubric. Please try again." },
      { status: 500 }
    );
  }
}
