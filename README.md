# Flow

Personal X/Twitter content pipeline for OpenClaw. Capture ideas → AI refinement → media generation → approval → posting.

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/youruser/flow.git
cd flow
cp .env.example .env

# 2. Edit .env — set your X_HANDLE and OPENCLAW_GATEWAY_TOKEN

# 3. Set up X credentials (see docs/X-CREDENTIALS.md)

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run
python api.py
# → http://127.0.0.1:5120
```

## What It Does

1. **Capture** — Drop ideas via web UI or API
2. **Refine** — AI agent transforms raw ideas into polished threads
3. **Media** — Generate graphics, screenshots, cards
4. **Review** — Approve/reject/edit before posting
5. **Post** — Publish to X with proper threading

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Required | Description |
|----------|----------|-------------|
| `X_HANDLE` | ✅ | Your X username (without @) |
| `OPENCLAW_GATEWAY_TOKEN` | ✅ | Your OpenClaw gateway token |
| `OAUTH_REDIRECT_URI` | ✅ | Must match your X app settings |
| `SECRETS_DIR` | | Path to credentials (default: `.secrets/`) |
| `REFINER_MODEL` | | AI model for refinement |

See `.env.example` for all options.

## X API Setup

Flow uses OAuth 2.0 for X API access. See [docs/X-CREDENTIALS.md](docs/X-CREDENTIALS.md) for setup instructions.

**TL;DR:**
1. Create an app at [developer.x.com](https://developer.x.com)
2. Get Client ID + Secret
3. Add them to `.secrets/x-oauth.env`
4. Run Flow and click "Connect X Account"

## Stack

- **Backend:** FastAPI + SQLite
- **Frontend:** Vanilla HTML/CSS/JS
- **AI:** OpenClaw agent integration
- **Auth:** X OAuth 2.0 PKCE
- **Posting:** X API v2

## Requirements

- Python 3.10+
- OpenClaw gateway running
- X Developer App

## Project Structure

```
flow/
├── api.py                 # Main FastAPI app
├── db.py                  # Database helpers
├── lib/
│   └── post.py            # X posting (bundled)
├── agents/
│   ├── refiner.py         # AI content refinement
│   └── media.py           # Screenshot generation (via OpenClaw)
├── static/                # Web UI
├── .secrets/              # Your X credentials (gitignored)
└── docs/                  # Documentation
```

## License

MIT
