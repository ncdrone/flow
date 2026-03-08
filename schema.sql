-- Personal X Pipeline Schema
-- SQLite database for ideas and drafts management

CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY,
  content TEXT NOT NULL,
  link TEXT,
  tags TEXT,
  image_path TEXT,
  status TEXT DEFAULT 'raw',  -- raw, refining, drafted, archived
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
  id INTEGER PRIMARY KEY,
  idea_id INTEGER REFERENCES ideas(id),
  thread_json TEXT NOT NULL,
  media_path TEXT,
  media_type TEXT,  -- uploaded, screenshot, graphic
  validation_grade TEXT,
  hook_type TEXT,
  status TEXT DEFAULT 'pending',  -- pending, posted, rejected, archived
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  posted_at TIMESTAMP,
  thread_url TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_ideas_status ON ideas(status);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_idea_id ON drafts(idea_id);
