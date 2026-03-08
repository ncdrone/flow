"""FastAPI backend for Personal X Pipeline."""

import hashlib
import json
import os
import re
import secrets
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import Cookie, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from PIL import Image
import io

import db

app = FastAPI(title="Personal X Pipeline", version="1.0.0")

# ============ SESSION MANAGEMENT ============

# Resolve secrets directory from env var or fall back to relative heuristic
_secrets_env = os.environ.get("SECRETS_DIR")
if _secrets_env:
    SECRETS_DIR = Path(_secrets_env)
else:
    # Fallback: 3 levels up from this file (original behaviour)
    SECRETS_DIR = Path(__file__).parent.parent.parent / '.secrets'

if not SECRETS_DIR.exists():
    raise RuntimeError(
        f"Secrets directory not found at {SECRETS_DIR}. "
        "Set SECRETS_DIR in .env or create the directory."
    )

SESSION_SECRET = (SECRETS_DIR / '.flow_session_secret').read_text().strip() if (SECRETS_DIR / '.flow_session_secret').exists() else None

def init_session_secret():
    """Initialize session secret if not exists."""
    global SESSION_SECRET
    secret_file = SECRETS_DIR / '.flow_session_secret'
    if not secret_file.exists():
        SESSION_SECRET = secrets.token_hex(32)
        secret_file.write_text(SESSION_SECRET)
    else:
        SESSION_SECRET = secret_file.read_text().strip()

init_session_secret()


def create_session_token() -> str:
    """Create a signed session token."""
    timestamp = str(int(datetime.now().timestamp()))
    payload = f"flow:{timestamp}"
    signature = hashlib.sha256(f"{payload}:{SESSION_SECRET}".encode()).hexdigest()[:16]
    return f"{payload}:{signature}"


def verify_session_token(token: str) -> bool:
    """Verify a session token is valid."""
    if not token or ':' not in token:
        return False
    try:
        parts = token.rsplit(':', 1)
        if len(parts) != 2:
            return False
        payload, signature = parts
        expected_sig = hashlib.sha256(f"{payload}:{SESSION_SECRET}".encode()).hexdigest()[:16]
        return secrets.compare_digest(signature, expected_sig)
    except Exception:
        return False


def has_valid_tokens() -> bool:
    """Check if OAuth tokens exist and are populated."""
    token_file = SECRETS_DIR / 'personal-x-oauth2.env'
    if not token_file.exists():
        return False
    content = token_file.read_text()
    return 'PERSONAL_ACCESS_TOKEN=' in content and len(content) > 100


def resize_image_for_web(input_path: Path, max_width: int = 1200, quality: int = 88) -> Path:
    """Resize an image to max_width and re-save as JPEG for mobile-friendly display.
    
    Twitter recommends 1200x675 max. iOS Safari can fail silently on images
    decoded to >32MB in memory (e.g. 3840x2160 = ~33MB).
    
    Returns the path of the resized image (replaces .png with .jpg if needed).
    """
    with Image.open(input_path) as img:
        w, h = img.size
        if w <= max_width and input_path.suffix.lower() == '.jpg':
            return input_path  # Already small enough and JPEG
        
        # Resize maintaining aspect ratio
        if w > max_width:
            ratio = max_width / w
            new_h = int(h * ratio)
            img = img.resize((max_width, new_h), Image.LANCZOS)
        
        # Convert to RGB (required for JPEG)
        if img.mode in ('RGBA', 'P', 'LA'):
            background = Image.new('RGB', img.size, (10, 10, 10))  # Dark bg to match app
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Save as JPEG
        out_path = input_path.with_suffix('.jpg')
        img.save(out_path, 'JPEG', quality=quality, optimize=True)
        
        # Remove original PNG if different from output
        if input_path != out_path and input_path.exists():
            input_path.unlink()
        
        return out_path


