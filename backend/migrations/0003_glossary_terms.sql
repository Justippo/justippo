-- 0003_glossary_terms.sql
-- Domain Glossary table (ADR-005, ADR-010)
-- Stores canonical EN/DE/FR legal & administrative terminology
-- extracted by BAML's ExtractGlossaryTerms typed-output call.
--
-- UNIQUE(term_en, term_de, term_fr) prevents duplicate triples.
-- Individual term-column indexes accelerate lookup in all three languages.

CREATE TABLE IF NOT EXISTS glossary_terms (
    id            TEXT PRIMARY KEY,       -- UUID v4
    term_en       TEXT NOT NULL,
    term_de       TEXT NOT NULL,
    term_fr       TEXT NOT NULL,
    definition    TEXT NOT NULL DEFAULT '',
    source_doc_id TEXT,                   -- FK → documents.id (soft reference)
    source_lang   TEXT,                   -- ISO 639-1 of the source document
    confidence    REAL NOT NULL DEFAULT 1.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Deduplication: same canonical triple = same concept
CREATE UNIQUE INDEX IF NOT EXISTS uq_glossary_terms_trilingual
    ON glossary_terms(term_en, term_de, term_fr);

-- Single-language lookup indexes (for search_terms / query expansion)
CREATE INDEX IF NOT EXISTS idx_glossary_terms_term_en
    ON glossary_terms(term_en);
CREATE INDEX IF NOT EXISTS idx_glossary_terms_term_de
    ON glossary_terms(term_de);
CREATE INDEX IF NOT EXISTS idx_glossary_terms_term_fr
    ON glossary_terms(term_fr);

-- Lookup by source document (for "show me terms from this doc")
CREATE INDEX IF NOT EXISTS idx_glossary_terms_source_doc_id
    ON glossary_terms(source_doc_id);
