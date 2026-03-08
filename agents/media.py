"""Media Agent - Generate screenshots and graphics for thread drafts.

Handles two modes:
1. Screenshot mode: Captures URLs via OpenClaw browser or FORGE API
2. Graphic mode: Generates stat/data cards via cardlib (if available)
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add parent to path for db imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import update_draft

MEDIA_OUTPUT_DIR = Path(__file__).parent.parent / "media" / "generated"

# OpenClaw gateway for browser screenshots
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN")

# Optional: FORGE API for screenshots (legacy, falls back to OpenClaw)
FORGE_API = os.environ.get("FORGE_API_URL")

# Optional: cardlib for graphic generation
_twitter_module_dir = os.environ.get("TWITTER_MODULE_DIR")
if _twitter_module_dir:
    sys.path.insert(0, _twitter_module_dir)

# Check if cardlib is available
try:
    from cardlib import card as cardlib_card
    CARDLIB_AVAILABLE = True
except ImportError:
    CARDLIB_AVAILABLE = False


def ensure_output_dir():
    """Ensure the output directory exists."""
    MEDIA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_filename(prefix: str = "media") -> str:
    """Generate a unique filename based on timestamp."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.png"


def screenshot_url(url: str, output_path: Optional[str] = None, 
                   width: int = 1200, height: int = 630) -> str:
    """Capture a screenshot of a URL.
    
    Tries FORGE API first (if configured), falls back to OpenClaw browser.
    
    Args:
        url: The URL to screenshot
        output_path: Where to save (auto-generated if None)
        width: Screenshot width (default 1200 for X cards)
        height: Screenshot height (default 630 for X cards)
        
    Returns:
        Path to the saved screenshot
    """
    ensure_output_dir()
    
    if output_path is None:
        output_path = str(MEDIA_OUTPUT_DIR / generate_filename("screenshot"))
    
    # Try FORGE API first if configured
    if FORGE_API:
        try:
            return _screenshot_via_forge(url, output_path, width, height)
        except Exception as e:
            print(f"FORGE failed, falling back to OpenClaw: {e}")
    
    # Fall back to OpenClaw browser
    return _screenshot_via_openclaw(url, output_path, width, height)


def _screenshot_via_forge(url: str, output_path: str, width: int, height: int) -> str:
    """Screenshot via FORGE API."""
    html = f'''<!DOCTYPE html>
<html>
<head><style>
body {{ margin: 0; padding: 0; overflow: hidden; }}
iframe {{ width: 100%; height: 100%; border: none; }}
</style></head>
<body><iframe src="{url}"></iframe></body>
</html>'''
    
    data = json.dumps({
        "html": html,
        "width": width,
        "height": height,
        "scale": 2
    }).encode()
    
    req = urllib.request.Request(
        FORGE_API,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(output_path, 'wb') as f:
            f.write(resp.read())
    return output_path


def _screenshot_via_openclaw(url: str, output_path: str, width: int, height: int) -> str:
    """Screenshot via OpenClaw browser tool."""
    if not GATEWAY_TOKEN:
        raise RuntimeError(
            "OPENCLAW_GATEWAY_TOKEN not set. "
            "Screenshots require OpenClaw gateway access."
        )
    
    data = json.dumps({
        "action": "screenshot",
        "url": url,
        "width": width,
        "height": height,
        "fullPage": False
    }).encode()
    
    req = urllib.request.Request(
        f"{GATEWAY_URL}/api/browser",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GATEWAY_TOKEN}"
        }
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
        
        if result.get("error"):
            raise RuntimeError(f"Browser error: {result['error']}")
        
        if "screenshot" in result:
            import base64
            img_data = base64.b64decode(result["screenshot"])
            with open(output_path, 'wb') as f:
                f.write(img_data)
            return output_path
        else:
            raise RuntimeError("No screenshot data in response")