def convert_media_path(path: str) -> str:
    """Convert absolute filesystem paths to URL paths."""
    if not path:
        return None
    # Handle absolute paths like /var/lib/.../media/generated/file.png
    if '/media/' in path:
        idx = path.find('/media/')
        return path[idx:]  # Returns /media/generated/file.png
    # Handle /static/ paths
    if '/static/' in path:
        idx = path.find('/static/')
        return path[idx:]
    # Already a URL path
    if path.startswith('/media/') or path.startswith('/static/'):
        return path
    return path


def process_draft_paths(draft: dict) -> dict:
    """Convert all media paths in a draft to URL paths."""
    if not draft:
        return draft
    
    # Convert draft-level media_path
    if draft.get('media_path'):
        draft['media_path'] = convert_media_path(draft['media_path'])
    
    # Convert thread-level media_paths
    if draft.get('thread'):
        for tweet in draft['thread']:
            if tweet.get('media_path'):
                tweet['media_path'] = convert_media_path(tweet['media_path'])
    
    return draft


# Static files for uploaded media
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Media files (generated images, screenshots)
MEDIA_DIR = Path(__file__).parent / "media"
MEDIA_DIR.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# ============ MODELS ============

class IdeaCreate(BaseModel):
    content: str
    link: Optional[str] = None
    tags: Optional[str] = None
    image_path: Optional[str] = None


class IdeaUpdate(BaseModel):
    content: Optional[str] = None
    link: Optional[str] = None
    tags: Optional[str] = None
    image_path: Optional[str] = None
    status: Optional[str] = None


class DraftUpdate(BaseModel):
    thread_json: Optional[str] = None
    media_path: Optional[str] = None
    media_type: Optional[str] = None
    validation_grade: Optional[str] = None
    hook_type: Optional[str] = None
    revision_notes: Optional[str] = None


class RevisionRequest(BaseModel):
    notes: str


class UploadResponse(BaseModel):
    path: str
    filename: str


# ============ IDEAS ENDPOINTS ============

@app.post("/ideas")
def create_idea(idea: IdeaCreate):
    """Create a new idea."""
    idea_id = db.create_idea(
        content=idea.content,
        link=idea.link,
        tags=idea.tags,
        image_path=idea.image_path
    )
    return {"id": idea_id, "status": "created"}


@app.get("/ideas")
def list_ideas(status: Optional[str] = Query(None)):
    """List all ideas, optionally filtered by status."""
    return db.get_ideas(status=status)


@app.get("/ideas/{idea_id}")
def get_idea(idea_id: int):
    """Get a single idea."""
    idea = db.get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")
    return idea


@app.put("/ideas/{idea_id}")
def update_idea(idea_id: int, update: IdeaUpdate):
    """Update an idea."""
    if not db.get_idea(idea_id):
        raise HTTPException(status_code=404, detail="Idea not found")
    
    db.update_idea(
        idea_id,
        content=update.content,
        link=update.link,
        tags=update.tags,
        image_path=update.image_path,
        status=update.status
    )
    return db.get_idea(idea_id)


@app.delete("/ideas/{idea_id}")
def delete_idea(idea_id: int):
    """Delete an idea."""
    if not db.delete_idea(idea_id):
        raise HTTPException(status_code=404, detail="Idea not found")
    return {"status": "deleted"}


@app.post("/ideas/{idea_id}/refine")
def refine_idea(idea_id: int):
    """Notify Metis (main session) to spawn Seshat and refine the idea."""
    idea = db.get_idea(idea_id)
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Archive original content before any refinement
    db.archive_idea_original(idea_id)
    
    db.set_idea_status(idea_id, "refining")

    import threading

    def notify_metis():
        try:
            content_preview = (idea.get("content") or "")[:100]
            notification = (
                f"REFINE_REQUEST\n"
                f"idea_id: {idea_id}\n"
                f"content: {content_preview}"
            )

            result = subprocess.run(
                ["openclaw", "sessions", "send", "--label", "main", "--message", notification],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"[refine] Failed to notify Metis for idea {idea_id}: {result.stderr}")
                db.set_idea_status(idea_id, "raw")
        except Exception as e:
            db.set_idea_status(idea_id, "raw")
            print(f"[refine] Exception notifying Metis for idea {idea_id}: {e}")

    thread = threading.Thread(target=notify_metis, daemon=True)
    thread.start()

    return {"id": idea_id, "status": "refining"}


