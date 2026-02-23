-- Shared Enterprise Schema
-- Database-backed shared-understanding for enterprise contexts

-- Core content tables
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    topic TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    source_skill TEXT,
    metadata JSON
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    text TEXT NOT NULL,
    status TEXT DEFAULT 'IN' CHECK (status IN ('IN', 'OUT', 'STALE')),
    source TEXT,
    source_hash TEXT,
    assumes JSON,           -- array of claim IDs
    depends_on JSON,        -- array of claim IDs
    superseded_by TEXT,     -- self-reference handled by app logic
    stale_reason TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_date DATE NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    related_ids JSON        -- array of related IDs (MRs, entries, etc.)
);

-- Conversations / context
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    topic TEXT NOT NULL,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'closed', 'archived'))
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT,         -- FK to threads.id handled by app logic
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL
);

-- External sources
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_type TEXT NOT NULL,  -- 'git', 'slack', 'jira', 'gdrive', etc.
    uri TEXT NOT NULL,
    last_synced TIMESTAMP,
    metadata JSON
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_entries_topic ON entries(topic);
CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(status);
CREATE INDEX IF NOT EXISTS idx_history_date ON history(event_date);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id);
