/**
 * Jenkins REST API client — read-only.
 *
 * All functions throw JenkinsError with a user-visible message on failure.
 * Callers (jenkins-debug/route.ts) catch and surface these to the UI.
 */

export class JenkinsError extends Error {
  constructor(
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = "JenkinsError";
  }
}

export interface JobStatus {
  result: "SUCCESS" | "FAILURE" | "ABORTED" | "UNSTABLE";
  duration: number;
  timestamp: number;
  buildNumber: number;
}

export interface ConsoleLogResult {
  log: string;
  truncated: boolean;
}

export interface LastSuccessfulBuild {
  buildNumber: number;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build the HTTP Basic auth header value from env vars. */
export function makeBasicAuth(user: string, token: string): string {
  return "Basic " + Buffer.from(`${user}:${token}`).toString("base64");
}

/**
 * Detect Blue Ocean URL format and return an error string.
 * Returns null if the URL looks like a classic Jenkins URL.
 */
export function detectBlueOceanUrl(jobUrl: string): string | null {
  if (jobUrl.includes("/blue/organizations/")) {
    return (
      "Blue Ocean URLs are not supported. Use the classic Jenkins URL format: " +
      "https://jenkins.acme.com/job/name/123"
    );
  }
  return null;
}

/**
 * Strip trailing slashes and normalize the URL.
 * Does NOT validate whether the URL is reachable.
 */
export function normalizeUrl(url: string): string {
  return url.replace(/\/+$/, "");
}

/** Shared fetch with Basic auth, timeout, and error mapping. */
async function jenkinsGet(
  url: string,
  auth: string,
  timeoutMs = 10_000
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Authorization: auth },
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes("timed out") || message.includes("timeout")) {
      throw new JenkinsError(
        `Jenkins API did not respond within ${timeoutMs / 1000}s. Check VPN/firewall or increase timeout.`
      );
    }
    throw new JenkinsError(
      `Cannot reach Jenkins at ${url}. Check VPN/firewall. (${message})`
    );
  }

  if (response.status === 401 || response.status === 403) {
    throw new JenkinsError(
      `Jenkins returned ${response.status}. Verify JENKINS_USER and JENKINS_TOKEN in .env.`,
      response.status
    );
  }

  if (response.status === 404) {
    throw new JenkinsError(
      `Not found (404): ${url}`,
      404
    );
  }

  if (!response.ok) {
    throw new JenkinsError(
      `Jenkins returned unexpected status ${response.status} for ${url}`,
      response.status
    );
  }

  return response;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Fetch status for a specific build.
 * @param buildUrl Full build URL including build number: https://jenkins.acme.com/job/name/123
 */
export async function fetchJobStatus(
  buildUrl: string,
  auth: string
): Promise<JobStatus> {
  const url = `${normalizeUrl(buildUrl)}/api/json`;
  const response = await jenkinsGet(url, auth);
  const data = await response.json();

  return {
    result: data.result,
    duration: data.duration,
    timestamp: data.timestamp,
    buildNumber: data.number,
  };
}

/**
 * Fetch console log for a build.
 * Returns last `maxLines` lines. Appends a truncation note when the log was trimmed.
 *
 * @param jobBaseUrl Job URL WITHOUT build number: https://jenkins.acme.com/job/name
 * @param buildNumber The build number to fetch
 */
export async function fetchConsoleText(
  jobBaseUrl: string,
  buildNumber: number,
  auth: string,
  maxLines = 2000
): Promise<ConsoleLogResult> {
  const url = `${normalizeUrl(jobBaseUrl)}/${buildNumber}/consoleText`;
  const response = await jenkinsGet(url, auth);
  const fullText = await response.text();

  const lines = fullText.split("\n");
  const truncated = lines.length > maxLines;
  const kept = truncated ? lines.slice(-maxLines) : lines;

  let log = kept.join("\n");
  if (truncated) {
    log +=
      `\n[Note: log truncated to last ${maxLines} lines. ` +
      `Full log was ${lines.length} lines — earlier context may have been omitted.]`;
  }

  return { log, truncated };
}

/**
 * Fetch the last successful build metadata for a job.
 * Returns null when no successful build exists (404).
 *
 * @param jobBaseUrl Job URL WITHOUT build number: https://jenkins.acme.com/job/name
 */
export async function fetchLastSuccessfulBuild(
  jobBaseUrl: string,
  auth: string
): Promise<LastSuccessfulBuild | null> {
  const url = `${normalizeUrl(jobBaseUrl)}/lastSuccessfulBuild/api/json`;
  try {
    const response = await jenkinsGet(url, auth);
    const data = await response.json();
    return { buildNumber: data.number, timestamp: data.timestamp };
  } catch (err) {
    if (err instanceof JenkinsError && err.status === 404) {
      return null;
    }
    throw err;
  }
}
