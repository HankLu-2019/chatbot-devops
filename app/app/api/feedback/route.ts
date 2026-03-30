import { NextRequest, NextResponse } from "next/server";
import pool from "@/lib/db";

interface FeedbackBody {
  space?: string;
  question: string;
  vote: "up" | "down";
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let body: FeedbackBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { space, question, vote } = body;

  if (!question || typeof question !== "string" || !question.trim()) {
    return NextResponse.json({ error: "question is required" }, { status: 400 });
  }

  if (vote !== "up" && vote !== "down") {
    return NextResponse.json({ error: "vote must be 'up' or 'down'" }, { status: 400 });
  }

  const client = await pool.connect();
  try {
    await client.query(
      "INSERT INTO feedback (space, question, vote) VALUES ($1, $2, $3)",
      [space ?? null, question.trim(), vote]
    );
    return NextResponse.json({ ok: true });
  } catch (err) {
    console.error("Feedback API error:", err);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  } finally {
    client.release();
  }
}
