"""Database helper functions for Personal X Pipeline."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "pipeline.db"


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database with schema."""
    schema_path = Path(__file__).parent / "schema.sql"
    with get_db() as conn:
        conn.executescript(schema_path.read_text())


# ============ IDEAS ============

def create_idea(
    content: str,
    link: Optional[str] = None,
    tags: Optional[str] = None,
    image_path: Optional[str] = None
) -> int:
    """Create a new idea. Returns the idea ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO ideas (content, link, tags, image_path)
               VALUES (?, ?, ?, ?)""",
            (content, link, tags, image_path)
        )
        return cursor.lastrowid


def get_idea(idea_id: int) -> Optional[dict]:
    """Get a single idea by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM ideas WHERE id = ?", (idea_id,)
        ).fetchone()
        return dict(row) if row else None


def get_ideas(status: Optional[str] = None) -> list[dict]:
    """List ideas, optionally filtered by status."""
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM ideas WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM ideas ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]


def update_idea(
    idea_id: int,
    content: Optional[str] = None,
    link: Optional[str] = None,
    tags: Optional[str] = None,
    image_path: Optional[str] = None,
    status: Optional[str] = None
) -> bool:
    """Update an idea. Returns True if updated."""
    updates = []
    params = []
    
    if content is not None:
        updates.append("content = ?")
        params.append(content)
    if link is not None:
        updates.append("link = ?")
        params.append(link)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)
    if image_path is not None:
        updates.append("image_path = ?")
        params.append(image_path)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    
    if not updates:
        return False
    
    updates.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(idea_id)
    
    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE ideas SET {', '.join(updates)} WHERE id = ?",
            params
        )
        return cursor.rowcount > 0


def delete_idea(idea_id: int) -> bool:
    """Delete an idea. Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        return cursor.rowcount > 0


def set_idea_status(idea_id: int, status: str) -> bool:
    """Set idea status (convenience function)."""
    return update_idea(idea_id, status=status)


# ============ DRAFTS ============

def create_draft(
    idea_id: int,
    thread_json: str,
    media_path: Optional[str] = None,
    media_type: Optional[str] = None,
    validation_grade: Optional[str] = None,
    hook_type: Optional[str] = None
) -> int:
    """Create a new draft. Returns the draft ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO drafts (idea_id, thread_json, media_path, media_type, validation_grade, hook_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (idea_id, thread_json, media_path, media_type, validation_grade, hook_type)
        )
        return cursor.lastrowid


def _parse_draft(row) -> dict:
    """Parse a draft row, converting thread_json to thread array."""
    import json
    d = dict(row)
    if d.get('thread_json'):
        try:
            d['thread'] = json.loads(d['thread_json'])
        except json.JSONDecodeError:
            d['thread'] = []
    else:
        d['thread'] = []
    return d


def get_draft(draft_id: int) -> Optional[dict]:
    """Get a single draft by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        return _parse_draft(row) if row else None


def get_drafts(status: Optional[str] = None) -> list[dict]:
    """List drafts, optionally filtered by status."""
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM drafts WHERE status = ? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM drafts ORDER BY created_at DESC"
            ).fetchall()
        return [_parse_draft(row) for row in rows]


def update_draft(
    draft_id: int,
    thread_json: Optional[str] = None,
    media_path: Optional[str] = None,
    media_type: Optional[str] = None,
    validation_grade: Optional[str] = None,
    hook_type: Optional[str] = None,
    status: Optional[str] = None,
    posted_at: Optional[str] = None,
    thread_url: Optional[str] = None,
    revision_notes: Optional[str] = None
) -> bool:
    """Update a draft. Returns True if updated."""
    updates = []
    params = []
    
    if thread_json is not None:
        updates.append("thread_json = ?")
        params.append(thread_json)
    if media_path is not None:
        updates.append("media_path = ?")
        params.append(media_path)
    if media_type is not None:
        updates.append("media_type = ?")
        params.append(media_type)
    if validation_grade is not None:
        updates.append("validation_grade = ?")
        params.append(validation_grade)
    if hook_type is not None:
        updates.append("hook_type = ?")
        params.append(hook_type)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if posted_at is not None:
        updates.append("posted_at = ?")
        params.append(posted_at)
    if thread_url is not None:
        updates.append("thread_url = ?")
        params.append(thread_url)
    if revision_notes is not None:
        updates.append("revision_notes = ?")
        params.append(revision_notes)
    
    if not updates:
        return False
    
    params.append(draft_id)
    
    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE drafts SET {', '.join(updates)} WHERE id = ?",
            params
        )
        return cursor.rowcount > 0


def set_draft_status(draft_id: int, status: str) -> bool:
    """Set draft status (convenience function)."""
    return update_draft(draft_id, status=status)


def mark_draft_posted(draft_id: int, thread_url: str) -> bool:
    """Mark a draft as posted with URL and timestamp."""
    return update_draft(
        draft_id,
        status='posted',
        posted_at=datetime.now().isoformat(),
        thread_url=thread_url
    )


def migrate_db():
    """Apply incremental schema migrations (safe to run repeatedly)."""
    with get_db() as conn:
        # Add revision_notes column if it doesn't exist
        cols = [row[1] for row in conn.execute("PRAGMA table_info(drafts)").fetchall()]
        if 'revision_notes' not in cols:
            conn.execute("ALTER TABLE drafts ADD COLUMN revision_notes TEXT")


# Initialize DB on import if it doesn't exist
if not DB_PATH.exists():
    init_db()

# Always run migrations (idempotent)
migrate_db()


# ============ ARCHIVAL ============

import json

ARCHIVE_DIR = Path(__file__).parent / "archive"


def archive_idea_original(idea_id: int) -> Optional[Path]:
    """Archive the original content of an idea before refinement. Returns archive path."""
    idea = get_idea(idea_id)
    if not idea:
        return None
    
    archive_path = ARCHIVE_DIR / "ideas" / f"idea-{idea_id}-original.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(archive_path, 'w') as f:
        json.dump({
            'id': idea_id,
            'original_content': idea.get('content'),
            'link': idea.get('link'),
            'tags': idea.get('tags'),
            'image_path': idea.get('image_path'),
            'archived_at': datetime.now().isoformat()
        }, f, indent=2)
    
    return archive_path


def archive_posted_draft(draft_id: int, thread_url: str) -> Optional[Path]:
    """Archive a posted draft with full context. Returns archive path."""
    draft = get_draft(draft_id)
    if not draft:
        return None
    
    idea = get_idea(draft['idea_id']) if draft.get('idea_id') else None
    
    archive_path = ARCHIVE_DIR / "posted" / f"draft-{draft_id}-posted.json"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(archive_path, 'w') as f:
        json.dump({
            'draft_id': draft_id,
            'idea_id': draft.get('idea_id'),
            'original_idea': idea.get('content') if idea else None,
            'thread_json': draft.get('thread_json'),
            'media_path': draft.get('media_path'),
            'validation_grade': draft.get('validation_grade'),
            'hook_type': draft.get('hook_type'),
            'thread_url': thread_url,
            'posted_at': datetime.now().isoformat()
        }, f, indent=2)
    
    return archive_path
