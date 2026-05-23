# Autonomous PR Review Agent
> An AI agent that reviews your Pull Requests like a senior engineer - in under 30 seconds.

Built with **Gemini API**, **FastAPI**, **LangGraph**, and **GitHub Actions**. Catches bugs, security issues, and missing tests by running parallel specialist agents on every PR diff.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?style=flat-square)](https://fastapi.tiangolo.com)
[![Gemini API](https://img.shields.io/badge/Gemini-2.0%20Flash-orange?style=flat-square)](https://aistudio.google.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

---

## What it does

When a PR is opened or updated, the agent automatically:

1. Fetches and parses the diff into file-level chunks
2. Runs **3 specialist AI agents in parallel** - code quality, logic/bugs, test coverage
3. Aggregates findings, deduplicates, and ranks by severity
4. Posts **inline comments on exact diff lines** + an overall review decision

---

## Architecture

```
PR opened / new commit pushed
            │
            ▼
    GitHub Actions Workflow
    (triggers on pull_request event)
            │
            ▼
    FastAPI Webhook Server
            │
     ┌──────┼──────┐
     ▼      ▼      ▼
  Code    Logic   Test
 Quality   &     Coverage
  Agent   Bugs    Agent
          Agent
     │      │      │
     └──────┼──────┘
            ▼
   LangGraph Aggregator
   (merge · deduplicate · rank)
            │
            ▼
   GitHub Reviews API
   (inline comments + verdict)
```
