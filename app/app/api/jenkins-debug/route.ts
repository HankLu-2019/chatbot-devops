import { NextRequest, NextResponse } from "next/server";
import { genai } from "@/lib/gemini";
import {
  makeBasicAuth,
  detectBlueOceanUrl,
  normalizeUrl,
  fetchJobStatus,
  fetchConsoleText,
  fetchLastSuccessfulBuild,
  JenkinsError,
} from "@/lib/jenkins";
import {
  JENKINS_FUNCTION_DECLARATIONS,
  DiagnosisResult,
  detectFailedStage,
  prepareLogContext,
} from "@/lib/jenkins-tools";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_TURNS = 8;
const TOOL_TIMEOUT_MS = 10_000;
const TOTAL_TIMEOUT_MS = 60_000;
const MAX_LOG_LINES = 2000;

// ---------------------------------------------------------------------------
// POST /api/jenkins-debug
// Body: { jobUrl: string }
// ---------------------------------------------------------------------------

export async function POST(req: NextRequest) {
  // --- Credential check (request-time, not startup) ---
  const jenkinsUser = process.env.JENKINS_USER;
  const jenkinsToken = process.env.JENKINS_TOKEN;
  if (!jenkinsUser || !jenkinsToken) {
    return NextResponse.json(
      {
        error:
          "Jenkins credentials not configured. " +
          "Add JENKINS_USER and JENKINS_TOKEN to .env / .env.local.",
      },
      { status: 500 }
    );
  }

  const auth = makeBasicAuth(jenkinsUser, jenkinsToken);

  // --- Parse request ---
  let jobUrl: string;
  try {
    const body = await req.json();
    jobUrl = (body.jobUrl ?? "").trim();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  if (!jobUrl) {
    return NextResponse.json({ error: "jobUrl is required." }, { status: 400 });
  }

  // --- Blue Ocean URL detection ---
  const blueOceanError = detectBlueOceanUrl(jobUrl);
  if (blueOceanError) {
    return NextResponse.json({ error: blueOceanError }, { status: 400 });
  }

  // ---------------------------------------------------------------------------
  // Agentic loop
  // ---------------------------------------------------------------------------

  const model = genai.getGenerativeModel({
    model: "gemini-2.5-flash",
    tools: [{ functionDeclarations: JENKINS_FUNCTION_DECLARATIONS }],
    systemInstruction: `You are a Jenkins build failure analyst. You have read-only access to Jenkins via tools.

When given a Jenkins build URL:
1. Call get_job_status to confirm the build failed and get the build number.
   - If result is SUCCESS/ABORTED, stop and say so — nothing to diagnose.
2. Call get_console_log (use the job base URL without build number) to get the failed build's log.
   - Note the failed_stage in the response.
3. Call get_last_successful_build to find the baseline build number.
   - If the response says no baseline exists, skip step 4 and diagnose from the failed log only.
4. Call get_build_log for the baseline build, passing the failed stage name as stage_name.
5. Compare the two logs — what changed? Focus on the error line and the 10 lines above it.
6. Write your diagnosis in exactly this format:
   ROOT CAUSE: <one sentence>
   FIX: <one sentence>

To extract the job base URL from a URL like https://jenkins.acme.com/job/payment-service/123:
- Job base URL = https://jenkins.acme.com/job/payment-service  (strip the build number)
- Build number = 123

Common failure classes:
- "unauthorized: authentication required" or "401" → image pull secret / registry token expired
- "No space left on device" → worker node disk full, needs cleanup or larger volume
- "HTTP 403" on an internal API → service account token expired or missing permissions
- "Authentication failed" on git clone → GitLab/GitHub deploy key or PAT expired
- Compilation error → code bug, not infrastructure

Do not suggest fixes that require write access to Jenkins.`,
  });

  // State shared across tool executions within this request
  let detectedStage: string | undefined;
  let baselineLog: string | null = null;

  // Tool executor: runs one named tool call and returns its result as an object
  async function executeTool(
    name: string,
    args: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    switch (name) {
      case "get_job_status": {
        const buildUrl = normalizeUrl(String(args.job_url ?? ""));
        try {
          const status = await fetchJobStatus(buildUrl, auth);
          return {
            result: status.result,
            duration_ms: status.duration,
            timestamp: status.timestamp,
            build_number: status.buildNumber,
          };
        } catch (err) {
          return { error: jenkinsErrorMessage(err, buildUrl) };
        }
      }

      case "get_console_log": {
        const jobBase = normalizeUrl(String(args.job_base_url ?? ""));
        const buildNum = Number(args.build_number);
        try {
          const { log, truncated } = await fetchConsoleText(
            jobBase,
            buildNum,
            auth,
            MAX_LOG_LINES
          );
          const stage = detectFailedStage(log);
          detectedStage = stage;

          const { failedContext, contextNote } = prepareLogContext(
            log,
            stage,
            null // baseline not fetched yet
          );

          return {
            log: failedContext,
            failed_stage: stage ?? null,
            truncated,
            context_note: contextNote,
          };
        } catch (err) {
          return { error: jenkinsErrorMessage(err, `${jobBase}/${buildNum}`) };
        }
      }

      case "get_last_successful_build": {
        const jobBase = normalizeUrl(String(args.job_base_url ?? ""));
        try {
          const result = await fetchLastSuccessfulBuild(jobBase, auth);
          if (!result) {
            return {
              found: false,
              message:
                "No successful build found for this job. " +
                "Cannot compare logs — diagnosing from failed log only.",
            };
          }
          return {
            found: true,
            build_number: result.buildNumber,
            timestamp: result.timestamp,
          };
        } catch (err) {
          return { error: jenkinsErrorMessage(err, jobBase) };
        }
      }

      case "get_build_log": {
        const jobBase = normalizeUrl(String(args.job_base_url ?? ""));
        const buildNum = Number(args.build_number);
        const stageName =
          typeof args.stage_name === "string" && args.stage_name
            ? args.stage_name
            : detectedStage;

        try {
          const { log, truncated } = await fetchConsoleText(
            jobBase,
            buildNum,
            auth,
            MAX_LOG_LINES
          );
          baselineLog = log;

          const { baselineContext, contextNote } = prepareLogContext(
            "",       // failedLog not needed here
            stageName,
            log
          );

          return {
            log: baselineContext ?? log.split("\n").slice(-200).join("\n"),
            truncated,
            context_note: contextNote,
          };
        } catch (err) {
          return { error: jenkinsErrorMessage(err, `${jobBase}/${buildNum}`) };
        }
      }

      default:
        return { error: `Unknown tool: ${name}` };
    }
  }

  // ---------------------------------------------------------------------------
  // Run the agentic loop with an overall timeout
  // ---------------------------------------------------------------------------

  const startMs = Date.now();
  const messages: Array<{ role: string; parts: unknown[] }> = [
    {
      role: "user",
      parts: [
        {
          text:
            `Diagnose why this Jenkins build failed: ${jobUrl}\n\n` +
            `Job base URL (for console log / last successful build tools): ` +
            `${jobUrl.replace(/\/\d+$/, "")}`,
        },
      ],
    },
  ];

  let turnsUsed = 0;
  let partial = false;
  let finalAnalysis = "";
  let finalBuildNumber: number | undefined;
  let finalFailedStage: string | undefined;

  try {
    for (turnsUsed = 0; turnsUsed < MAX_TURNS; turnsUsed++) {
      // Check overall timeout
      if (Date.now() - startMs > TOTAL_TIMEOUT_MS) {
        partial = true;
        break;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result = await (model as any).generateContent({ contents: messages });
      const response = result.response;

      // Append model turn to history
      messages.push({
        role: "model",
        parts: response.candidates?.[0]?.content?.parts ?? [],
      });

      // Check for function calls
      const calls = response.functionCalls?.() ?? [];
      if (!calls || calls.length === 0) {
        // No more tool calls — model has finished reasoning
        finalAnalysis = response.text?.() ?? "";
        break;
      }

      // Execute all tool calls and collect function responses
      const responseParts: unknown[] = [];
      for (const call of calls) {
        const toolResult = await Promise.race([
          executeTool(call.name, call.args as Record<string, unknown>),
          new Promise<Record<string, unknown>>((resolve) =>
            setTimeout(
              () =>
                resolve({
                  error: `Tool '${call.name}' timed out after ${TOOL_TIMEOUT_MS / 1000}s.`,
                }),
              TOOL_TIMEOUT_MS
            )
          ),
        ]);

        // Extract useful metadata from tool results
        if (call.name === "get_job_status" && toolResult.build_number) {
          finalBuildNumber = Number(toolResult.build_number);
        }
        if (call.name === "get_console_log" && toolResult.failed_stage) {
          finalFailedStage = String(toolResult.failed_stage);
        }

        responseParts.push({
          functionResponse: {
            name: call.name,
            response: toolResult,
          },
        });
      }

      messages.push({ role: "user", parts: responseParts });
    }

    // If we hit max turns without a final answer
    if (turnsUsed >= MAX_TURNS && !finalAnalysis) {
      partial = true;
      finalAnalysis =
        "Analysis reached max depth. " +
        (detectedStage ? `Failed stage detected: '${detectedStage}'. ` : "") +
        "Partial findings are shown above. Try a more specific job URL or check the logs manually.";
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json(
      { error: `Diagnosis failed: ${message}` },
      { status: 500 }
    );
  }

  if (Date.now() - startMs > TOTAL_TIMEOUT_MS) {
    partial = true;
    if (!finalAnalysis) {
      finalAnalysis =
        "Diagnosis timed out after 60s. " +
        (detectedStage ? `Failed stage: '${detectedStage}'. ` : "") +
        "Check Jenkins logs manually.";
    }
  }

  const diagnosisResult: DiagnosisResult = {
    jobUrl,
    buildNumber: finalBuildNumber ?? 0,
    failedStage: finalFailedStage ?? detectedStage,
    analysis: finalAnalysis,
    turnsUsed,
    partial,
  };

  return NextResponse.json(diagnosisResult);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function jenkinsErrorMessage(err: unknown, url: string): string {
  if (err instanceof JenkinsError) {
    return err.message;
  }
  return `Unexpected error fetching ${url}: ${err instanceof Error ? err.message : String(err)}`;
}
