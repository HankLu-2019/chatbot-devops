import { FunctionDeclaration, SchemaType } from "@google/generative-ai";

// ---------------------------------------------------------------------------
// Shared result type — returned by POST /api/jenkins-debug
// ---------------------------------------------------------------------------

export interface KbSource {
  url: string;
  title: string;
  snippet: string;
}

export interface DiagnosisResult {
  jobUrl: string;
  buildNumber: number;
  failedStage?: string;
  analysis: string;     // Full Gemini diagnosis text
  sources: KbSource[];  // Knowledge base results cited by the agent (Sprint 2+)
  turnsUsed: number;
  partial: boolean;     // true if max turns hit or total timeout reached
}

// ---------------------------------------------------------------------------
// Gemini function declarations — Sprint 1
// ---------------------------------------------------------------------------

export const JENKINS_FUNCTION_DECLARATIONS: FunctionDeclaration[] = [
  {
    name: "get_job_status",
    description:
      "Get the status of a specific Jenkins build. " +
      "Call this first to confirm the build actually failed before fetching logs.",
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        job_url: {
          type: SchemaType.STRING,
          description:
            "Full Jenkins build URL including the build number. " +
            "Example: https://jenkins.acme.com/job/payment-service/123",
        },
      },
      required: ["job_url"],
    },
  },
  {
    name: "get_console_log",
    description:
      "Get the console log for a failed Jenkins build. " +
      "Returns the last 2000 lines of the log and the name of the failed pipeline stage if detected. " +
      "Call this to find the exact error message and stage where the build broke.",
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        job_base_url: {
          type: SchemaType.STRING,
          description:
            "Jenkins job URL WITHOUT the build number. " +
            "Example: https://jenkins.acme.com/job/payment-service",
        },
        build_number: {
          type: SchemaType.NUMBER,
          description: "The build number to fetch the log for.",
        },
      },
      required: ["job_base_url", "build_number"],
    },
  },
  {
    name: "get_last_successful_build",
    description:
      "Find the last successful build number for a Jenkins job. " +
      "Use this to get a baseline build to compare against the failing one.",
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        job_base_url: {
          type: SchemaType.STRING,
          description:
            "Jenkins job URL WITHOUT the build number. " +
            "Example: https://jenkins.acme.com/job/payment-service",
        },
      },
      required: ["job_base_url"],
    },
  },
  {
    name: "get_build_log",
    description:
      "Get the console log for any Jenkins build (typically used to fetch a baseline/successful build log). " +
      "Returns the last 2000 lines. Compare this against the failing build log to spot the difference.",
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        job_base_url: {
          type: SchemaType.STRING,
          description:
            "Jenkins job URL WITHOUT the build number. " +
            "Example: https://jenkins.acme.com/job/payment-service",
        },
        build_number: {
          type: SchemaType.NUMBER,
          description: "The build number to fetch.",
        },
        stage_name: {
          type: SchemaType.STRING,
          description:
            "Optional: the stage name from the failing build. " +
            "If provided, only the section of the log for that stage is returned. " +
            "Pass the value from get_console_log's failed_stage field.",
        },
      },
      required: ["job_base_url", "build_number"],
    },
  },
  {
    name: "search_knowledge_base",
    description:
      "Search the internal Confluence and Jira knowledge base for documentation, runbooks, " +
      "or past incidents related to this failure. " +
      "Use this after identifying the root cause to find known solutions, runbooks, or " +
      "Jira tickets where teammates solved the same problem before. " +
      "Returns the most relevant pages with URLs and snippets.",
    parameters: {
      type: SchemaType.OBJECT,
      properties: {
        query: {
          type: SchemaType.STRING,
          description:
            "Search query describing the problem. Be specific — include the error type, " +
            "tool name, and symptom. " +
            "Example: 'ECR registry credentials expired image pull unauthorized' or " +
            "'Jenkins worker disk space full cleanup'",
        },
        spaces: {
          type: SchemaType.STRING,
          description:
            "Optional: comma-separated list of knowledge base spaces to search. " +
            "Examples: 'CI-CD', 'INFRA', 'CI-CD,INFRA'. Leave empty to search all spaces.",
        },
      },
      required: ["query"],
    },
  },
];

// ---------------------------------------------------------------------------
// Log analysis helpers
// ---------------------------------------------------------------------------

/**
 * Detect the failed pipeline stage from a Jenkins console log.
 * Tries three patterns in order; returns undefined if none match.
 */