# ============ DRAFTS ENDPOINTS ============

@app.get("/drafts")
def list_drafts(status: Optional[str] = Query(None)):
    """List all drafts, optionally filtered by status."""
    drafts = db.get_drafts(status=status)
    return [process_draft_paths(d) for d in drafts]


@app.get("/drafts/{draft_id}")
def get_draft(draft_id: int):
    """Get a single draft."""
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return process_draft_paths(draft)


@app.post("/drafts/{draft_id}/dry-run")
def dry_run_post(draft_id: int):
    """
    VERIFICATION GATE: Show exactly what will be posted.
    Run this BEFORE approving any post.
    """
    import os
    from PIL import Image
    
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    thread = json.loads(draft["thread_json"])
    draft_media = draft.get("media_path")
    
    result = {
        "draft_id": draft_id,
        "tweet_count": len(thread),
        "tweets": [],
        "warnings": [],
        "ready_to_post": True
    }
    
    for i, tweet in enumerate(thread):
        tweet_info = {
            "index": i + 1,
            "text": tweet["text"],
            "char_count": len(tweet["text"]),
            "media": None
        }
        
        # Determine media path for this tweet
        if i == 0:
            media_path = tweet.get("media_path") or draft_media
        else:
            media_path = tweet.get("media_path")
        
        if media_path:
            resolved = resolve_media_path(media_path)
            exists = os.path.exists(resolved) if resolved else False
            
            media_info = {
                "url_path": convert_media_path(media_path),
                "resolved_path": resolved,
                "exists": exists
            }
            
            if exists:
                try:
                    with Image.open(resolved) as img:
                        media_info["dimensions"] = f"{img.width}x{img.height}"
                        media_info["format"] = img.format
                        media_info["size_kb"] = round(os.path.getsize(resolved) / 1024, 1)
                except:
                    media_info["dimensions"] = "unknown"
            else:
                result["warnings"].append(f"Tweet {i+1}: Media file not found: {resolved}")
                result["ready_to_post"] = False
            
            tweet_info["media"] = media_info
        
        result["tweets"].append(tweet_info)
    
    return result


@app.put("/drafts/{draft_id}")
def update_draft(draft_id: int, update: DraftUpdate):
    """Update a draft (edit thread text, etc.)."""
    if not db.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    
    db.update_draft(
        draft_id,
        thread_json=update.thread_json,
        media_path=update.media_path,
        media_type=update.media_type,
        validation_grade=update.validation_grade,
        hook_type=update.hook_type,
        revision_notes=update.revision_notes
    )
    return db.get_draft(draft_id)


@app.post("/drafts/{draft_id}/request-revision")
def request_revision(draft_id: int, body: RevisionRequest):
    """Save revision notes and mark draft as revision_requested."""
    if not db.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    
    if not body.notes or not body.notes.strip():
        raise HTTPException(status_code=400, detail="Revision notes cannot be empty")
    
    db.update_draft(
        draft_id,
        revision_notes=body.notes.strip(),
        status="revision_requested"
    )
    return {"id": draft_id, "status": "revision_requested"}


