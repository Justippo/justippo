# Multilingual RAG Retrieval Evaluation Report

**Date:** 2026-06-22 23:51 UTC  
**Endpoint:** `http://localhost:8000`  
**Top-k:** 10  
**Timeout:** 90s per query  
**Runner:** `docs/testing/eval/run_eval.py`  

## Test Environment

| Parameter | Value |
|-----------|-------|
| Backend | EvidenceEU FastAPI (SSE streaming) |
| Endpoint | `http://localhost:8000/api/v1/search/?q=<query>&top_k=10` |
| Timeout | 90s |
| Top-k | 10 |
| Metrics | recall@k, MRR, NDCG@k |
| Dataset | 10 Q∟A pairs per language (cross-lingual) |

## Results Summary

| Language | Queries | recall@k | MRR | NDCG@k | Pass? |
|----------|---------|----------|-----|--------|-------|
| EN | 15 | 0.767 | 0.619 | 1.776 | ✅ |
| DE | 15 | 0.300 | 0.600 | 0.756 | ✅ |
| FR | 15 | 0.450 | 0.694 | 1.288 | ✅ |

## EN Detail

| # | Query | Retrieved (top-k) | recall@k | MRR | NDCG@k |
|---|-------|-------------------|----------|-----|--------|
| 1 | Directive 2004/38/EC free movement rights EU citiz | 32013R0610, 32004L0038, 32013R0610 | 1.000 | 0.500 | 0.987 |
| 2 | Non-EU family member reunification EU citizen anot | 32004L0038, 32004L0038-de, 32004L0038-de | 1.000 | 1.000 | 2.391 |
| 3 | Permanent residence right five years EU citizen an | 32004L0038-de, 32004L0038, 32003L0109 | 1.000 | 0.500 | 1.696 |
| 4 | Directive 2003/88/EC maximum weekly working hours  | 32003L0088, 32003L0088, 32003L0088 | 1.000 | 1.000 | 4.187 |
| 5 | 48 hour weekly working limit rest break workers EU | 32003L0088, 32003L0088, 32003L0088 | 1.000 | 1.000 | 4.228 |
| 6 | Directive 2005/36/EC recognition professional qual | 32013L0055, 32013L0055, 32005L0036 | 1.000 | 1.000 | 2.364 |
| 7 | Automatic recognition regulated professions profes | 32013L0055, 32013L0055, 32005L0036 | 1.000 | 1.000 | 2.786 |
| 8 | Collective redundancy consultation employer obliga | 32018L0957, 32008L0104, 32008L0104 | 0.000 | 0.000 | 0.000 |
| 9 | Regulation 883/2004 social security coordination c | 32019R1149, 32018R1724, 32009R0987 | 0.500 | 0.333 | 0.571 |
| 10 | A1 portable document social security EU regulation | 32019R1149, 32009R0987, 32019R1149 | 0.500 | 0.500 | 0.605 |
| 11 | Directive 2008/104/EC temporary agency work equal  | 32018L0957, 32018L0957, 32008L0104 | 1.000 | 0.333 | 1.762 |
| 12 | Posted workers equal treatment host member state d | 32014L0067, 32014L0067, 32014L0067 | 0.500 | 0.111 | 0.185 |
| 13 | Fixed-term work contracts anti-discrimination prot | 32008L0104, 32008L0104, 32018L0957 | 0.000 | 0.000 | 0.000 |
| 14 | Long-term resident third-country nationals residen | 32003L0109, 32003L0109, 32003L0109 | 1.000 | 1.000 | 2.609 |
| 15 | Regulation 987/2004 implementing social security c | 32009R0987, 32009R0987, 32018L0957 | 1.000 | 1.000 | 2.265 |

## DE Detail

| # | Query | Retrieved (top-k) | recall@k | MRR | NDCG@k |
|---|-------|-------------------|----------|-----|--------|
| 1 | Richtlinie 2004/38/EG Rechte Unionsbürger Freizügi | 32004L0038-de, 32018R1724-de, 32013R0610-de | 0.500 | 1.000 | 0.613 |
| 2 | Nicht-EU-Ehepartner mitbringen Freizügigkeit EU-Bü | 32018R1724-de, 32013L0055-de, 32013L0055-de | 0.000 | 0.000 | 0.000 |
| 3 | Daueraufenthaltsrecht fünf Jahre Unionsbürger Aufe | 32013L0055-de, 32019R1149-de, 32024R1689-de | 0.000 | 0.000 | 0.000 |
| 4 | Richtlinie 2003/88/EG wöchentliche Arbeitszeit 48  | 32003L0088-de, 32003L0088-de, 32018L0957-de | 0.500 | 1.000 | 1.482 |
| 5 | Arbeitszeitbegrenzung Ruhepause Arbeitnehmer EG Ri | 32008L0104-de, 32003L0088-de, 32018L0957-de | 0.500 | 0.500 | 0.799 |
| 6 | Richtlinie 2005/36/EG Anerkennung Berufsqualifikat | 32013L0055-de, 32013L0055-de, 32005L0036-de | 0.500 | 1.000 | 1.774 |
| 7 | Automatische Anerkennung regulierter Berufe Berufs | 32013L0055-de, 32013L0055-de, 32013L0055-de | 0.500 | 1.000 | 1.774 |
| 8 | Richtlinie 98/59/EG Massenentlassungen Konsultatio | 32018L0957-de, 32018L0957-de, 32014L0067-de | 0.000 | 0.000 | 0.000 |
| 9 | Verordnung 883/2004 soziale Sicherheit Grenzgänger | 32009R0987-de, 32009R0987-de, 32009R0987-de | 0.250 | 1.000 | 1.101 |
| 10 | Nachweis A1 soziale Sicherheit portable Urkunde EU | 32019R1149-de, 32003L0088-de, 32005L0036-de | 0.000 | 0.000 | 0.000 |
| 11 | Richtlinie 2008/104/EG Leiharbeitnehmer Gleichbeha | 32008L0104-de, 32018L0957-de, 32018L0957-de | 0.500 | 1.000 | 0.807 |
| 12 | Richtlinie 96/71/EG Entsendung Arbeitnehmer Gleich | 32014L0067-de, 32018L0957-de, 32018L0957-de | 0.250 | 0.500 | 0.682 |
| 13 | Richtlinie 1999/70/EG befristete Arbeitsverträge D | 32018L0957-de, 32003L0110-de, 32008L0104-de | 0.000 | 0.000 | 0.000 |
| 14 | Richtlinie 2003/109/EG Drittstaatsangehörige Dauer | 32003L0109-de, 32004L0114-de, 32003L0088-de | 0.500 | 1.000 | 0.788 |
| 15 | Verordnung 883/2004 Durchführung soziale Sicherhei | 32009R0987-de, 32009R0987-de, 32009R0987-de | 0.500 | 1.000 | 1.525 |

