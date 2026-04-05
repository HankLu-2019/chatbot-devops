import { GoogleGenerativeAI } from "@google/generative-ai";

if (!process.env.GEMINI_API_KEY) {
  throw new Error("GEMINI_API_KEY is required");
}

export const genai = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