export function detectFailedStage(log: string): string | undefined {
  // Pattern 1: Declarative pipeline — "[Pipeline] { (StageName)" followed by a FAILED marker
  const declarativeMatch = log.match(
    /\[Pipeline\] \{ \(([^)]+)\)[\s\S]*?(?=Stage '[^']*' skipped due to earlier failure|ERROR: script returned exit code)/
  );
  if (declarativeMatch) {
    // Walk backwards from the last "[Pipeline] { (StageName)" before the failure
    const stageMatches = [...log.matchAll(/\[Pipeline\] \{ \(([^)]+)\)/g)];
    if (stageMatches.length > 0) {
      // The last stage block before ERROR is the failed one
      const lastStage = stageMatches[stageMatches.length - 1];
      // Only return it if there's a failure marker after it
      const afterStage = log.slice((lastStage.index ?? 0) + lastStage[0].length);
      if (
        afterStage.includes("ERROR:") ||
        afterStage.includes("exit code") ||
        afterStage.includes("FAILURE")
      ) {
        return lastStage[1];
      }
    }
  }

  // Pattern 2: "Stage 'StageName' skipped due to earlier failure"
  // The failed stage is the one BEFORE the first skipped stage
  const skipMatch = log.match(/Stage '([^']+)' skipped due to earlier failure/);
  if (skipMatch) {
    // Find the stage immediately before the skipped ones
    const beforeSkip = log.slice(0, log.indexOf(skipMatch[0]));
    const stageMatches = [...beforeSkip.matchAll(/\[Pipeline\] \{ \(([^)]+)\)/g)];
    if (stageMatches.length > 0) {
      return stageMatches[stageMatches.length - 1][1];
    }
  }

  // Pattern 3: Any ERROR: line — extract surrounding stage from context
  const errorIdx = log.indexOf("\nERROR: ");
  if (errorIdx !== -1) {
    const beforeError = log.slice(0, errorIdx);
    const stageMatches = [...beforeError.matchAll(/\[Pipeline\] \{ \(([^)]+)\)/g)];
    if (stageMatches.length > 0) {
      return stageMatches[stageMatches.length - 1][1];
    }
  }

  return undefined;
}

/**
 * Extract the log section for a specific pipeline stage.
 * Returns the content between "[Pipeline] { (StageName)" and the next "[Pipeline] }" or end.
 * Returns null if the stage is not found in this log.
 */
export function extractStageSection(
  log: string,
  stageName: string
): string | null {
  const startMarker = `[Pipeline] { (${stageName})`;
  const startIdx = log.indexOf(startMarker);
  if (startIdx === -1) return null;

  // Find end: next "[Pipeline] }" after the start, or end of log
  const afterStart = log.slice(startIdx);
  const endMatch = afterStart.match(/\[Pipeline\] \}/);
  const section = endMatch
    ? afterStart.slice(0, (endMatch.index ?? afterStart.length) + endMatch[0].length)
    : afterStart;

  return section.trim();
}

/**
 * Prepare log context to send to Gemini.
 * Applies stage extraction to keep context window usage low.
 *
 * @param failedLog    Full (truncated) log of the failed build
 * @param failedStage  Stage name detected from the failed log (may be undefined)
 * @param baselineLog  Full (truncated) log of the last successful build (may be null if no baseline)
 */
export function prepareLogContext(
  failedLog: string,
  failedStage: string | undefined,
  baselineLog: string | null
): { failedContext: string; baselineContext: string | null; contextNote: string } {
  const TAIL_LINES = 200;

  if (!failedStage) {
    // Stage detection failed — pass last N lines of each
    const failedTail = failedLog.split("\n").slice(-TAIL_LINES).join("\n");
    const baselineTail = baselineLog
      ? baselineLog.split("\n").slice(-TAIL_LINES).join("\n")
      : null;
    return {
      failedContext: failedTail,
      baselineContext: baselineTail,
      contextNote:
        "Failed stage could not be detected automatically. Showing last " +
        `${TAIL_LINES} lines of each log.`,
    };
  }

  const failedSection = extractStageSection(failedLog, failedStage);

  if (!baselineLog) {
    return {
      failedContext: failedSection ?? failedLog.split("\n").slice(-TAIL_LINES).join("\n"),
      baselineContext: null,
      contextNote:
        `No successful baseline build found. ` +
        `Diagnosing from failed build's '${failedStage}' stage only.`,
    };
  }

  const baselineSection = extractStageSection(baselineLog, failedStage);

  if (!baselineSection) {
    // Stage never ran in the baseline — pass only the failing section
    return {
      failedContext: failedSection ?? failedLog.split("\n").slice(-TAIL_LINES).join("\n"),
      baselineContext: null,
      contextNote:
        `Stage '${failedStage}' has no baseline to compare — ` +
        `it did not appear in the last successful build.`,
    };
  }

  return {
    failedContext: failedSection ?? failedLog.split("\n").slice(-TAIL_LINES).join("\n"),
    baselineContext: baselineSection,
    contextNote: `Showing '${failedStage}' stage section from both builds.`,
  };
}
