#!/usr/bin/env python3
"""
X/Twitter posting tool — Flow bundle.

Auth strategy:
  OAuth 2.0 Bearer (refresh on 401, fall back to OAuth 1.0a if configured)

Usage:
  python3 post.py "Your tweet text"
  python3 post.py "Tweet with image" --media /path/to/image.png
  python3 post.py "Preview" --dry-run
  python3 post.py "Debug" --verbose
"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# USER CONFIGURATION — Edit these for your setup
# ---------------------------------------------------------------------------

# Where your X API credentials are stored
SECRETS_DIR: Path = Path(os.environ.get('SECRETS_DIR', 
    str(Path(__file__).parent.parent / '.secrets')))

# Account configurations — edit 'personal' for your account
# Add more accounts if you manage multiple X handles
ACCOUNT_CONFIGS: Dict[str, Dict[str, str]] = {
    'personal': {
        'env_file':   os.environ.get('X_CREDENTIALS_FILE', 'x-oauth.env'),
        'key_prefix': os.environ.get('X_KEY_PREFIX', 'X'),
        'handle':     os.environ.get('X_HANDLE', 'yourhandle'),
    },
    # Add additional accounts here if needed:
    # 'business': {
    #     'env_file':   'business-x.env',
    #     'key_prefix': 'BUSINESS',
    #     'handle':     'yourbusiness',
    # },
}

# OAuth2 config — maps to your token files
_OAUTH2_CONFIG: Dict[str, Dict[str, str]] = {
    'personal': {
        'token_file':        os.environ.get('X_OAUTH2_TOKEN_FILE', 'x-oauth2.env'),
        'cred_file':         os.environ.get('X_OAUTH2_TOKEN_FILE', 'x-oauth2.env'),
        'access_key':        'ACCESS_TOKEN',
        'refresh_key':       'REFRESH_TOKEN',
        'client_id_key':     'CLIENT_ID',
        'client_secret_key': 'CLIENT_SECRET',
    },
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Retry delays (seconds) for 503 Service Unavailable on POST /2/tweets.
# X sheds load under stress — 503 does NOT count against monthly write quota.
RETRY_DELAYS: List[int] = [5, 15, 30]

_verbose: bool = False


def _log(msg: str) -> None:
    """Print only in verbose mode."""
    if _verbose:
        print(msg)


# ---------------------------------------------------------------------------
# Env file helpers
# ---------------------------------------------------------------------------

def _load_env_file(path: Path) -> Dict[str, str]:
    """Parse a key=value env file, skipping comments and blank lines."""
    raw: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            raw[k] = v
    return raw


def _save_env_file(path: Path, raw: Dict[str, str]) -> None:
    """Write a dict back to a key=value env file, preserving insertion order."""
    path.write_text('\n'.join(f'{k}={v}' for k, v in raw.items()) + '\n')


def load_env(account: str = 'personal') -> Dict[str, str]:
    """Load OAuth 1.0a credentials for the given account."""
    config = ACCOUNT_CONFIGS.get(account)
    if not config:
        print(f"ERROR: Unknown account '{account}'. Use: {', '.join(ACCOUNT_CONFIGS.keys())}")
        sys.exit(1)

    raw = _load_env_file(SECRETS_DIR / config['env_file'])
    prefix = config['key_prefix']

    # Support both prefixed keys (AUTMORI_CONSUMER_KEY) and plain keys (TWITTER_CONSUMER_KEY)
    env: Dict[str, str] = {
        'TWITTER_CONSUMER_API_KEY': (
            raw.get(f'{prefix}_CONSUMER_KEY', '')
            or raw.get('TWITTER_CONSUMER_API_KEY', '')
            or raw.get('TWITTER_CONSUMER_KEY', '')
        ),
        'TWITTER_CONSUMER_SECRET': (
            raw.get(f'{prefix}_CONSUMER_SECRET', '')
            or raw.get('TWITTER_CONSUMER_SECRET', '')
        ),
        'TWITTER_ACCESS_TOKEN': (
            raw.get(f'{prefix}_ACCESS_TOKEN', '')
            or raw.get('TWITTER_ACCESS_TOKEN', '')
        ),
        'TWITTER_ACCESS_SECRET': (
            raw.get(f'{prefix}_ACCESS_TOKEN_SECRET', '')
            or raw.get(f'{prefix}_ACCESS_SECRET', '')
            or raw.get('TWITTER_ACCESS_SECRET', '')
            or raw.get('TWITTER_ACCESS_TOKEN_SECRET', '')
        ),
        '_handle': config['handle'],
    }
    return env


# ---------------------------------------------------------------------------
# OAuth 1.0a
# ---------------------------------------------------------------------------

def oauth_sign(
    method: str,
    url: str,
    params: Dict[str, str],
    consumer_secret: str,
    token_secret: str,
) -> str:
    """Compute HMAC-SHA1 OAuth 1.0a signature."""
    param_string = '&'.join(
        f'{urllib.parse.quote(k, safe="")}={urllib.parse.quote(v, safe="")}'
        for k, v in sorted(params.items())
    )
    base_string = (
        f'{method}&'
        f'{urllib.parse.quote(url, safe="")}&'
        f'{urllib.parse.quote(param_string, safe="")}'
    )
    signing_key = (
        f'{urllib.parse.quote(consumer_secret, safe="")}&'
        f'{urllib.parse.quote(token_secret, safe="")}'
    )
    sig = hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1)
    return base64.b64encode(sig.digest()).decode()


def oauth_header(
    method: str,
    url: str,
    env: Dict[str, str],
    extra_params: Optional[Dict[str, str]] = None,
) -> str:
    """Build the Authorization header for an OAuth 1.0a request."""
    nonce = base64.b64encode(os.urandom(32)).decode().strip('=+/')[:32]
    params: Dict[str, str] = {
        'oauth_consumer_key':     env['TWITTER_CONSUMER_API_KEY'],
        'oauth_nonce':            nonce,
        'oauth_signature_method': 'HMAC-SHA1',
        'oauth_timestamp':        str(int(time.time())),
        'oauth_token':            env['TWITTER_ACCESS_TOKEN'],
        'oauth_version':          '1.0',
    }
    sign_params = {**params, **(extra_params or {})}
    params['oauth_signature'] = oauth_sign(
        method, url, sign_params,
        env['TWITTER_CONSUMER_SECRET'],
        env['TWITTER_ACCESS_SECRET'],
    )
    return 'OAuth ' + ', '.join(
        f'{k}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(params.items())
    )


# ---------------------------------------------------------------------------
# OAuth 2.0 helpers
# ---------------------------------------------------------------------------

def load_bearer_token(account: str) -> Optional[str]:
    """Return the stored OAuth2 Bearer token for an account, or None."""
    cfg = _OAUTH2_CONFIG.get(account)
    if not cfg:
        return None
    path = SECRETS_DIR / cfg['token_file']
    if not path.exists():
        return None
    raw = _load_env_file(path)
    return raw.get(cfg['access_key']) or None


def refresh_oauth2_token(account: str) -> Optional[str]:
    """Refresh the OAuth2 access token via the stored refresh token.

    On success: persists new tokens to disk and returns the new access token.
    On failure: prints a diagnostic to stderr and returns None.
    """
    cfg = _OAUTH2_CONFIG.get(account)
    if not cfg:
        print(f"  [oauth2] Unknown account: {account}", file=sys.stderr)
        return None

    token_path = SECRETS_DIR / cfg['token_file']
    if not token_path.exists():
        print(f"  [oauth2] Token file not found: {token_path}", file=sys.stderr)
        return None

    token_raw = _load_env_file(token_path)
    refresh_token = token_raw.get(cfg['refresh_key'])
    if not refresh_token:
        print(f"  [oauth2] No refresh token in {token_path.name}", file=sys.stderr)
        return None

    cred_path = SECRETS_DIR / cfg['cred_file']
    cred_raw = _load_env_file(cred_path) if cred_path.exists() else {}
    client_id = cred_raw.get(cfg['client_id_key'])
    client_secret = cred_raw.get(cfg['client_secret_key'])
    if not client_id or not client_secret:
        print(f"  [oauth2] Missing client credentials for {account}", file=sys.stderr)
        return None

    body = urllib.parse.urlencode({
        'grant_type':    'refresh_token',
        'refresh_token': refresh_token,
        'client_id':     client_id,
    }).encode()
    basic = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    req = urllib.request.Request(
        'https://api.x.com/2/oauth2/token',
        data=body,
        headers={
            'Authorization': f'Basic {basic}',
            'Content-Type':  'application/x-www-form-urlencoded',
        },
    )
    try:
        resp: Dict[str, str] = json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        print(f"  [oauth2] Refresh HTTP {e.code}: {e.read().decode(errors='replace')}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"  [oauth2] Refresh failed: {exc}", file=sys.stderr)
        return None

    new_access = resp.get('access_token')
    if not new_access:
        print(f"  [oauth2] No access_token in refresh response", file=sys.stderr)
        return None

    token_raw[cfg['access_key']] = new_access
    token_raw[cfg['refresh_key']] = resp.get('refresh_token', refresh_token)
    _save_env_file(token_path, token_raw)
    _log(f"  [oauth2] Token refreshed for {account}")
    return new_access


# ---------------------------------------------------------------------------
# Media upload v1.1 (OAuth 1.0a) — legacy, kept as fallback
# Prefer upload_media_v2() which uses OAuth 2.0 Bearer token
# ---------------------------------------------------------------------------

def upload_media(filepath: str, env: Dict[str, str]) -> str:
    """Upload media via chunked v1.1 endpoint. Returns media_id_string."""
    fpath = Path(filepath)
    file_size = fpath.stat().st_size

    ext = fpath.suffix.lower()
    media_types: Dict[str, str] = {
        '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.gif': 'image/gif', '.webp': 'image/webp',
        '.mp4': 'video/mp4', '.mov': 'video/quicktime',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    category = 'tweet_gif' if ext == '.gif' else ('tweet_video' if ext in ('.mp4', '.mov') else 'tweet_image')

    upload_url = 'https://upload.twitter.com/1.1/media/upload.json'

    # INIT
    init_params = {'command': 'INIT', 'total_bytes': str(file_size),
                   'media_type': media_type, 'media_category': category}
    auth = oauth_header('POST', upload_url, env, init_params)
    req = urllib.request.Request(upload_url, data=urllib.parse.urlencode(init_params).encode(),
                                 headers={'Authorization': auth, 'Content-Type': 'application/x-www-form-urlencoded'})
    resp: Dict = json.loads(urllib.request.urlopen(req).read())
    media_id: str = resp['media_id_string']
    _log(f"  INIT: media_id={media_id}")

    # APPEND (5 MB chunks)
    chunk_size = 5 * 1024 * 1024
    with open(fpath, 'rb') as f:
        segment = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            boundary = f'----Boundary{os.urandom(8).hex()}'
            body = b''
            for name, value in [('command', 'APPEND'), ('media_id', media_id), ('segment_index', str(segment))]:
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="media_data"\r\n\r\n'.encode()
            body += base64.b64encode(chunk) + b'\r\n'
            body += f'--{boundary}--\r\n'.encode()
            auth = oauth_header('POST', upload_url, env)
            req = urllib.request.Request(upload_url, data=body,
                                         headers={'Authorization': auth,
                                                  'Content-Type': f'multipart/form-data; boundary={boundary}'})
            urllib.request.urlopen(req)
            _log(f"  APPEND: segment {segment}")
            segment += 1

    # FINALIZE
    final_params = {'command': 'FINALIZE', 'media_id': media_id}
    auth = oauth_header('POST', upload_url, env, final_params)
    req = urllib.request.Request(upload_url, data=urllib.parse.urlencode(final_params).encode(),
                                 headers={'Authorization': auth, 'Content-Type': 'application/x-www-form-urlencoded'})
    resp = json.loads(urllib.request.urlopen(req).read())
    _log(f"  FINALIZE: {resp.get('processing_info', 'ready')}")

    # STATUS poll (video/gif only)
    while resp.get('processing_info', {}).get('state') in ('pending', 'in_progress'):
        wait: int = resp['processing_info'].get('check_after_secs', 2)
        _log(f"  Processing… waiting {wait}s")
        time.sleep(wait)
        status_params = {'command': 'STATUS', 'media_id': media_id}
        auth = oauth_header('GET', upload_url, env, status_params)
        status_url = f'{upload_url}?{urllib.parse.urlencode(status_params)}'
        req = urllib.request.Request(status_url, headers={'Authorization': auth})
        resp = json.loads(urllib.request.urlopen(req).read())

    if resp.get('processing_info', {}).get('state') == 'failed':
        print(f"ERROR: Media processing failed: {resp['processing_info']}", file=sys.stderr)
        sys.exit(1)

    _log(f"  Upload complete: {media_id}")
    return media_id


# ---------------------------------------------------------------------------
# Media upload v2 (OAuth 2.0 Bearer) — use this when bearer token available
# ---------------------------------------------------------------------------

def upload_media_v2(filepath: str, bearer_token: str) -> str:
    """Upload media via v2 API with OAuth 2.0 Bearer token. Returns media_id."""
    import base64
    fpath = Path(filepath)
    
    # Read and base64 encode
    with open(fpath, 'rb') as f:
        media_data = base64.b64encode(f.read()).decode()
    
    # Determine media category
    ext = fpath.suffix.lower()
    if ext in ('.mp4', '.mov'):
        category = 'tweet_video'
    elif ext == '.gif':
        category = 'tweet_gif'
    else:
        category = 'tweet_image'
    
    url = 'https://api.x.com/2/media/upload'
    payload = {
        'media': media_data,
        'media_category': category
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            'Authorization': f'Bearer {bearer_token}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )
    
    _log(f"  v2 upload: {fpath.name} ({category})")
    resp = json.loads(urllib.request.urlopen(req, timeout=120).read())
    media_id = resp['data']['id']
    _log(f"  v2 upload complete: {media_id}")
    return media_id


# ---------------------------------------------------------------------------
# Core post function
# ---------------------------------------------------------------------------

def post_tweet(
    text: str,
    media_ids: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    account: str = 'personal',
) -> Dict:
    """Post a tweet via v2 API with 503 retry/backoff.

    Auth routing:
      personal → OAuth 1.0a directly (tokens never expire)
      OAuth 2.0 Bearer → refresh on 401 → fall back to OAuth 1.0a
    """
    url = 'https://api.x.com/2/tweets'
    payload: Dict = {'text': text}
    if media_ids:
        payload['media'] = {'media_ids': media_ids}
    if reply_to:
        payload['reply'] = {'in_reply_to_tweet_id': reply_to}
    body = json.dumps(payload).encode()

    if env is None:
        env = load_env(account)

    def _request(auth_header: str) -> Dict:
        """Execute the POST with exponential backoff on 503."""
        delays = [0] + RETRY_DELAYS
        last_exc: Optional[Exception] = None
        for attempt, delay in enumerate(delays):
            if delay:
                print(f"  503 — retrying in {delay}s (attempt {attempt}/{len(RETRY_DELAYS)})…")
                time.sleep(delay)
            try:
                _log(f"  → POST {url}")
                req = urllib.request.Request(url, data=body, headers={
                    'Authorization': auth_header,
                    'Content-Type':  'application/json',
                })
                resp_bytes = urllib.request.urlopen(req).read()
                _log(f"  ← {resp_bytes.decode()}")
                result: Dict = json.loads(resp_bytes)
                return result
            except urllib.error.HTTPError as exc:
                if exc.code == 503 and attempt < len(RETRY_DELAYS):
                    last_exc = exc
                    continue
                raise
        raise last_exc or RuntimeError("All 503 retries exhausted")

    # All accounts: OAuth2 with refresh → OAuth1a fallback
    bearer = load_bearer_token(account)
    if bearer:
        try:
            return _request(f'Bearer {bearer}')
        except urllib.error.HTTPError as exc:
            if exc.code != 401:
                raise
            _log("  [oauth2] 401 — attempting token refresh…")
            new_token = refresh_oauth2_token(account)
            if new_token:
                try:
                    return _request(f'Bearer {new_token}')
                except urllib.error.HTTPError as exc2:
                    if exc2.code != 401:
                        raise
                    _log("  [oauth2] Still 401 after refresh — falling back to OAuth 1.0a")
            else:
                _log("  [oauth2] Refresh failed — falling back to OAuth 1.0a")

    return _request(oauth_header('POST', url, env))


# ---------------------------------------------------------------------------
# Credential verification (no post, no quota cost)
# ---------------------------------------------------------------------------

def verify_credentials(account: str = 'personal') -> Dict:
    """Verify X credentials by calling GET /2/users/me.

    Returns a dict with keys:
      ok    (bool)   — True if credentials are valid
      handle (str)  — @handle confirmed by X (or empty on failure)
      id    (str)   — numeric user ID (or empty on failure)
      error (str)   — human-readable error message (empty on success)

    Never posts anything. Does not count against monthly write quota.
    """
    url = 'https://api.x.com/2/users/me'
    env = load_env(account)

    def _get(auth_header: str) -> Dict:
        req = urllib.request.Request(url, headers={'Authorization': auth_header})
        _log(f"  → GET {url}")
        resp_bytes = urllib.request.urlopen(req, timeout=10).read()
        _log(f"  ← {resp_bytes.decode()}")
        return json.loads(resp_bytes)

    try:
        # Try OAuth 2.0 Bearer first, fall back to OAuth 1.0a
        bearer = load_bearer_token(account)
        if bearer:
            try:
                data = _get(f'Bearer {bearer}')
            except urllib.error.HTTPError as exc:
                if exc.code != 401:
                    raise
                _log("  [oauth2] 401 — attempting refresh before verify…")
                new_token = refresh_oauth2_token(account)
                if new_token:
                    data = _get(f'Bearer {new_token}')
                else:
                    _log("  [oauth2] Refresh failed — falling back to OAuth 1.0a")
                    data = _get(oauth_header('GET', url, env))
        else:
            data = _get(oauth_header('GET', url, env))

        user = data.get('data', {})
        return {
            'ok': True,
            'handle': user.get('username', ''),
            'id': user.get('id', ''),
            'error': '',
        }
    except urllib.error.HTTPError as exc:
        body = ''
        try:
            body = exc.read().decode()
        except Exception:
            pass
        return {'ok': False, 'handle': '', 'id': '', 'error': f'HTTP {exc.code}: {body[:200]}'}
    except Exception as exc:
        return {'ok': False, 'handle': '', 'id': '', 'error': str(exc)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    global _verbose

    parser = argparse.ArgumentParser(description='Post to X/Twitter')
    parser.add_argument('text', help='Tweet text')
    parser.add_argument('--media', action='append', metavar='PATH',
                        help='Media file to attach (repeat up to 4x)')
    parser.add_argument('--reply-to', metavar='TWEET_ID',
                        help='Tweet ID to reply to (for threads)')
    parser.add_argument('--account', default='personal', choices=list(ACCOUNT_CONFIGS.keys()),
                        help='Account to post from (default: personal)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without posting')
    parser.add_argument('--verbose', action='store_true',
                        help='Print full request/response details')
    args = parser.parse_args()

    _verbose = args.verbose

    if len(args.text) > 4000:
        print(f"ERROR: Tweet is {len(args.text)} chars (max 4000 with Premium)")
        sys.exit(1)
    if len(args.text) > 280:
        _log(f"NOTE: {len(args.text)} chars — remainder behind 'Show more'")

    env = load_env(args.account)
    handle = env.get('_handle', args.account)
    preview = args.text[:80] + ('…' if len(args.text) > 80 else '')
    print(f"@{handle}: {preview} ({len(args.text)} chars)")

    if args.dry_run:
        print("DRY RUN — not posting")
        return

    media_ids: List[str] = []
    if args.media:
        # Try v2 upload (OAuth 2.0) first, fall back to v1.1 (OAuth 1.0a)
        bearer = load_bearer_token(args.account)
        for path in args.media[:4]:
            print(f"Uploading {Path(path).name}…")
            if bearer:
                try:
                    media_ids.append(upload_media_v2(path, bearer))
                except Exception as e:
                    _log(f"  v2 upload failed ({e}), trying v1.1…")
                    media_ids.append(upload_media(path, env))
            else:
                media_ids.append(upload_media(path, env))

    resp = post_tweet(args.text, media_ids or None, args.reply_to, env, account=args.account)
    tweet_id = resp.get('data', {}).get('id', 'unknown')
    print(f"✅ https://x.com/{handle}/status/{tweet_id}")
    if _verbose:
        print(json.dumps(resp, indent=2))


if __name__ == '__main__':
    main()