@app.post("/drafts/{draft_id}/approve")
def approve_draft(draft_id: int):
    """Approve and post a draft to X."""
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    if draft["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve draft with status '{draft['status']}'"
        )
    
    try:
        thread_url = post_thread(draft)
        db.mark_draft_posted(draft_id, thread_url)
        # Archive the posted draft for reference
        db.archive_posted_draft(draft_id, thread_url)
        return {"id": draft_id, "status": "posted", "thread_url": thread_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post: {str(e)}")


@app.post("/drafts/{draft_id}/reject")
def reject_draft(draft_id: int):
    """Reject a draft."""
    if not db.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    
    db.set_draft_status(draft_id, "rejected")
    return {"id": draft_id, "status": "rejected"}


@app.post("/drafts/{draft_id}/archive")
def archive_draft(draft_id: int):
    """Archive a draft."""
    if not db.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")
    
    db.set_draft_status(draft_id, "archived")
    return {"id": draft_id, "status": "archived"}


class MediaPrompt(BaseModel):
    prompt: str
    tweet_index: int = 0  # Which tweet to attach media to


@app.post("/drafts/{draft_id}/generate-media")
def generate_media(draft_id: int, body: MediaPrompt):
    """Generate media for a draft using Forge screenshot API."""
    import requests
    import time
    
    draft = db.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    # Generate HTML for a branded quote/text card
    html = f'''<!DOCTYPE html>
<html>
<head>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  width: 3840px;
  height: 2160px;
  background: #0A0A0A;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 200px;
}}
.card {{
  background: #111;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 24px;
  padding: 120px;
  max-width: 3000px;
  text-align: center;
}}
.prompt {{
  font-size: 72px;
  font-weight: 500;
  color: #ECECEC;
  line-height: 1.4;
}}
.accent {{
  color: #FF6B35;
}}
</style>
</head>
<body>
<div class="card">
  <div class="prompt">{prompt.replace('<', '&lt;').replace('>', '&gt;')}<span class="accent">.</span></div>
</div>
</body>
</html>'''
    
    # Call Forge API
    try:
        timestamp = int(time.time())
        output_filename = f"generated-{draft_id}-{timestamp}.png"
        output_path = MEDIA_DIR / "generated" / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        forge_api_url = os.environ.get("FORGE_API_URL", "http://127.0.0.1:5110/api/screenshot")
        response = requests.post(
            forge_api_url,
            json={'html': html, 'width': 3840, 'height': 2160, 'scale': 1.0},
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Forge API error: {response.text}")
        
        output_path.write_bytes(response.content)
        
        # Resize to mobile-friendly dimensions (max 1200px wide, JPEG)
        # Prevents iOS Safari silent failures on large images (>32MB decoded)
        output_path = resize_image_for_web(output_path, max_width=1200)
        output_filename = output_path.name
        
        # Update draft with media path
        media_url = f"/media/generated/{output_filename}"
        
        # Update the thread JSON to add media to specific tweet
        thread = json.loads(draft["thread_json"]) if draft["thread_json"] else []
        if body.tweet_index < len(thread):
            thread[body.tweet_index]["media_path"] = str(output_path)
            thread[body.tweet_index]["has_media"] = True
        
        db.update_draft(draft_id, thread_json=json.dumps(thread), media_path=str(output_path))
        
        return {
            "id": draft_id,
            "media_path": media_url,
            "tweet_index": body.tweet_index,
            "status": "generated"
        }
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate media: {str(e)}")


# ============ MEDIA UPLOAD ============

@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)):
    """Upload a media file."""
    # Generate unique filename
    ext = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = STATIC_DIR / filename
    
    # Save file
    content = await file.read()
    filepath.write_bytes(content)
    
    # Resize to mobile-friendly dimensions if it's an image
    try:
        filepath = resize_image_for_web(filepath, max_width=1200)
        filename = filepath.name
    except Exception:
        pass  # Not an image or resize failed — keep original
    
    return UploadResponse(
        path=f"/static/{filename}",
        filename=filename
    )


# ============ POSTING INTEGRATION ============
# Posting is handled via twitter_interface.py which auto-discovers lib/post.py


