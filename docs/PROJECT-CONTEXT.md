# PROJECT-CONTEXT.md — Flow: Personal X Pipeline

> Build agent reference. Copy-paste ready.

---

## 1. API Keys / Secrets

All secrets live in a directory pointed to by the `SECRETS_DIR` env var. See `.env.example` for the full list of required variables.

### Twitter/X Credentials

Flow requires two credential files inside `SECRETS_DIR`:

**App credentials** (filename set by `X_CREDENTIALS_FILE`, default `x-oauth.env`)
- Keys: `AUTMORI_CLIENT_ID`, `AUTMORI_CLIENT_SECRET`
- Used for OAuth 2.0 flow (PKCE)

**OAuth 2.0 tokens** (auto-created at `personal-x-oauth2.env` after completing OAuth)
- Keys: `PERSONAL_ACCESS_TOKEN`, `PERSONAL_REFRESH_TOKEN`, `PERSONAL_CLIENT_ID`, `PERSONAL_CLIENT_SECRET`

### Session Secret

Flow auto-generates a session signing secret at `$SECRETS_DIR/.flow_session_secret` on first run.

---

## 2. External Dependencies

Flow depends on two scripts from an external Twitter tooling module. Set their paths in `.env`:

### post.py — X Posting CLI

Set `POST_SCRIPT_PATH` in `.env` to the absolute path of `post.py`.

```bash
# Basic post
python3 post.py "Tweet text" --account personal

# With media
python3 post.py "Tweet with image" --media /path/to/image.png --account personal

# Thread reply
python3 post.py "Reply text" --reply-to <tweet_id> --account personal

# Dry run
python3 post.py "Preview only" --dry-run
```

**Required interface:** accepts `text`, `--account`, `--reply-to`, `--media` flags. Outputs tweet ID in stdout.

**Limits:** 280 chars visible, 4000 max (Premium), 4 media files max

---

### cardlib.py — Card Generation

Set `TWITTER_MODULE_DIR` in `.env` to the directory containing `cardlib.py`.

```python
from cardlib import card

# Custom stat card
path = card("stat",
            number="54 km",
            label="debris along-track uncertainty",
            category="DATA")
```

**Card Types:** `stat`, `conjunction`, `trend`, `compare`, `quote`

---

### FORGE Screenshot API

Set `FORGE_API_URL` in `.env` (default: `http://127.0.0.1:5110/api/screenshot`).

A local screenshot service that accepts HTML and returns PNG bytes.

```bash
# Screenshot raw HTML
POST /api/screenshot
Content-Type: application/json
{"html": "<html>...</html>", "width": 1080, "height": 1350, "scale": 2.0}
```

**Returns:** PNG image bytes

---

## 3. Design System

### NOIR Palette (Primary)

```css
/* Backgrounds */
--bg-primary:     #000000
--bg-secondary:   #080808
--bg-elevated:    #101010
--bg-hover:       #181818
--bg-glass:       rgba(255,255,255,0.02)

/* Text */
--text-primary:   #FFFFFF
--text-secondary: #999999
--text-muted:     #555555

/* Accent */
--accent:         #FF6B35  /* Orange — CTAs, links, focus */
--accent-dim:     rgba(255,107,53,0.15)
--accent-glow:    rgba(255,107,53,0.25)

/* Borders */
--border:         rgba(255,255,255,0.06)
--border-focus:   rgba(255,255,255,0.12)

/* Semantic */
--success:        #00FF88
--error:          #FF3366
--warning:        #FFB800
```

### Card Palette

```python
BG           = "#0A0A0A"   # Near-black canvas
TEXT_PRIMARY = "#ECECEC"
TEXT_SEC     = "#9CA3AF"
TEXT_DIM     = "#555555"
ACCENT       = "#FF6B35"   # Orange — hero stats, wordmark period
RISK_HIGH    = "#EF4444"
RISK_MED     = "#EAB308"
RISK_LOW     = "#22C55E"
```

### Typography

| Font | Weight | Usage |
|------|--------|-------|
| SpaceGrotesk-Bold | 700 | Hero numbers, wordmark, headers |
| SpaceGrotesk-Medium | 500 | Subheads, quote text |
| Inter-Regular | 400 | Labels, body, attribution |
| Inter-SemiBold | 600 | Headers, emphasis |
| JetBrainsMono-Regular | 400 | Data values, timestamps, code |

### Hard Rules

- `em` units over `px` — px only for borders and touch floors
- `border-radius: 0` on buttons, 2px max on cards
- No emojis in UI — Lucide Icons only
- Branding: `NAME.` with orange period

---

## 4. Project File Tree

```
personal-x/
├── api.py                          # FastAPI backend
├── db.py                           # SQLite helpers
├── schema.sql                      # Database schema
├── twitter_interface.py            # Wrapper for post.py/cardlib
├── .env.example                    # Required env vars template
├── requirements.txt                # Python deps
├── cron-config.json                # Cron scheduling config
├── agents/
│   ├── refiner.py                  # AI refinement agent
│   ├── refiner_prompt.md           # Refinement prompt template
│   ├── media.py                    # Media generation agent
│   └── media_prompt.md             # Media prompt template
├── scripts/
│   ├── check_raw_ideas.py          # Cron: check for raw ideas
│   ├── install-service.sh          # Systemd install helper
│   └── screenshot.py               # Screenshot utility
├── static/
│   ├── index.html                  # Main app UI
│   ├── styles.css                  # App styles
│   ├── app.js                      # App frontend logic
│   └── login.html                  # OAuth login page
├── media/
│   └── generated/                  # Generated images (gitignored)
├── docs/
│   ├── SPEC-v1.md                  # Pipeline specification
│   ├── EXECUTION-v1.md             # Implementation plan
│   ├── HOSTING.md                  # Hosting options
│   └── PROJECT-CONTEXT.md          # (this file)
├── arsenal-personal-x.service.template  # Systemd service template
└── nginx.conf.example              # Nginx config example
```

---

## 5. Quick Snippets

### Run locally

```bash
cp .env.example .env
# Edit .env — fill in SECRETS_DIR, POST_SCRIPT_PATH, TWITTER_MODULE_DIR, etc.
pip install -r requirements.txt
python api.py
# → http://127.0.0.1:5120
```

### Post with generated card

```bash
# With POST_SCRIPT_PATH and TWITTER_MODULE_DIR set:
python -c "
from twitter_interface import post_tweet
# Generate card via cardlib first, then post
post_tweet('The covariance gap is real.', media='/tmp/card.png')
"
```

### Check raw ideas

```bash
python scripts/check_raw_ideas.py
```

---

## 6. Environment Setup

See `.env.example` for all required variables. Key setup steps:

```bash
# 1. Copy template
cp .env.example .env

# 2. Install deps
pip install -r requirements.txt

# 3. Start server
python api.py
```

For production, use the systemd service template:
```bash
./scripts/install-service.sh /path/to/flow
sudo systemctl start flow
```

---

*See HOSTING.md for deployment options.*
