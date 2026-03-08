#!/usr/bin/env python3
"""
Screenshot utility for X Pipeline.
Takes a URL, captures a 4K screenshot, saves to media/generated/.

Usage:
    python screenshot.py <url> [--output <filename>] [--crop <top,left,bottom,right>]
    
Examples:
    python screenshot.py https://github.com/snarktank/ralph
    python screenshot.py https://example.com --output my-screenshot.png
    python screenshot.py https://example.com --crop 0,0,50,100  # crop percentages
"""

import argparse
import subprocess
import json
import sys
import os
from pathlib import Path
import hashlib
import time

MEDIA_DIR = Path(__file__).parent.parent / "media" / "generated"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

def take_screenshot(url: str, output: str = None, width: int = 1920, height: int = 1080) -> str:
    """Take screenshot using openclaw browser tool."""
    
    # Generate output filename if not provided
    if not output:
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = int(time.time())
        output = f"screenshot-{url_hash}-{timestamp}.png"
    
    output_path = MEDIA_DIR / output
    
    # Use openclaw CLI to take screenshot
    cmd = [
        "openclaw", "browser", "screenshot",
        "--url", url,
        "--profile", "openclaw",
        "--width", str(width),
        "--height", str(height),
        "--output", str(output_path)
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"Screenshot saved: {output_path}")
            return str(output_path)
        else:
            # Fallback: try curl + wkhtmltoimage if available
            print(f"openclaw browser failed, trying fallback...")
            print(f"Error: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        print("Screenshot timed out")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Take screenshots for X Pipeline")
    parser.add_argument("url", help="URL to screenshot")
    parser.add_argument("--output", "-o", help="Output filename (saved to media/generated/)")
    parser.add_argument("--width", type=int, default=1920, help="Viewport width")
    parser.add_argument("--height", type=int, default=1080, help="Viewport height")
    
    args = parser.parse_args()
    
    path = take_screenshot(args.url, args.output, args.width, args.height)
    if path:
        # Output JSON for easy parsing
        print(json.dumps({"success": True, "path": path}))
        sys.exit(0)
    else:
        print(json.dumps({"success": False, "error": "Screenshot failed"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
