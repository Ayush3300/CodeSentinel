"""
GitHub API client for fetching PR diffs and posting review results.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv
from github import Github
from github.GithubException import GithubException

# Load .env so GITHUB_TOKEN is available when this module is imported directly
load_dotenv()


class GithubClient:
    """
    Thin wrapper around PyGithub and the REST API for PR review workflows.

    Requires ``GITHUB_TOKEN`` in the environment (classic PAT or fine-grained
    token with ``pull_requests:write`` and ``contents:read`` as needed).
    """

    def __init__(self) -> None:
        """Initialize the PyGithub client using ``GITHUB_TOKEN`` from the environment."""
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError(
                "GITHUB_TOKEN is not set. Add it to your .env file or environment."
            )

        self._token = token
        self.gh = Github(token)

    def get_diff(self, diff_url: str) -> str:
        """
        Fetch the raw unified diff for a pull request.

        Args:
            diff_url: URL from the pull_request webhook payload (``diff_url`` field).

        Returns:
            The raw diff text.

        Raises:
            requests.HTTPError: If the HTTP request fails.
            requests.RequestException: On network or timeout errors.
        """
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github.v3.diff",
        }

        response = requests.get(diff_url, headers=headers, timeout=60)
        response.raise_for_status()
        return response.text

    def post_review(
        self,
        repo_name: str,
        pr_number: int,
        commit_sha: str,
        summary: str,
        findings: list[dict],
        verdict: str,
    ) -> bool:
        """
        Submit a pull request review with optional inline comments.

        Args:
            repo_name: Full repository name (``owner/repo``).
            pr_number: Pull request number.
            commit_sha: HEAD commit SHA to attach the review to.
            summary: Top-level review body (markdown supported).
            findings: List of dicts with keys ``filename``, ``line``, ``severity``,
                ``category``, ``title``, ``explanation``, and ``fix``. Entries
                without a valid line are skipped.
            verdict: Review event — ``APPROVE``, ``REQUEST_CHANGES``, or ``COMMENT``.

        Returns:
            ``True`` if the review was created, ``False`` on failure.
        """
        inline_comments = self._build_inline_comments(findings)

        try:
            repo = self.gh.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            commit = repo.get_commit(commit_sha)
            pr.create_review(
                commit=commit,
                body=summary,
                event=verdict,
                comments=inline_comments,
            )
            return True
        except GithubException as exc:
            print(f"[GithubClient] Failed to post review on {repo_name}#{pr_number}: {exc}")
            return False
        except Exception as exc:
            import traceback

            print(f"[GithubClient] Full error: {traceback.format_exc()}")
            return False

    def get_pr_info(self, repo_name: str, pr_number: int) -> dict:
        """
        Fetch basic metadata about a pull request.

        Args:
            repo_name: Full repository name (``owner/repo``).
            pr_number: Pull request number.

        Returns:
            Dict with ``title``, ``author``, ``base_branch``, ``head_branch``,
            and ``changed_files`` (file count).

        Raises:
            GithubException: If the repository or pull request cannot be loaded.
        """
        try:
            repo = self.gh.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            return {
                "title": pr.title,
                "author": pr.user.login if pr.user else "unknown",
                "base_branch": pr.base.ref,
                "head_branch": pr.head.ref,
                "changed_files": pr.changed_files,
            }
        except GithubException:
            raise
        except Exception as exc:
            raise GithubException(
                status=0,
                data={"message": str(exc)},
                headers=None,
            ) from exc

    @staticmethod
    def _build_inline_comments(findings: list[dict]) -> list[dict]:
        """
        Convert agent findings into GitHub review comment payloads.

        Skips findings missing a positive line number.
        """
        inline_comments: list[dict] = []

        for finding in findings:
            line = finding.get("line")
            if line is None or line == 0:
                continue

            filename = finding.get("filename")
            severity = str(finding.get("severity", "info")).upper()
            category = finding.get("category", "General")
            title = finding.get("title", "Issue")
            explanation = finding.get("explanation", "")
            fix = finding.get("fix", "")

            if not filename:
                continue

            body = (
                f"**{severity} — {category}**\n\n"
                f"**{title}**\n\n"
                f"{explanation}\n\n"
                f"**Suggested fix:**\n```python\n{fix}\n```"
            )

            inline_comments.append(
                {
                    "path": filename,
                    "line": int(line),
                    "body": body,
                }
            )

        return inline_comments
