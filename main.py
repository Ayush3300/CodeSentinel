"""
Autonomous PR Review Agent — FastAPI webhook server for GitHub pull_request events.
"""

import asyncio
import hashlib
import hmac
import json
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# Actions we care about on pull_request events
ALLOWED_ACTIONS = frozenset({"opened", "synchronize"})

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(title="Autonomous PR Review Agent")


# ---------------------------------------------------------------------------
# Review pipeline (stub)
# ---------------------------------------------------------------------------
async def run_review(
    repo: str,
    pr_number: int,
    head_sha: str,
    diff_url: str,
) -> None:
    """Run the full PR review pipeline for a single pull request."""
    # TODO: fetch diff, run specialist agents, post review to GitHub
    pass


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------
def verify_webhook_signature(payload_body: bytes, signature_header: str | None) -> bool:
    """
    Verify GitHub's X-Hub-Signature-256 header using HMAC-SHA256.

    GitHub sends: X-Hub-Signature-256: sha256=<hex_digest>
    """
    if not WEBHOOK_SECRET or not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    received_digest = signature_header.removeprefix("sha256=")
    expected_digest = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_digest, received_digest)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
async def health_check() -> dict[str, str]:
    """Liveness check for load balancers and deploy probes."""
    return {"status": "running", "agent": "PR Review Agent"}


@app.post("/webhook")
async def github_webhook(request: Request) -> JSONResponse:
    """
    Receive GitHub webhook events.

    Only pull_request events with action opened or synchronize trigger a review.
    The review runs in the background; this handler returns immediately.
    """
    # Read raw body once — required for signature verification before JSON parse
    body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Only handle pull_request events; ignore pushes, issues, etc.
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "pull_request":
        return JSONResponse(content={"status": "ignored"})

    action = payload.get("action", "")
    if action not in ALLOWED_ACTIONS:
        return JSONResponse(content={"status": "ignored"})

    # Extract fields needed to drive the review pipeline
    try:
        repo = payload["repository"]["full_name"]
        pull_request = payload["pull_request"]
        pr_number = pull_request["number"]
        head_sha = pull_request["head"]["sha"]
        diff_url = pull_request["diff_url"]
    except (KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Malformed pull_request payload")

    # Fire-and-forget: respond to GitHub before the review completes
    asyncio.create_task(run_review(repo, pr_number, head_sha, diff_url))

    return JSONResponse(content={"status": "ok"})


# ---------------------------------------------------------------------------
# Local development entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
