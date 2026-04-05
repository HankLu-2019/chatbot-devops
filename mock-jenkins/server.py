"""
Mock Jenkins API server for local development and testing.

Simulates the 4 Jenkins REST endpoints used by the Jenkins Debugging Agent.
Provides fake jobs covering the top failure scenarios from the design doc.

Usage:
  JENKINS_URL=http://localhost:8080 in .env.local
  Credentials: any non-empty JENKINS_USER + JENKINS_TOKEN are accepted.

Available fake jobs (use these URLs in the Jenkins Debugger):
  http://localhost:8080/job/payment-service/123    <- ECR auth failure
  http://localhost:8080/job/payment-service/125    <- disk space failure
  http://localhost:8080/job/api-gateway/88         <- HTTP 403 failure
  http://localhost:8080/job/gitlab-sync/42         <- GitLab access failure
  http://localhost:8080/job/new-service/1          <- no prior successful build
  http://localhost:8080/job/payment-service/119    <- successful build (for baseline)
"""

import base64
import os
from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional

app = FastAPI()

# ---------------------------------------------------------------------------
# Auth check — any non-empty user:token pair is accepted
# ---------------------------------------------------------------------------

def check_auth(authorization: Optional[str]) -> bool:
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:]).decode("utf-8")
        user, _, token = decoded.partition(":")
        return bool(user and token)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fake console logs
# ---------------------------------------------------------------------------