def extract_tweet_id(output: str) -> Optional[str]:
    """Extract tweet ID from post.py output."""
    # Try to find ID in output - adjust pattern based on actual output format
    # Common patterns: "Tweet posted: 1234567890" or JSON with "id": "1234567890"
    patterns = [
        r'"id":\s*"?(\d+)"?',
        r'Tweet.*?(\d{15,})',
        r'status/(\d+)',
        r'^(\d{15,})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, output, re.MULTILINE)
        if match:
            return match.group(1)
    return None


def resolve_media_path(path: str) -> str:
    """Resolve a media path to an absolute filesystem path."""
    if not path:
        return None
    # Already absolute
    if path.startswith("/var/") or path.startswith("/home/"):
        return path
    # Relative /static/ path
    if path.startswith("/static/"):
        return str(STATIC_DIR / path.replace("/static/", ""))
    # Relative /media/ path
    if path.startswith("/media/"):
        return str(MEDIA_DIR / path.replace("/media/", ""))
    return path


def post_thread(draft: dict) -> str:
    """Post a thread to X and return the thread URL."""
    from twitter_interface import post_tweet as _post_tweet

    thread = json.loads(draft["thread_json"])
    draft_media = draft.get("media_path")

    if not thread:
        raise ValueError("Empty thread")

    # Post first tweet - prefer per-tweet media, fall back to draft-level
    first_tweet = thread[0]
    media_path = first_tweet.get("media_path") or draft_media
    media_path = resolve_media_path(media_path)

    output = _post_tweet(first_tweet["text"], account="personal", media=media_path)

    first_id = extract_tweet_id(output)
    if not first_id:
        raise RuntimeError(f"Could not extract tweet ID from output: {output}")

    # Post replies - include media if tweet has media_path
    reply_to = first_id
    for tweet in thread[1:]:
        tweet_media = resolve_media_path(tweet.get("media_path"))
        output = _post_tweet(
            tweet["text"],
            account="personal",
            reply_to=reply_to,
            media=tweet_media,
        )
        new_id = extract_tweet_id(output)
        if new_id:
            reply_to = new_id

    x_handle = os.environ.get("X_HANDLE", "unknown")
    return f"https://x.com/{x_handle}/status/{first_id}"


# ============ VERIFY CONNECTION ============

@app.get("/verify")
def verify_connection():
    """Verify X credentials via GET /2/users/me — no post, no quota cost."""
    try:
        from twitter_interface import verify_credentials
        result = verify_credentials("personal")
        return result
    except Exception as exc:
        return {"ok": False, "handle": "", "id": "", "error": str(exc)}


# ============ OAUTH 2.0 CALLBACK ============

@app.get("/oauth/callback")
def oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """X OAuth 2.0 callback — exchanges code for tokens instantly server-side."""
    import base64 as _b64, hashlib as _hs, json as _json, urllib.parse as _up, urllib.request as _ur, urllib.error as _ue

    SECRETS = SECRETS_DIR  # module-level var set from SECRETS_DIR env
    STATE_FILE = SECRETS / '.personal_oauth2_state.json'

    if error:
        return _html_response(f"<h2>❌ Auth denied</h2><p>{error}</p>")

    if not code or not state:
        return _html_response("<h2>❌ Missing code or state</h2>")

    # Load saved state
    try:
        saved = _json.loads(STATE_FILE.read_text())
    except Exception:
        return _html_response("<h2>❌ No pending auth session found. Generate a new link.</h2>")

    if state != saved['state']:
        return _html_response("<h2>❌ State mismatch — possible CSRF. Generate a new link.</h2>")

    # Load client creds
    _x_creds_file = os.environ.get("X_CREDENTIALS_FILE", "x-oauth.env")
    x_env = {}
    for line in (SECRETS / _x_creds_file).read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            x_env[k] = v

    # Support multiple key naming conventions
    client_id = x_env.get('CLIENT_ID') or x_env.get('X_CLIENT_ID')
    client_secret = x_env.get('CLIENT_SECRET') or x_env.get('X_CLIENT_SECRET')
    if not client_id or not client_secret:
        return _html_response("<h2>❌ CLIENT_ID or CLIENT_SECRET not found in credentials file.</h2>")

    data = _up.urlencode({
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': os.environ.get("OAUTH_REDIRECT_URI", "https://your-domain.com/oauth/callback"),  # Must match /oauth/start
        'code_verifier': saved['verifier'],
    }).encode()

    auth = _b64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = _ur.Request(
        'https://api.x.com/2/oauth2/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded', 'Authorization': f'Basic {auth}'}
    )

    try:
        tokens = _json.loads(_ur.urlopen(req, timeout=10).read())
    except _ue.HTTPError as exc:
        body = exc.read().decode()
        return _html_response(f"<h2>❌ Token exchange failed</h2><pre>{body}</pre>")

    access_token = tokens['access_token']
    refresh_token = tokens.get('refresh_token', '')
    scope = tokens.get('scope', '')
    expires_in = tokens.get('expires_in', 0)

    x_handle = os.environ.get("X_HANDLE", "user")
    (SECRETS / 'personal-x-oauth2.env').write_text(
        f"# @{x_handle} OAuth 2.0 tokens — Flow app\n"
        f"# Scopes: {scope}\n"
        f"PERSONAL_ACCESS_TOKEN={access_token}\n"
        f"PERSONAL_REFRESH_TOKEN={refresh_token}\n"
        f"PERSONAL_CLIENT_ID={client_id}\n"
        f"PERSONAL_CLIENT_SECRET={client_secret}\n"
    )
    STATE_FILE.unlink(missing_ok=True)

    # Create session and redirect to app
    session_token = create_session_token()
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="flow_session",
        value=session_token,
        httponly=True,
        secure=False,  # Tailscale is HTTP internally
        samesite="lax",
        max_age=60 * 60 * 24 * 30  # 30 days
    )
    return response

