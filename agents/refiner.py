"""Refiner Agent - Transform raw ideas into polished thread drafts.

Takes a raw idea from the DB and produces a validated, Dan-voiced thread draft.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Add parent to path for db imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import get_idea, create_draft, update_idea

PROMPT_TEMPLATE_PATH = Path(__file__).parent / "refiner_prompt.md"


def load_prompt_template() -> str:
    """Load the refiner prompt template."""
    return PROMPT_TEMPLATE_PATH.read_text()


def build_prompt(idea: dict) -> str:
    """Build the full prompt with idea content injected."""
    template = load_prompt_template()
    
    # Build idea context
    idea_block = f"""## Raw Idea

**Content:**
{idea['content']}

**Link:** {idea.get('link') or 'None'}

**Tags:** {idea.get('tags') or 'None'}

**Image:** {idea.get('image_path') or 'None'}
"""
    
    return template + "\n\n" + idea_block


def parse_response(response: str) -> Optional[dict]:
    """Extract JSON from agent response."""
    # Try to find JSON block
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        json_str = response[start:end].strip()
    elif "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        json_str = response[start:end].strip()
    else:
        # Try to parse the whole response
        json_str = response.strip()
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to find any JSON object in the response
        import re
        match = re.search(r'\{[\s\S]*"thread"[\s\S]*\}', response)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def refine_idea(idea_id: int, model: str = None) -> Optional[int]:
    """Refine an idea into a draft thread.
    
    Args:
        idea_id: The ID of the idea to refine
        model: The model to use for refinement
        
    Returns:
        The draft ID if successful, None otherwise
    """
    if model is None:
        model = os.environ.get("REFINER_MODEL", "anthropic/claude-sonnet-4-20250514")

    # Load idea
    idea = get_idea(idea_id)
    if not idea:
        raise ValueError(f"Idea {idea_id} not found")
    
    # Build prompt
    prompt = build_prompt(idea)
    
    # Call model via OpenClaw gateway HTTP API
    try:
        import urllib.request
        from pathlib import Path

        GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
        GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
        if not GATEWAY_TOKEN:
            raise RuntimeError(
                "OPENCLAW_GATEWAY_TOKEN env var is required. "
                "Copy .env.example → .env and set your gateway token."
            )

        payload = json.dumps({
            "message": prompt,
            "agentId": "main",
            "stream": False
        }).encode()

        req = urllib.request.Request(
            f"{GATEWAY_URL}/api/agent",
            data=payload,
            headers={
                "Authorization": f"Bearer {GATEWAY_TOKEN}",
                "Content-Type": "application/json"
            }
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            response = data.get("reply") or data.get("message") or data.get("text") or str(data)

    except Exception as e:
        print(f"Error calling gateway: {e}", file=sys.stderr)
        return None
    
    # Parse response
    parsed = parse_response(response)
    if not parsed or "thread" not in parsed:
        print("Failed to parse response JSON", file=sys.stderr)
        print(f"Raw response: {response[:500]}...", file=sys.stderr)
        return None
    
    # Extract validation info
    validation = parsed.get("validation", {})
    grade = validation.get("grade", "C")
    hook_type = validation.get("hook_type", "unknown")
    
    # Inherit uploaded media from idea if present
    idea_image_path = idea.get("image_path")
    if idea_image_path:
        # Use uploaded image as draft media
        inherited_media_path = idea_image_path
        # Detect media_type from file extension
        ext = Path(idea_image_path).suffix.lower().lstrip(".")
        ext_to_type = {
            "jpg": "image", "jpeg": "image", "png": "image",
            "gif": "image", "webp": "image", "svg": "image",
            "mp4": "video", "mov": "video", "avi": "video", "webm": "video",
        }
        inherited_media_type = ext_to_type.get(ext, "image")
    else:
        # No uploaded image — check if thread requests media, mark pending
        inherited_media_path = None
        has_media = any(t.get("has_media", False) for t in parsed["thread"])
        inherited_media_type = "pending" if has_media else None

    # Save to DB
    draft_id = create_draft(
        idea_id=idea_id,
        thread_json=json.dumps(parsed["thread"]),
        validation_grade=grade,
        hook_type=hook_type,
        media_path=inherited_media_path,
        media_type=inherited_media_type,
    )
    
    # Update idea status
    update_idea(idea_id, status="drafted")
    
    return draft_id


def refine_idea_sync(idea_id: int) -> dict:
    """Synchronous wrapper that returns the full result for API use."""
    draft_id = refine_idea(idea_id)
    if draft_id is None:
        return {"success": False, "error": "Failed to refine idea"}
    
    from db import get_draft
    draft = get_draft(draft_id)
    return {
        "success": True,
        "draft_id": draft_id,
        "draft": draft
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Refine an idea into a thread draft")
    parser.add_argument("idea_id", type=int, help="ID of the idea to refine")
    parser.add_argument("--model", default=None, help="Model to use (default: REFINER_MODEL env var)")
    args = parser.parse_args()
    
    draft_id = refine_idea(args.idea_id, args.model)
    if draft_id:
        print(f"Created draft {draft_id}")
    else:
        print("Failed to create draft")
        sys.exit(1)