def screenshot_html(html: str, output_path: Optional[str] = None,
                    width: int = 1200, height: int = 630) -> str:
    """Capture a screenshot of raw HTML via FORGE API.
    
    Args:
        html: The HTML content to render
        output_path: Where to save (auto-generated if None)
        width: Screenshot width
        height: Screenshot height
        
    Returns:
        Path to the saved screenshot
    """
    if not FORGE_API:
        raise RuntimeError("HTML screenshots require FORGE_API_URL to be configured")
    
    ensure_output_dir()
    
    if output_path is None:
        output_path = str(MEDIA_OUTPUT_DIR / generate_filename("html"))
    
    data = json.dumps({
        "html": html,
        "width": width,
        "height": height,
        "scale": 2
    }).encode()
    
    req = urllib.request.Request(
        FORGE_API,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(output_path, 'wb') as f:
            f.write(resp.read())
    return output_path


def generate_card(card_type: str, **kwargs) -> str:
    """Generate a graphic card using cardlib.
    
    Args:
        card_type: One of "stat", "conjunction", "trend", "compare", "quote"
        **kwargs: Arguments passed to cardlib.card()
        
    Returns:
        Path to the generated card image
    """
    if not CARDLIB_AVAILABLE:
        raise RuntimeError(
            "cardlib not available. Set TWITTER_MODULE_DIR in .env "
            "to the directory containing cardlib.py"
        )
    
    try:
        path = cardlib_card(card_type, **kwargs)
        return path
    except Exception as e:
        raise RuntimeError(f"cardlib error: {e}")


def detect_mode(prompt: str) -> Literal["screenshot", "card", "unknown"]:
    """Detect whether the prompt wants a screenshot or a card."""
    url_pattern = r'https?://[^\s]+'
    if re.search(url_pattern, prompt):
        return "screenshot"
    
    card_keywords = [
        r'\b\d+[x×%]\b',
        r'\bstat\b', r'\bcard\b', r'\bgraphic\b',
        r'\bquote\b', r'\btrend\b', r'\bcompare\b',
        r'\bmetric\b', r'\bdata\b'
    ]
    
    prompt_lower = prompt.lower()
    for kw in card_keywords:
        if re.search(kw, prompt_lower):
            return "card"
    
    return "unknown"


def parse_card_prompt(prompt: str) -> dict:
    """Parse a card generation prompt into cardlib arguments."""
    result = {"card_type": "stat", "kwargs": {}}
    
    prompt_lower = prompt.lower()
    if "trend" in prompt_lower:
        result["card_type"] = "trend"
    elif "compare" in prompt_lower:
        result["card_type"] = "compare"
    elif "quote" in prompt_lower:
        result["card_type"] = "quote"
    elif "conjunction" in prompt_lower:
        result["card_type"] = "conjunction"
    
    number_match = re.search(r'(\d+(?:\.\d+)?[x×%]?)', prompt)
    if number_match:
        result["kwargs"]["number"] = number_match.group(1)
    
    label_patterns = [
        r'showing\s+"([^"]+)"',
        r'showing\s+([^\.,]+)',
        r'label[:\s]+([^\.,]+)',
    ]
    for pattern in label_patterns:
        match = re.search(pattern, prompt_lower)
        if match:
            result["kwargs"]["label"] = match.group(1).strip()
            break
    
    return result


def generate_media(prompt: str, draft_id: Optional[int] = None) -> dict:
    """Generate media based on a natural language prompt.
    
    Args:
        prompt: Description of what media to generate
        draft_id: Optional draft ID to update with media path
        
    Returns:
        Dict with success status, path, and mode
    """
    mode = detect_mode(prompt)
    
    try:
        if mode == "screenshot":
            url_match = re.search(r'https?://[^\s]+', prompt)
            if not url_match:
                return {"success": False, "error": "No URL found in prompt"}
            
            url = url_match.group(0).rstrip('.,;:')
            path = screenshot_url(url)
            media_type = "screenshot"
            
        elif mode == "card":
            if not CARDLIB_AVAILABLE:
                return {
                    "success": False, 
                    "error": "Card generation not available. Set TWITTER_MODULE_DIR."
                }
            
            parsed = parse_card_prompt(prompt)
            path = generate_card(parsed["card_type"], **parsed["kwargs"])
            media_type = f"card_{parsed['card_type']}"
            
        else:
            return {
                "success": False, 
                "error": "Could not determine media type. Include a URL for screenshot or describe a stat/data card."
            }
        
        if draft_id is not None:
            update_draft(draft_id, media_path=path, media_type=media_type)
        
        return {
            "success": True,
            "path": path,
            "mode": mode,
            "media_type": media_type
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_media_for_draft(draft_id: int, tweet_index: int, prompt: str) -> dict:
    """Generate media for a specific tweet in a draft."""
    from db import get_draft
    
    draft = get_draft(draft_id)
    if not draft:
        return {"success": False, "error": f"Draft {draft_id} not found"}
    
    result = generate_media(prompt)
    
    if result["success"]:
        update_draft(draft_id, media_path=result["path"], media_type=result.get("media_type"))
    
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate media for X content")
    parser.add_argument("prompt", help="What media to generate")
    parser.add_argument("--draft-id", type=int, help="Draft ID to update")
    args = parser.parse_args()
    
    result = generate_media(args.prompt, args.draft_id)
    print(json.dumps(result, indent=2))
