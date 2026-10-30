CREATE TABLE IF NOT EXISTS document_clusters (
    doc_id      TEXT NOT NULL,
    level       TEXT NOT NULL CHECK (level IN ('fine', 'mid', 'broad')),
    cluster_id  INTEGER NOT NULL,
    cluster_label TEXT NOT NULL DEFAULT '',
    top_terms   TEXT NOT NULL DEFAULT '[]',
    topic_area  TEXT NOT NULL DEFAULT '',
    sil_score   REAL,
    PRIMARY KEY (doc_id, level),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_clusters_level
    ON document_clusters(level, cluster_id);

CREATE INDEX IF NOT EXISTS idx_document_clusters_topic
    ON document_clusters(topic_area);

CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT 'en'
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_name_type_lang
    ON entities(name, entity_type, language);

CREATE TABLE IF NOT EXISTS document_entities (
    doc_id      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    mentions    INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (doc_id, entity_id),
    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_document_entities_entity
    ON document_entities(entity_id);
