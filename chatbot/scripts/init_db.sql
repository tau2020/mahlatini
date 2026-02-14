-- ============================================
-- Mahlatini AI Chatbot — Database Initialisation
-- ============================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Conversations ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      VARCHAR(64) NOT NULL,
    source_page     TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    message_count   INTEGER DEFAULT 0,
    client_classification VARCHAR(32),
    primary_intent  VARCHAR(32),
    sentiment_avg   FLOAT,
    escalated       BOOLEAN DEFAULT FALSE,
    resolved_by_bot BOOLEAN DEFAULT FALSE,
    response_time_avg_ms INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_conversations_session ON conversations(session_id);
CREATE INDEX idx_conversations_started ON conversations(started_at);

-- ─── Messages ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    intent          VARCHAR(32),
    sentiment       VARCHAR(16),
    confidence      FLOAT,
    response_time_ms INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- ─── Leads ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS leads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID REFERENCES conversations(id),
    contact_name    TEXT,                              -- encrypted at app level
    contact_email   TEXT,                              -- encrypted at app level
    contact_phone   TEXT,                              -- encrypted at app level
    destination     VARCHAR(128),
    destination_region VARCHAR(128),
    travel_date_start DATE,
    travel_date_end   DATE,
    duration_days   INTEGER,
    pax_adults      INTEGER,
    pax_children    INTEGER,
    children_ages   INTEGER[],
    budget_min      DECIMAL(12,2),
    budget_max      DECIMAL(12,2),
    budget_currency VARCHAR(3) DEFAULT 'GBP',
    experience_types TEXT[],
    special_requests TEXT,
    lead_score      INTEGER DEFAULT 0 CHECK (lead_score BETWEEN 0 AND 100),
    classification  VARCHAR(32),
    booking_stage   VARCHAR(32) DEFAULT 'new',
    urgency         VARCHAR(16) DEFAULT 'low',
    jira_ticket_key VARCHAR(32),
    assigned_agent  VARCHAR(128),
    converted       BOOLEAN DEFAULT FALSE,
    conversion_date DATE,
    booking_value   DECIMAL(12,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_leads_conversation ON leads(conversation_id);
CREATE INDEX idx_leads_classification ON leads(classification);
CREATE INDEX idx_leads_score ON leads(lead_score);
CREATE INDEX idx_leads_created ON leads(created_at);
CREATE INDEX idx_leads_stage ON leads(booking_stage);

-- ─── Analytics Events ────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type      VARCHAR(64) NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    lead_id         UUID REFERENCES leads(id),
    payload         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_analytics_type ON analytics_events(event_type);
CREATE INDEX idx_analytics_created ON analytics_events(created_at);

-- ─── Destinations (dimension table) ──────────────────────
CREATE TABLE IF NOT EXISTS destinations (
    id      SERIAL PRIMARY KEY,
    name    VARCHAR(128) NOT NULL UNIQUE,
    country VARCHAR(128),
    region  VARCHAR(64) CHECK (region IN ('Africa', 'Indian Ocean', 'Indian Subcontinent', 'Middle East'))
);

-- Seed destinations from the Mahlatini website
INSERT INTO destinations (name, country, region) VALUES
    ('Botswana', 'Botswana', 'Africa'),
    ('Egypt', 'Egypt', 'Africa'),
    ('Kenya', 'Kenya', 'Africa'),
    ('Malawi', 'Malawi', 'Africa'),
    ('Morocco', 'Morocco', 'Africa'),
    ('Mozambique', 'Mozambique', 'Africa'),
    ('Namibia', 'Namibia', 'Africa'),
    ('Republic of Congo', 'Republic of Congo', 'Africa'),
    ('Rwanda', 'Rwanda', 'Africa'),
    ('South Africa', 'South Africa', 'Africa'),
    ('Tanzania', 'Tanzania', 'Africa'),
    ('Uganda', 'Uganda', 'Africa'),
    ('Zambia', 'Zambia', 'Africa'),
    ('Zimbabwe', 'Zimbabwe', 'Africa'),
    ('Madagascar', 'Madagascar', 'Indian Ocean'),
    ('Maldives', 'Maldives', 'Indian Ocean'),
    ('Mauritius', 'Mauritius', 'Indian Ocean'),
    ('Seychelles', 'Seychelles', 'Indian Ocean'),
    ('Bhutan', 'Bhutan', 'Indian Subcontinent'),
    ('India', 'India', 'Indian Subcontinent'),
    ('Nepal', 'Nepal', 'Indian Subcontinent'),
    ('Sri Lanka', 'Sri Lanka', 'Indian Subcontinent'),
    ('Oman', 'Oman', 'Middle East'),
    ('United Arab Emirates', 'United Arab Emirates', 'Middle East')
ON CONFLICT (name) DO NOTHING;

-- ─── Updated-at trigger ──────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_conversations_updated
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_leads_updated
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── Views for Power BI ──────────────────────────────────
CREATE OR REPLACE VIEW v_lead_pipeline AS
SELECT
    l.id,
    l.destination,
    l.lead_score,
    l.classification,
    l.booking_stage,
    l.urgency,
    l.budget_max,
    l.budget_currency,
    l.pax_adults + COALESCE(l.pax_children, 0) AS total_pax,
    l.converted,
    l.booking_value,
    l.assigned_agent,
    l.created_at,
    c.source_page,
    c.message_count,
    c.escalated,
    c.resolved_by_bot,
    c.response_time_avg_ms
FROM leads l
LEFT JOIN conversations c ON c.id = l.conversation_id;

CREATE OR REPLACE VIEW v_daily_metrics AS
SELECT
    DATE(created_at) AS metric_date,
    COUNT(*) AS total_leads,
    COUNT(*) FILTER (WHERE converted = TRUE) AS conversions,
    ROUND(100.0 * COUNT(*) FILTER (WHERE converted = TRUE) / NULLIF(COUNT(*), 0), 2) AS conversion_rate,
    AVG(lead_score) AS avg_lead_score,
    COUNT(*) FILTER (WHERE classification IN ('vip', 'high_value')) AS high_value_leads,
    SUM(budget_max) FILTER (WHERE booking_stage NOT IN ('closed_lost')) AS pipeline_value
FROM leads
GROUP BY DATE(created_at)
ORDER BY metric_date DESC;
