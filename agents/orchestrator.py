"""
Main coordinator — fetches diffs, runs specialist agents in parallel, posts reviews.
"""

from __future__ import annotations

import asyncio

from agents.code_quality import code_quality_agent
from agents.logic_bug import logic_bug_agent
from agents.test_coverage import test_coverage_agent
from core.aggregator import aggregate, format_summary
from core.diff_parser import DiffChunk


async def run_all_agents(chunks: list[DiffChunk]) -> dict:
    """
    Run code quality, logic/bug, and test-coverage agents concurrently.

    Args:
        chunks: Parsed (and optionally split) diff chunks to review.

    Returns:
        Aggregated result from :func:`core.aggregator.aggregate`.
    """
    quality_findings, bug_findings, coverage_findings = await asyncio.gather(
        code_quality_agent(chunks),
        logic_bug_agent(chunks),
        test_coverage_agent(chunks),
    )

    return aggregate(quality_findings, bug_findings, coverage_findings)


async def orchestrate(
    repo: str,
    pr_number: int,
    head_sha: str,
    diff_url: str,
) -> None:
    """
    End-to-end PR review: fetch diff, run agents, aggregate, post to GitHub.

    Args:
        repo: Full repository name (``owner/repo``).
        pr_number: Pull request number.
        head_sha: HEAD commit SHA for the review.
        diff_url: GitHub diff URL from the webhook payload.
    """
    try:
        from core.diff_parser import chunk_large_diff, parse_diff
        from core.github_client import GithubClient

        client = GithubClient()

        # Step 1: Fetch the raw unified diff from GitHub
        raw_diff = client.get_diff(diff_url)

        # Step 2: Parse into per-file DiffChunk objects
        chunks = parse_diff(raw_diff)

        # Step 3: Split oversized patches so agents stay within context limits
        chunks = chunk_large_diff(chunks)

        # Step 4: Nothing to review — notify on the PR and exit early
        if not chunks:
            client.post_review(
                repo_name=repo,
                pr_number=pr_number,
                commit_sha=head_sha,
                summary="No reviewable changes found",
                findings=[],
                verdict="COMMENT",
            )
            print(f"Review complete for PR #{pr_number} — no reviewable changes")
            return

        # Step 5: Run all three specialist agents in parallel and merge results
        result = await run_all_agents(chunks)

        # Step 6: Build a human-readable summary for the review body
        summary = format_summary(result)

        # Step 7: Post inline comments and verdict to GitHub
        client.post_review(
            repo_name=repo,
            pr_number=pr_number,
            commit_sha=head_sha,
            summary=summary,
            findings=result["findings"],
            verdict=result["verdict"],
        )

        # Step 8: Log completion
        print(
            f"Review complete for PR #{pr_number} — verdict: {result['verdict']}"
        )

    except Exception as exc:
        print(f"[orchestrator] Review failed for {repo}#{pr_number}: {exc}")
