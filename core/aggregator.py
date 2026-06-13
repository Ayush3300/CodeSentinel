"""
Merge and rank findings from all specialist review agents.
"""

from __future__ import annotations

import os
import re

import requests

from prompts.review_prompt import summary_prompt

# Higher index = higher priority when deduplicating
_SEVERITY_RANK = {
    "suggestion": 0,
    "warning": 1,
    "critical": 2,
}

# Sort order for final output (critical first)
_SORT_ORDER = {"critical": 0, "warning": 1, "suggestion": 2}

# Optional markdown fences around LLM summary output
_FENCE_RE = re.compile(r"^```(?:markdown)?\s*\n?", re.IGNORECASE)
_TRAILING_FENCE_RE = re.compile(r"\n?```\s*$")


def call_groq(prompt: str) -> str:
    """Call Groq chat completions API (same pattern as specialist agents)."""
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
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def _strip_markdown_fences(text: str) -> str:
    """Remove optional code fences from LLM markdown output."""
    cleaned = text.strip()
    cleaned = _FENCE_RE.sub("", cleaned)
    cleaned = _TRAILING_FENCE_RE.sub("", cleaned)
    return cleaned.strip()


def aggregate(
    quality_findings: list[dict],
    bug_findings: list[dict],
    coverage_findings: list[dict],
) -> dict:
    """
    Combine findings from code quality, logic/bug, and test-coverage agents.

    Deduplicates by (filename, line), keeping the highest severity. Sorts
    critical → warning → suggestion and picks a GitHub review verdict.

    Args:
        quality_findings: Output from :func:`agents.code_quality.code_quality_agent`.
        bug_findings: Output from :func:`agents.logic_bug.logic_bug_agent`.
        coverage_findings: Output from :func:`agents.test_coverage.test_coverage_agent`.

    Returns:
        Dict with ``findings``, ``verdict``, ``total``, and per-severity counts.
    """
    # Step 1 — Combine all findings into one list
    combined = list(quality_findings) + list(bug_findings) + list(coverage_findings)

    # Step 2 — Deduplicate by filename + line, keep highest severity
    deduped = _deduplicate_findings(combined)

    # Step 3 — Sort: critical first, then warning, then suggestion
    sorted_findings = sorted(
        deduped,
        key=lambda f: (
            _SORT_ORDER.get(_normalize_severity(f.get("severity")), 99),
            f.get("filename", ""),
            f.get("line", 0),
        ),
    )

    # Count by severity for the response payload
    critical_count = _count_severity(sorted_findings, "critical")
    warning_count = _count_severity(sorted_findings, "warning")
    suggestion_count = _count_severity(sorted_findings, "suggestion")

    # Step 4 — Decide GitHub review event from worst severity present
    verdict = _decide_verdict(sorted_findings)

    # Step 5 — Return aggregated result
    return {
        "findings": sorted_findings,
        "verdict": verdict,
        "total": len(sorted_findings),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "suggestion_count": suggestion_count,
    }


def format_summary(aggregated: dict) -> str:
    """
    Build a markdown PR review summary via Groq and :func:`summary_prompt`.

    Args:
        aggregated: Result dict from :func:`aggregate`.

    Returns:
        Markdown summary string for the GitHub review body.
    """
    all_findings = aggregated.get("findings", [])

    if not all_findings:
        return (
            "## PR Review Summary\n\n"
            "No issues found. The PR looks clean and ready to merge."
        )

    try:
        prompt = summary_prompt(all_findings)
        raw = call_groq(prompt)
        return _strip_markdown_fences(raw)
    except Exception as exc:
        print(f"[aggregator] Failed to generate summary via Groq: {exc}")
        total = aggregated.get("total", 0)
        critical = aggregated.get("critical_count", 0)
        warnings = aggregated.get("warning_count", 0)
        suggestions = aggregated.get("suggestion_count", 0)
        return (
            f"## PR Review Summary\n\n"
            f"Found {total} issue(s) across the changed files.\n\n"
            f"### Breakdown\n"
            f"- Critical: {critical}\n"
            f"- Major: {warnings}\n"
            f"- Minor: {suggestions}\n"
        )


def _normalize_severity(severity: str | None) -> str:
    """Normalize severity to lowercase for consistent comparisons."""
    if not severity:
        return "suggestion"
    return str(severity).lower()


def _deduplicate_findings(findings: list[dict]) -> list[dict]:
    """
    Keep one finding per (filename, line) with the highest severity.

    Findings without a usable line are kept as-is (keyed by object identity).
    """
    by_key: dict[tuple[str, int] | int, dict] = {}
    no_line: list[dict] = []

    for finding in findings:
        filename = finding.get("filename", "")
        line = finding.get("line")

        if line is None or line == 0:
            no_line.append(finding)
            continue

        key = (filename, int(line))
        existing = by_key.get(key)

        if existing is None:
            by_key[key] = finding
            continue

        if _SEVERITY_RANK.get(
            _normalize_severity(finding.get("severity")), 0
        ) > _SEVERITY_RANK.get(_normalize_severity(existing.get("severity")), 0):
            by_key[key] = finding

    return list(by_key.values()) + no_line


def _count_severity(findings: list[dict], severity: str) -> int:
    """Count findings matching a severity level (case-insensitive)."""
    target = severity.lower()
    return sum(
        1 for f in findings if _normalize_severity(f.get("severity")) == target
    )


def _decide_verdict(findings: list[dict]) -> str:
    """
    Map combined findings to a GitHub review event.

    - Any critical → COMMENT
    - Any warning (and no critical) → COMMENT
    - Otherwise → APPROVE
    """
    severities = {_normalize_severity(f.get("severity")) for f in findings}

    if "critical" in severities:
        return "COMMENT"
    if "warning" in severities:
        return "COMMENT"
    return "APPROVE"