## FR Detail

| # | Query | Retrieved (top-k) | recall@k | MRR | NDCG@k |
|---|-------|-------------------|----------|-----|--------|
| 1 | Directive 2004/38/CE droits citoyens UE libre circ | 32004L0038-fr, 32013R0610-fr, 32013R0610-fr | 0.500 | 1.000 | 1.002 |
| 2 | Conjoint non-UE citoyen UE libre circulation autre | 32004L0038-fr, 32004L0038-fr, 32018R1724-fr | 0.500 | 1.000 | 1.566 |
| 3 | Séjour permanent cinq ans citoyens UE résidence | 32004L0038-fr, 32004L0038-fr, 32004L0038-fr | 0.500 | 1.000 | 2.786 |
| 4 | Directive 2003/88/CE durée maximale travail hebdom | 32003L0088-fr, 32003L0088-fr, 32018L0957-fr | 1.000 | 1.000 | 1.872 |
| 5 | Limite 48 heures travail hebdomadaire pause repos  | 32003L0088-fr, 32003L0088-fr, 32003L0088-fr | 0.500 | 1.000 | 2.178 |
| 6 | Directive 2005/36/CE reconnaissance qualifications | 32013L0055-fr, 32013L0055-fr, 32013L0055-fr | 0.500 | 1.000 | 1.774 |
| 7 | Reconnaissance automatique professions réglementée | 32013L0055-fr, 32005L0036-fr, 32013L0055-fr | 0.500 | 1.000 | 1.774 |
| 8 | Directive 98/59/CE licenciements collectifs procéd | 32014L0067-fr, 32018L0957-fr, 32022R0858-fr | 0.000 | 0.000 | 0.000 |
| 9 | Règlement 883/2004 coordination sécurité sociale t | 32018L0957-fr, 32009R0987-fr, 32009R0987-fr | 0.250 | 0.500 | 0.879 |
| 10 | Certificat portable A1 sécurité sociale réglementa | 32003L0109-fr, 32018R1724-fr, 32009R0987-fr | 0.250 | 0.333 | 0.481 |
| 11 | Directive 2008/104/CE travail intérimaire égalité  | 32018L0957-fr, 32018L0957-fr, 32018L0957-fr | 0.500 | 0.250 | 0.646 |
| 12 | Directive 96/71/CE détachement travailleurs égalit | 32014L0067-fr, 32014L0067-fr, 32018L0957-fr | 0.250 | 0.333 | 0.784 |
| 13 | Directive 1999/70/CE contrats durée déterminée pro | 32018L0957-fr, 32014L0067-fr, 32018L0957-fr | 0.000 | 0.000 | 0.000 |
| 14 | Directive 2003/109/CE résidents longue durée pays  | 32004L0114-fr, 32003L0109-fr, 32003L0109-fr | 0.500 | 1.000 | 1.774 |
| 15 | Règlement 987/2004 exécution sécurité sociale coor | 32009R0987-fr, 32018L0957-fr, 32009R0987-fr | 1.000 | 1.000 | 1.800 |

## Pass Criteria

- **recall@k ≥ 0.40** per language, OR **MRR ≥ 0.30**  
- All queries complete without timeout or HTTP error  
- No SSE stream parsing failures  

## Metric Definitions

- **recall@k** — fraction of relevant documents found in top-k results.  
- **MRR** (Mean Reciprocal Rank) — 1/rank of first relevant result.  
- **NDCG@k** (Normalized Discounted Cumulative Gain) — ranking quality with binary relevance.  

## Design Notes

- Retrieval-only evaluation (no LLM synthesis). Measures whether the correct document appears in top-k results.  
- Document IDs matched against Hindsight `document_id` field in SSE response events.  
- Fixtures use real EUR-Lex CELEX IDs matching documents seeded by `scripts/seed_documents.py`.  

## Raw Output

Full per-query results included in the detail tables above.

---

*This report is auto-generated by `run_eval.py` and fed directly into the Final D&T document testing section.*