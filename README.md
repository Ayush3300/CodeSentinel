# CodeSentinel
> An AI agent that reviews your Pull Requests like a senior engineer — in under 30 seconds.

Built with **Groq**, **FastAPI**, and **GitHub Webhooks**. Catches bugs, security issues, and missing tests by running parallel specialist agents on every PR diff.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green?style=flat-square)](https://fastapi.tiangolo.com)
[![Groq](https://img.shields.io/badge/Groq-llama--3.3--70b--versatile-orange?style=flat-square)](https://groq.com)
[![Railway](https://img.shields.io/badge/Deployed%20on-Railway-purple?style=flat-square)](https://railway.app)

---

## What it does
 
When a PR is opened or updated, the agent automatically:
 
1. Fetches and parses the diff into file-level chunks
2. Runs **3 specialist AI agents in parallel** — code quality, logic/security, test coverage — using Groq's LLaMA 3.3 70B model
3. Each finding includes a **category**, **title**, **detailed explanation** (written like a senior engineer mentoring a junior dev), and a **concrete code fix**
4. Aggregates findings into a structured summary (Breakdown by severity, By Category) and posts it as the overall PR review
5. Posts **inline comments on exact diff lines** with severity, category, explanation, and suggested fix
---
 
## Architecture
 
```
PR opened / new commit pushed
            │
            ▼
    GitHub Webhook (pull_request event)
            │
            ▼
    FastAPI Webhook Server (Railway)
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
   Aggregator (Groq summary)
   (merge · deduplicate · rank)
            │
            ▼
   GitHub Reviews API
   (inline comments + verdict)
```
 
---
 
## Tech Stack
 
| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| LLM | Groq API (llama-3.3-70b-versatile) |
| Agent orchestration | Custom async pipeline (asyncio) |
| GitHub integration | PyGithub + Webhooks |
| Deployment | Railway (Docker) |
| Language | Python 3.11+ |
 
---
 
## Getting Started
 
### Prerequisites
 
> Note: Each person running this agent needs their own free Groq API key and GitHub token. This lets the agent act on your own repositories without sharing credentials.
 
- Python 3.11+
- A [Groq API key](https://console.groq.com/)
- A GitHub personal access token with `repo` scope (for private repos) or `public_repo` (for public repos)
- A random `WEBHOOK_SECRET` string for GitHub webhook signature verification
### 1. Clone and install
 
```bash
git clone https://github.com/Ayush3300/CodeSentinel.git
cd CodeSentinel
pip install -r requirements.txt
```
 
### 2. Configure environment variables
 
Copy `.env.example` to `.env` and fill in your values:
 
```env
GROQ_API_KEY=your_groq_api_key_here
GITHUB_TOKEN=your_github_token_here
WEBHOOK_SECRET=your_random_secret_here
```
 
### 3. Run locally
 
```bash
uvicorn main:app --reload --port 8000
```
 
The server starts at `http://localhost:8000`. Health check: `GET /`.
 
### 4. Expose the webhook (local dev)
 
For local development, use a tunnel such as [ngrok](https://ngrok.com/) to expose port 8000:
 
```bash
ngrok http 8000
```
 
Then add a webhook in your GitHub repo:
 
- **Payload URL:** `https://<your-tunnel-url>/webhook`
- **Content type:** `application/json`
- **Secret:** same value as `WEBHOOK_SECRET`
- **Events:** Pull requests
> ngrok is optional and only needed for local development. For production, deploy to Railway (see below).
 
---
 
## Live Deployment
 
This project is deployed on Railway and runs 24/7. To point it at your own repo:
 
1. Fork this repo and deploy to your own Railway project
2. Add your `GROQ_API_KEY`, `GITHUB_TOKEN`, and `WEBHOOK_SECRET` as Railway environment variables
3. Generate a public domain in Railway (Settings → Networking → Generate Domain)
4. Add a webhook in your target repo pointing to `https://your-app.up.railway.app/webhook` with the same `WEBHOOK_SECRET`
5. Select **Pull requests** as the event
---
 
## Project Structure
 
```
.
├── main.py                  # FastAPI webhook server
├── agents/
│   ├── orchestrator.py      # End-to-end review coordinator
│   ├── code_quality.py      # Code quality specialist agent
│   ├── logic_bug.py         # Logic & security specialist agent
│   └── test_coverage.py     # Test coverage specialist agent
├── core/
│   ├── diff_parser.py       # Parse unified diffs into chunks
│   ├── aggregator.py        # Merge, deduplicate, summarize findings
│   └── github_client.py     # GitHub API (diff fetch, post review)
├── prompts/
│   └── review_prompt.py     # LLM prompt templates
├── Dockerfile
├── requirements.txt
└── .env.example
```
 
---
 
## How the agent pipeline works
 
1. **Webhook** — GitHub sends a `pull_request` event (`opened` or `synchronize`) to `POST /webhook`. The server verifies the HMAC signature and kicks off a background review task.
2. **Fetch diff** — `GithubClient` downloads the raw unified diff for the PR head commit.
3. **Parse & chunk** — `parse_diff()` splits the diff into per-file `DiffChunk` objects; `chunk_large_diff()` splits oversized patches.
4. **Parallel agents** — Three specialist agents run concurrently via `asyncio.gather()`, each calling Groq (llama-3.3-70b-versatile) with a tailored prompt.
5. **Aggregate** — Findings are deduplicated by `(filename, line)`, ranked by severity, and a verdict is chosen (`APPROVE` / `COMMENT`).
6. **Summarize** — `format_summary()` calls Groq again with `summary_prompt()` to produce a structured markdown review body.
7. **Post review** — Inline comments (with category, title, explanation, fix) and the summary are submitted via the GitHub Reviews API.
---
 
## What I learned
 
- Designing structured LLM prompts that return rich, mentor-style explanations (category, title, explanation, fix) instead of one-liners
- Debugging webhook signature verification and environment variable propagation on Railway
- Switching LLM providers (Gemini → Groq) due to rate limits, and designing the codebase to make this swap straightforward
- Deploying a FastAPI + Docker app to Railway with persistent webhooks
- Running multiple specialist agents in parallel with `asyncio` while pacing API calls to stay within rate limits
- Parsing GitHub unified diffs and mapping findings to exact line numbers for inline review comments
---
 
## License
 
MIT