LOGS = {
    # payment-service #123 — ECR authentication failure
    ("payment-service", "123"): """\
Started by user admin
Running in Durably Non-Resumable mode in: /var/jenkins_home/workspace/payment-service
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent1 in /var/jenkins_home/workspace/payment-service_123
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Checkout)
[Pipeline] git
 > git rev-parse --resolve-git-dir /var/jenkins_home/workspace/payment-service_123/.git
Fetching changes from the remote Git repository
 > git fetch --tags --force --progress -- https://gitlab.acme.internal/backend/payment-service.git +refs/heads/*:refs/remotes/origin/*
 > git rev-parse refs/remotes/origin/main^{commit}
Checking out Revision abc123def456789 (refs/remotes/origin/main)
 > git checkout -f abc123def456789
Commit message: "fix: payment retry logic on timeout"
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Build)
[Pipeline] sh
+ mvn clean package -DskipTests -q
[BUILD] Compiled 87 source files
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Docker Pull)
[Pipeline] sh
+ docker pull 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
Error response from daemon: Head "https://123456789.dkr.ecr.us-east-1.amazonaws.com/v2/payment-service/manifests/base-jdk17": unauthorized: authentication required
[Pipeline] }
Stage 'Docker Build' skipped due to earlier failure
Stage 'Unit Tests' skipped due to earlier failure
Stage 'Push Image' skipped due to earlier failure
Stage 'Deploy Staging' skipped due to earlier failure
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
""",

    # payment-service #125 — disk space exhausted on worker node
    ("payment-service", "125"): """\
Started by user admin
Running in Durably Non-Resumable mode in: /var/jenkins_home/workspace/payment-service
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent1 in /var/jenkins_home/workspace/payment-service_125
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Checkout)
[Pipeline] git
Fetching changes from the remote Git repository
Checking out Revision bcd234ef5 (refs/remotes/origin/main)
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Build)
[Pipeline] sh
+ mvn clean package -DskipTests -q
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Docker Pull)
[Pipeline] sh
+ docker pull 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
Pulling from payment-service
Status: Image is up to date for 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Docker Build)
[Pipeline] sh
+ docker build -t payment-service:bcd234ef5 .
Sending build context to Docker daemon  98.3MB
Step 1/12 : FROM 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
Step 2/12 : WORKDIR /app
Step 3/12 : COPY target/payment-service.jar .
ERROR: failed to copy files: failed to create symlink: no space left on device
[Pipeline] }
Stage 'Unit Tests' skipped due to earlier failure
Stage 'Push Image' skipped due to earlier failure
Stage 'Deploy Staging' skipped due to earlier failure
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
""",

    # api-gateway #88 — HTTP 403 on internal API call
    ("api-gateway", "88"): """\
Started by timer
Running in Durably Non-Resumable mode in: /var/jenkins_home/workspace/api-gateway
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent2 in /var/jenkins_home/workspace/api-gateway_88
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Checkout)
[Pipeline] git
Checking out Revision def345gh6 (refs/remotes/origin/release/2.4.1)
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Build and Test)
[Pipeline] sh
+ mvn clean verify -q
Tests run: 142, Failures: 0, Errors: 0, Skipped: 0
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Register Service)
[Pipeline] sh
+ curl -s -f -X POST https://service-registry.acme.internal/api/v1/register \
  -H "Authorization: Bearer ${SERVICE_REGISTRY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"api-gateway","version":"2.4.1","environment":"staging"}'
curl: (22) The requested URL returned error: 403
[Pipeline] }
Stage 'Deploy' skipped due to earlier failure
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
""",

    # gitlab-sync #42 — GitLab access denied
    ("gitlab-sync", "42"): """\
Started by user admin
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent1 in /var/jenkins_home/workspace/gitlab-sync_42
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Sync Repos)
[Pipeline] sh
+ git clone https://gitlab.acme.internal/infra/k8s-configs.git
Cloning into 'k8s-configs'...
remote: HTTP Basic: Access denied. The provided password or token is incorrect or your account has 2FA enabled.
remote: You must use a personal access token with 'read_repository' or 'write_repository' scope for Git over HTTP.
fatal: Authentication failed for 'https://gitlab.acme.internal/infra/k8s-configs.git/'
[Pipeline] }
Stage 'Validate Configs' skipped due to earlier failure
Stage 'Apply Changes' skipped due to earlier failure
[Pipeline] }
[Pipeline] End of Pipeline
ERROR: script returned exit code 128
Finished: FAILURE
""",

    # new-service #1 — first-ever build, no prior success
    ("new-service", "1"): """\
Started by user jsmith
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent1 in /var/jenkins_home/workspace/new-service_1
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Checkout)
[Pipeline] git
Checking out Revision aaa111bbb (refs/remotes/origin/main)
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Build)
[Pipeline] sh
+ mvn clean package -q
[ERROR] COMPILATION ERROR :
[ERROR] src/main/java/com/acme/newservice/Application.java:[23,8] error: class Application is public, should be declared in a file named Application.java
[Pipeline] }
Stage 'Test' skipped due to earlier failure
Stage 'Docker Build' skipped due to earlier failure
[Pipeline] }
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
""",

    # payment-service #119 — successful baseline
    ("payment-service", "119"): """\
Started by user admin
[Pipeline] Start of Pipeline
[Pipeline] node
Running on agent1 in /var/jenkins_home/workspace/payment-service_119
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Checkout)
[Pipeline] git
Checking out Revision zyx987wvu (refs/remotes/origin/main)
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Build)
[Pipeline] sh
+ mvn clean package -DskipTests -q
[BUILD] Compiled 87 source files
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Docker Pull)
[Pipeline] sh
+ docker pull 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
Pulling from payment-service
Status: Image is up to date for 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:base-jdk17
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Docker Build)
[Pipeline] sh
+ docker build -t payment-service:zyx987wvu .
Successfully built a1b2c3d4e5f6
Successfully tagged payment-service:zyx987wvu
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Unit Tests)
[Pipeline] sh
Tests run: 198, Failures: 0, Errors: 0, Skipped: 2
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Push Image)
[Pipeline] sh
+ docker push 123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service:zyx987wvu
The push refers to repository [123456789.dkr.ecr.us-east-1.amazonaws.com/payment-service]
Pushed zyx987wvu
[Pipeline] }
[Pipeline] stage
[Pipeline] { (Deploy Staging)
[Pipeline] sh
+ kubectl set image deployment/payment-service payment-service=...
deployment.apps/payment-service image updated
[Pipeline] }
[Pipeline] }
[Pipeline] End of Pipeline
Finished: SUCCESS
""",

    # api-gateway #85 — successful baseline
    ("api-gateway", "85"): """\
Started by timer
[Pipeline] Start of Pipeline
[Pipeline] node
[Pipeline] { (Checkout)
Checking out Revision abc111def (refs/remotes/origin/release/2.4.0)
[Pipeline] { (Build and Test)
Tests run: 142, Failures: 0, Errors: 0, Skipped: 0
[Pipeline] { (Register Service)
+ curl -s -f -X POST https://service-registry.acme.internal/api/v1/register ...
{"status":"registered","id":"api-gateway-2.4.0"}
[Pipeline] { (Deploy)
Deployment complete. api-gateway 2.4.0 is live on staging.
Finished: SUCCESS
""",

    # gitlab-sync #38 — successful baseline
    ("gitlab-sync", "38"): """\
Started by user admin
[Pipeline] { (Sync Repos)
+ git clone https://gitlab.acme.internal/infra/k8s-configs.git
Cloning into 'k8s-configs'...
remote: Enumerating objects: 247, done.
Receiving objects: 100% (247/247), done.
Synced 247 config files.
[Pipeline] { (Validate Configs)
All 12 manifests valid.
[Pipeline] { (Apply Changes)
Applied 3 changes to staging namespace.
Finished: SUCCESS
""",
}

