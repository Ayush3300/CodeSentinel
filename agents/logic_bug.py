"""
Logic and security specialist agent — finds bugs and vulnerabilities via Groq.
"""

from __future__ import annotations

import asyncio
import json
import os
import re

import requests
from dotenv import load_dotenv

from core.diff_parser import DiffChunk
from prompts.review_prompt import logic_bug_prompt

load_dotenv()


def call_groq(prompt: str) -> str:
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        },
    )
    return response.json()["choices"][0]["message"]["content"]


# Optional language tag on fenced blocks, e.g. ```json
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_TRAILING_FENCE_RE = re.compile(r"\n?```\s*$")


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that models sometimes add despite instructions."""
    cleaned = text.strip()
    cleaned = _FENCE_RE.sub("", cleaned)
    cleaned = _TRAILING_FENCE_RE.sub("", cleaned)
    return cleaned.strip()


def _parse_findings_response(raw_text: str, filename: str) -> list[dict]:
    """
    Parse the model's JSON response and attach the source filename to each finding.

    Returns an empty list if the payload is invalid or has no findings.
    """
    cleaned = _strip_markdown_fences(raw_text)
    data = json.loads(cleaned)

    findings = data.get("findings", [])
    if not isinstance(findings, list):
        return []

    enriched: list[dict] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        finding = dict(item)
        finding["filename"] = filename
        enriched.append(finding)

    return enriched


async def _review_chunk(chunk: DiffChunk) -> list[dict]:
    """Call Groq for a single diff chunk and return parsed findings."""
    prompt = logic_bug_prompt(chunk.filename, chunk.patch)

    try:
        raw_text = await asyncio.to_thread(call_groq, prompt)
    except Exception as exc:
        print(f"[logic_bug_agent] Groq API error for {chunk.filename}: {exc}")
        return []

    if not raw_text:
        print(f"[logic_bug_agent] Empty response for {chunk.filename}")
        return []

    try:
        return _parse_findings_response(raw_text, chunk.filename)
    except json.JSONDecodeError as exc:
        print(
            f"[logic_bug_agent] Invalid JSON for {chunk.filename}: {exc}"
        )
        return []


async def logic_bug_agent(chunks: list) -> list[dict]:
    """
    Review all diff chunks for logic errors and security issues.

    Iterates over each :class:`~core.diff_parser.DiffChunk`, sends the
    logic/bug prompt to Groq, and merges findings into one list.
    Waits one second between API calls to reduce rate-limit errors.

    Args:
        chunks: List of :class:`DiffChunk` objects from the diff parser.

    Returns:
        Combined findings across all chunks. Each dict includes at least
        ``filename``, ``line``, ``severity``, ``message``, and ``fix``.
        Returns ``[]`` when there are no chunks or no issues found.
    """
    if not chunks:
        return []

    if not os.getenv("GROQ_API_KEY"):
        raise ValueError(
            "GROQ_API_KEY is not set. Add it to your .env file or environment."
        )

    all_findings: list[dict] = []

    for index, chunk in enumerate(chunks):
        # Pace requests to stay under Groq rate limits
        if index > 0:
            await asyncio.sleep(1)

        chunk_findings = await _review_chunk(chunk)
        all_findings.extend(chunk_findings)

    return all_findings
