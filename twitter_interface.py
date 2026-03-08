"""Thin wrapper around post.py and cardlib.py.

Uses bundled lib/ by default. Override with env vars if needed:
  POST_SCRIPT_PATH — absolute path to post.py
  TWITTER_MODULE_DIR — directory containing cardlib.py
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Default to bundled lib/ directory
_BUNDLED_LIB = Path(__file__).parent / "lib"


def get_post_script() -> Path:
    """Resolve the post.py path — bundled by default, env override available."""
    path = os.environ.get("POST_SCRIPT_PATH")
    if path:
        p = Path(path)
    else:
        p = _BUNDLED_LIB / "post.py"
    
    if not p.exists():
        raise RuntimeError(
            f"post.py not found at {p}. "
            "Check that lib/post.py exists or set POST_SCRIPT_PATH in .env."
        )
    return p


def get_twitter_module_dir() -> str:
    """Resolve the twitter module directory — bundled by default."""
    path = os.environ.get("TWITTER_MODULE_DIR")
    if path:
        return path
    return str(_BUNDLED_LIB)


def post_tweet(
    text: str,
    account: str = "personal",
    reply_to: str = None,
    media: str = None,
) -> str:
    """Post a tweet. Returns stdout from post.py.

    Args:
        text: Tweet text content
        account: Account identifier (default: "personal")
        reply_to: Tweet ID to reply to (optional)
        media: Absolute path to media file (optional)

    Returns:
        stdout output from post.py (contains tweet ID)
    """
    cmd = ["python3", str(get_post_script()), text, "--account", account]
    if reply_to:
        cmd += ["--reply-to", reply_to]
    if media:
        cmd += ["--media", media]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"post.py failed: {result.stderr}")
    return result.stdout


def verify_credentials(account: str = "personal") -> dict:
    """Verify X credentials via post.py verify_credentials().

    Args:
        account: Account identifier (default: "personal")

    Returns:
        Dict with ok, handle, id fields
    """
    post_dir = str(get_post_script().parent)
    if post_dir not in sys.path:
        sys.path.insert(0, post_dir)
    try:
        import post as twitter_post  # type: ignore
        return twitter_post.verify_credentials(account)
    except ImportError as e:
        raise RuntimeError(f"Could not import post.py from {post_dir}: {e}")
