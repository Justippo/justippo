from __future__ import annotations

import logging
from typing import Any

from app.services.rag_service import HindsightRAGService

logger = logging.getLogger(__name__)


class GraphAugmentedRAGService(HindsightRAGService):
    def __init__(
        self,
        base_url: str | None = None,
        bank_id: str | None = None,
        access_key: str | None = None,
        glossary_repo: object | None = None,
        client: Any | None = None,
        d1_client: Any | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            bank_id=bank_id,
            access_key=access_key,
            glossary_repo=glossary_repo,
            client=client,
        )
        self._d1 = d1_client

    async def query(
        self,
        q: str,
        top_k: int = 5,
        lang: str = "en",
    ) -> list[dict[str, Any]]:
        base_results = await super().query(q=q, top_k=top_k, lang=lang)
        if not self._d1 or not base_results:
            return base_results
        try:
            entity_docs = await self._fetch_related_via_entities(q)
            seen = {r.get("document_id") for r in base_results if r.get("document_id")}
            for doc in entity_docs:
                if doc.get("document_id") not in seen:
                    base_results.append(doc)
                    seen.add(doc.get("document_id", ""))
        except Exception as exc:
            logger.debug("Graph entity expansion failed (non-fatal): %s", exc)
        return base_results[:top_k]

    async def _fetch_related_via_entities(self, query: str) -> list[dict[str, Any]]:
        if not self._d1:
            return []
        query_lower = query.lower()
        tokens = [t.strip() for t in query_lower.split() if len(t.strip()) >= 4]
        if not tokens:
            return []
        all_doc_ids: set[str] = set()
        for token in tokens[:5]:
            result = await self._d1.query(
                "SELECT DISTINCT e.id, e.name, e.entity_type, de.doc_id "
                "FROM entities e "
                "JOIN document_entities de ON de.entity_id = e.id "
                "WHERE LOWER(e.name) LIKE ?",
                params=[f"%{token}%"],
            )
            if result:
                all_doc_ids.update(r["doc_id"] for r in result)
        if not all_doc_ids:
            return []
        placeholders = ", ".join("?" for _ in all_doc_ids)
        docs = await self._d1.query(
            f"SELECT id, filename as title FROM documents WHERE id IN ({placeholders})",
            params=list(all_doc_ids),
        )
        if not docs:
            return []
        return [
            {
                "document_id": d["id"],
                "text": "",
                "source_title": d.get("title", d["id"]),
                "source_url": "",
                "source_language": "en",
            }
            for d in docs
        ]
