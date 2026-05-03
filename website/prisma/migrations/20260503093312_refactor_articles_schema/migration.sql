-- Drop existing articles table and recreate with new schema
-- This is a breaking change: old article data will be lost

DROP TABLE IF EXISTS articles CASCADE;

CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    code TEXT UNIQUE,
    title TEXT NOT NULL,
    lead TEXT,
    friendly_uri TEXT,
    link TEXT NOT NULL,
    published_date TEXT,
    last_modified_date TEXT,
    main_category TEXT,
    article_type TEXT,
    exclusive INTEGER NOT NULL DEFAULT 0,
    authors TEXT,
    picture_url TEXT,
    picture_caption TEXT,
    picture_credits TEXT,
    domain TEXT,
    uuid TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_articles_published_date ON articles (published_date);
CREATE INDEX idx_articles_domain ON articles (domain);

-- Create article_mp_matches junction table
CREATE TABLE article_mp_matches (
    id SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    mp_id INTEGER NOT NULL REFERENCES deputies(id) ON DELETE CASCADE,
    mp_name TEXT NOT NULL,
    mp_party TEXT NOT NULL,
    mention_count INTEGER NOT NULL,
    match_quality TEXT NOT NULL,
    article_source TEXT NOT NULL
);

CREATE UNIQUE INDEX article_mp_matches_article_id_mp_id_key ON article_mp_matches(article_id, mp_id);
CREATE INDEX idx_article_mp_matches_article_id ON article_mp_matches(article_id);
CREATE INDEX idx_article_mp_matches_mp_id ON article_mp_matches(mp_id);