@app.get("/oauth/start")
def oauth_start():
    """Generate an OAuth 2.0 auth URL and redirect the user to X to authorize."""
    import base64 as _b64, hashlib as _hs, json as _json, secrets as _sec, urllib.parse as _up

    SECRETS = SECRETS_DIR  # module-level var set from SECRETS_DIR env

    _x_creds_file = os.environ.get("X_CREDENTIALS_FILE", "x-oauth.env")
    x_env = {}
    for line in (SECRETS / _x_creds_file).read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            x_env[k] = v

    # Support multiple key naming conventions
    client_id = x_env.get('CLIENT_ID') or x_env.get('X_CLIENT_ID')
    if not client_id:
        return _html_response("<h2>❌ CLIENT_ID not found in credentials file.</h2>")
    verifier = _sec.token_urlsafe(64)[:128]
    challenge = _b64.urlsafe_b64encode(_hs.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    state = _sec.token_urlsafe(32)

    (SECRETS / '.personal_oauth2_state.json').write_text(_json.dumps({
        'verifier': verifier, 'state': state, 'client_id': client_id
    }))

    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': os.environ.get("OAUTH_REDIRECT_URI", "https://your-domain.com/oauth/callback"),
        'scope': 'tweet.read tweet.write users.read offline.access media.write',
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"https://x.com/i/oauth2/authorize?{_up.urlencode(params)}")

def _html_response(body: str, title: str = "Flow — Auth") -> "Response":
    from fastapi.responses import HTMLResponse
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset=UTF-8><title>{title}</title>
<style>body{{font-family:system-ui;background:#0A0A0A;color:#ECECEC;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{max-width:480px;padding:2rem;border:1px solid rgba(255,255,255,0.08);border-radius:8px}}
h2{{margin-top:0}}code{{background:rgba(255,255,255,0.06);padding:2px 6px;border-radius:4px}}</style>
</head><body><div class="box">{body}</div></body></html>""")


# ============ HEALTH CHECK ============

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# ============ ROOT (serve index.html) ============
from fastapi.responses import FileResponse

@app.get("/")
async def root(flow_session: Optional[str] = Cookie(default=None)):
    """Serve app if authenticated, show login page if not."""
    # Check session cookie AND valid tokens exist
    if not verify_session_token(flow_session) or not has_valid_tokens():
        return FileResponse(STATIC_DIR / "login.html")
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5120)