# Build metadata
BUILD_META = {
    ("payment-service", "123"): {"result": "FAILURE", "duration": 43200, "timestamp": 1743400000000, "number": 123},
    ("payment-service", "125"): {"result": "FAILURE", "duration": 67000, "timestamp": 1743420000000, "number": 125},
    ("payment-service", "119"): {"result": "SUCCESS", "duration": 180000, "timestamp": 1743300000000, "number": 119},
    ("api-gateway", "88"):      {"result": "FAILURE", "duration": 38000, "timestamp": 1743410000000, "number": 88},
    ("api-gateway", "85"):      {"result": "SUCCESS", "duration": 175000, "timestamp": 1743350000000, "number": 85},
    ("gitlab-sync", "42"):      {"result": "FAILURE", "duration": 12000, "timestamp": 1743405000000, "number": 42},
    ("gitlab-sync", "38"):      {"result": "SUCCESS", "duration": 25000, "timestamp": 1743355000000, "number": 38},
    ("new-service", "1"):       {"result": "FAILURE", "duration": 8000,  "timestamp": 1743415000000, "number": 1},
}

LAST_SUCCESS = {
    "payment-service": {"number": 119, "timestamp": 1743300000000},
    "api-gateway":     {"number": 85,  "timestamp": 1743350000000},
    "gitlab-sync":     {"number": 38,  "timestamp": 1743355000000},
    # new-service has no successful build
}

JOB_META = {
    "payment-service": {"name": "payment-service", "url": "http://mock-jenkins:8080/job/payment-service/"},
    "api-gateway":     {"name": "api-gateway",     "url": "http://mock-jenkins:8080/job/api-gateway/"},
    "gitlab-sync":     {"name": "gitlab-sync",     "url": "http://mock-jenkins:8080/job/gitlab-sync/"},
    "new-service":     {"name": "new-service",     "url": "http://mock-jenkins:8080/job/new-service/"},
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/job/{job_name}/lastSuccessfulBuild/api/json")
def last_successful_build(job_name: str,
                          authorization: Optional[str] = Header(None)):
    if not check_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    if job_name not in JOB_META:
        raise HTTPException(status_code=404, detail=f"Job {job_name} not found")

    success = LAST_SUCCESS.get(job_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"No successful build found for {job_name}")

    return {
        "result": "SUCCESS",
        "number": success["number"],
        "timestamp": success["timestamp"],
        "url": f"http://mock-jenkins:8080/job/{job_name}/{success['number']}/",
    }


@app.get("/job/{job_name}/api/json")
def job_info(job_name: str, authorization: Optional[str] = Header(None)):
    if not check_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    meta = JOB_META.get(job_name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Job {job_name} not found")

    builds = [
        {"number": int(build_num), "url": f"http://mock-jenkins:8080/job/{job_name}/{build_num}/"}
        for (jn, build_num) in BUILD_META
        if jn == job_name
    ]

    return {
        "name": meta["name"],
        "url": meta["url"],
        "builds": sorted(builds, key=lambda b: b["number"], reverse=True),
    }


@app.get("/job/{job_name}/{build_num}/api/json")
def build_status(job_name: str, build_num: str, request: Request,
                 authorization: Optional[str] = Header(None)):
    if not check_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    key = (job_name, build_num)
    meta = BUILD_META.get(key)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Build {build_num} not found for job {job_name}")

    return {
        "result": meta["result"],
        "duration": meta["duration"],
        "timestamp": meta["timestamp"],
        "number": meta["number"],
        "url": f"http://mock-jenkins:8080/job/{job_name}/{build_num}/",
    }


@app.get("/job/{job_name}/{build_num}/consoleText")
def console_text(job_name: str, build_num: str,
                 authorization: Optional[str] = Header(None)):
    if not check_auth(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    key = (job_name, build_num)
    log = LOGS.get(key)
    if not log:
        raise HTTPException(status_code=404, detail=f"Build {build_num} not found for job {job_name}")

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(log)


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-jenkins"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
