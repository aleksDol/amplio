from asyncpg import Pool


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    owner_id BIGINT REFERENCES users(telegram_id),
    telegram_chat_id BIGINT UNIQUE,
    username TEXT,
    title TEXT,
    subscribers INT,
    min_free_match_subscribers INT,
    max_free_match_subscribers INT,
    last_subscribers_updated_at TIMESTAMP,
    niche TEXT,
    is_verified BOOL DEFAULT FALSE,
    bot_is_admin BOOL DEFAULT FALSE,
    rating FLOAT DEFAULT 5.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS subscribers INTEGER;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS min_free_match_subscribers INTEGER;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS max_free_match_subscribers INTEGER;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS last_subscribers_updated_at TIMESTAMP;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS completed_bundles_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS violations_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS cancelled_after_preview_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS publish_failures_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE channels
ADD COLUMN IF NOT EXISTS last_rating_update_at TIMESTAMP;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'channels_telegram_chat_id_key'
    ) THEN
        ALTER TABLE channels
        ADD CONSTRAINT channels_telegram_chat_id_key UNIQUE (telegram_chat_id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS bundles (
    id SERIAL PRIMARY KEY,
    creator_channel_id INT REFERENCES channels(id),
    niche TEXT,
    scheduled_at TIMESTAMP,
    slots INT,
    has_paid_slot BOOL DEFAULT FALSE,
    paid_slot_price INT,
    post_lifetime_hours INTEGER,
    preview_text TEXT,
    preview_generated_at TIMESTAMP,
    published_at TIMESTAMP,
    completed_at TIMESTAMP,
    last_checked_at TIMESTAMP,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS post_lifetime_hours INTEGER;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS paid_slot_price INTEGER;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS has_paid_slot BOOLEAN DEFAULT FALSE;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS preview_text TEXT;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS preview_generated_at TIMESTAMP;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS published_at TIMESTAMP;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;

ALTER TABLE bundles
ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS participants (
    id SERIAL PRIMARY KEY,
    bundle_id INT REFERENCES bundles(id),
    channel_id INT REFERENCES channels(id),
    type TEXT DEFAULT 'free',
    ad_text TEXT,
    confirmed BOOL DEFAULT FALSE,
    preview_confirmed BOOLEAN DEFAULT FALSE,
    preview_confirmed_at TIMESTAMP,
    preview_message_id BIGINT,
    preview_sent_at TIMESTAMP,
    removed_reason TEXT,
    removed_at TIMESTAMP,
    status TEXT DEFAULT 'active'
);

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS preview_confirmed BOOLEAN DEFAULT FALSE;

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS preview_confirmed_at TIMESTAMP;

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS preview_message_id BIGINT;

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS preview_sent_at TIMESTAMP;

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS removed_reason TEXT;

ALTER TABLE participants
ADD COLUMN IF NOT EXISTS removed_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    bundle_id INT REFERENCES bundles(id),
    channel_id INT REFERENCES channels(id),
    message_id BIGINT,
    status TEXT DEFAULT 'active',
    published_at TIMESTAMP,
    delete_at TIMESTAMP,
    error_text TEXT,
    deleted_at TIMESTAMP,
    checked_at TIMESTAMP
);

ALTER TABLE posts
ADD COLUMN IF NOT EXISTS error_text TEXT;

ALTER TABLE posts
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;

ALTER TABLE posts
ADD COLUMN IF NOT EXISTS checked_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    participant_id INT REFERENCES participants(id),
    amount INT,
    commission INT,
    net_amount INT,
    status TEXT DEFAULT 'pending',
    yukassa_id TEXT,
    payment_url TEXT,
    idempotence_key TEXT,
    external_status TEXT,
    payment_expires_at TIMESTAMP,
    paid_at TIMESTAMP,
    cancelled_at TIMESTAMP,
    raw_payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS commission INTEGER;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS net_amount INTEGER;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS payment_url TEXT;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS idempotence_key TEXT;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS external_status TEXT;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS payment_expires_at TIMESTAMP;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP;

ALTER TABLE payments
ADD COLUMN IF NOT EXISTS raw_payload JSONB;

CREATE TABLE IF NOT EXISTS user_settings (
    user_telegram_id BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
    bundle_notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bundle_notifications (
    id SERIAL PRIMARY KEY,
    bundle_id INTEGER NOT NULL REFERENCES bundles(id) ON DELETE CASCADE,
    user_telegram_id BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    channel_id INTEGER REFERENCES channels(id) ON DELETE SET NULL,
    notification_type TEXT NOT NULL,
    sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(bundle_id, user_telegram_id)
);

CREATE TABLE IF NOT EXISTS channel_violations (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    bundle_id INTEGER REFERENCES bundles(id) ON DELETE SET NULL,
    participant_id INTEGER REFERENCES participants(id) ON DELETE SET NULL,
    violation_type TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS channel_rating_history (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    bundle_id INTEGER REFERENCES bundles(id) ON DELETE SET NULL,
    delta NUMERIC(4,2) NOT NULL,
    reason TEXT NOT NULL,
    rating_before NUMERIC(4,2) NOT NULL,
    rating_after NUMERIC(4,2) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bundle_completion_bonus_applied (
    bundle_id INTEGER PRIMARY KEY REFERENCES bundles(id) ON DELETE CASCADE,
    applied_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""


async def create_tables(pool: Pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute(CREATE_TABLES_SQL)
