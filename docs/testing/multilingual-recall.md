# Multilingual RAG Recall — Seed Eval Set

> **Purpose:** Seed evaluation dataset for AdalFlow LLM-AutoDiff prompt optimization
> of the multilingual RAG recall pipeline. 20 queries across EN/DE/FR with
> ground-truth passages.
>
> **Created:** 2026-06-13
> **Used by:** `experiments/adalflow/rag_recall_opt.py`
> **Status:** Ready for optimization

## Dataset

| # | Language | Query | Ground-Truth Passage |
|---|----------|-------|---------------------|
| 1 | en | What are the residency requirements for EU long-term resident status? | Under Directive 2003/109/EC, third-country nationals who have resided legally in a Member State for five years may apply for EU long-term resident status. |
| 2 | en | How does GDPR define "personal data"? | Article 4(1) GDPR defines personal data as any information relating to an identified or identifiable natural person. |
| 3 | en | What is the right to be forgotten under EU law? | Article 17 GDPR establishes the right to erasure, commonly known as the right to be forgotten. Data subjects may request deletion of personal data where there is no overriding legitimate ground for processing. |
| 4 | en | When does the Digital Services Act apply to online platforms? | The Digital Services Act (Regulation 2022/2065) applies to intermediary services offered to recipients established or located in the EU, regardless of where the provider is established. It became fully applicable on 17 February 2024. |
| 5 | en | What are the penalties for non-compliance with the EU AI Act? | The EU AI Act (Regulation 2024/1689) establishes fines up to €35 million or 7% of annual worldwide turnover for prohibited AI practices, whichever is higher. |
| 6 | en | How does the EU define "consumer" in consumer rights legislation? | Directive 2011/83/EU defines a consumer as any natural person acting for purposes outside their trade, business, craft or profession. |
| 7 | en | What language rights do EU citizens have when interacting with EU institutions? | Regulation 1/1958 establishes that official documents may be sent to EU institutions in any of the 24 official languages, and the reply must be in the same language. |
| 8 | de | Welche Voraussetzungen gelten für die Anerkennung von Berufsqualifikationen in der EU? | Die Richtlinie 2005/36/EG regelt die Anerkennung von Berufsqualifikationen. Sie gilt für reglementierte Berufe und ermöglicht die teilweise oder vollständige Anerkennung von Qualifikationen, die in einem anderen Mitgliedstaat erworben wurden. |
| 9 | de | Was ist der Europäische Sozialfonds und welche Ziele verfolgt er? | Der Europäische Sozialfonds Plus (ESF+) ist das wichtigste Finanzierungsinstrument der EU zur Förderung der Beschäftigung, der sozialen Eingliederung und der allgemeinen und beruflichen Bildung in den Mitgliedstaaten. |
| 10 | de | Wie ist das Europäische Parlament bei Gesetzgebungsverfahren beteiligt? | Gemäß Artikel 294 AEUV (ordentliches Gesetzgebungsverfahren) ist das Europäische Parlament gleichberechtigt mit dem Rat an der Gesetzgebung beteiligt. Beide Organe müssen demselben Text zustimmen. |
| 11 | de | Welche Rechte haben Fluggäste bei Verspätungen nach EU-Recht? | Die Verordnung (EG) Nr. 261/2004 legt Ausgleichszahlungen für Fluggäste bei Annullierung oder großer Verspätung fest. Bei Verspätungen über drei Stunden haben Passagiere Anspruch auf Betreuungsleistungen und finanzielle Entschädigung. |
| 12 | de | Was besagt das EU-Verbot von Einwegplastik? | Die Richtlinie (EU) 2019/904 über Einwegkunststoffprodukte verbietet bestimmte Einwegprodukte wie Plastikbesteck, Teller, Strohhalme und Wattestäbchen ab Juli 2021. |
| 13 | de | Wie funktioniert das EU-Emissionshandelssystem? | Das EU-Emissionshandelssystem (EU-EHS) funktioniert nach dem Cap-and-Trade-Prinzip. Es setzt eine Obergrenze für Treibhausgasemissionen, und Unternehmen handeln mit Emissionszertifikaten innerhalb dieser Grenze. |
| 14 | fr | Qu'est-ce que le principe de reconnaissance mutuelle dans le marché intérieur européen? | Le principe de reconnaissance mutuelle, établi par l'arrêt Cassis de Dijon (CJCE, 1979), dispose que tout produit légalement fabriqué et commercialisé dans un État membre peut être vendu dans tous les autres États membres, sauf raisons impérieuses d'intérêt général. |
| 15 | fr | Comment la directive sur le droit d'auteur protège-t-elle les créateurs dans l'UE? | La directive (UE) 2019/790 sur le droit d'auteur dans le marché unique numérique modernise les règles de droit d'auteur. Elle introduit un nouveau droit voisin pour les éditeurs de presse et responsabilise les plateformes de partage de contenu. |
| 16 | fr | Quelles sont les conditions pour bénéficier de la protection temporaire dans l'UE? | La directive 2001/55/CE relative à la protection temporaire permet d'accorder une protection immédiate et collective en cas d'afflux massif de personnes déplacées. Elle a été activée pour la première fois en 2022 pour les personnes fuyant l'Ukraine. |
| 17 | fr | Qu'est-ce que le mécanisme de protection civile de l'Union européenne? | Le mécanisme de protection civile de l'Union (décision 1313/2013/UE) coordonne la réponse aux catastrophes naturelles et d'origine humaine. Il comprend le Centre de coordination de la réaction d'urgence (ERCC) et la réserve rescEU. |
| 18 | fr | Comment fonctionne le système d'information Schengen (SIS)? | Le système d'information Schengen (SIS) est une base de données partagée permettant aux autorités compétentes de chaque État membre de coopérer. Il contient des signalements de personnes et d'objets et est utilisé pour les contrôles aux frontières et les enquêtes policières. |
| 19 | fr | Quels sont les droits des passagers ferroviaires dans l'UE? | Le règlement (UE) 2021/782 sur les droits des passagers ferroviaires renforce les droits des voyageurs, notamment en cas de retard. Il prévoit des indemnisations, une assistance en gare, et des règles sur le transport des vélos. |
| 20 | fr | Comment l'UE lutte-t-elle contre le blanchiment d'argent? | La directive (UE) 2015/849 (4e directive anti-blanchiment) impose des obligations de vigilance aux entités financières, la déclaration des transactions suspectes, et la création de registres centraux des bénéficiaires effectifs. Elle est renforcée par la 5e et la 6e directive. |

## Field Descriptions

| Field | Description |
|-------|-------------|
| `#` | Sequential identifier |
| `language` | ISO 639-1 code (en, de, fr) |
| `query` | Natural-language query in the given language |
| `ground_truth_passage` | The passage that must be retrieved for a successful recall hit |

## Usage

```python
from experiments.adalflow.rag_recall_opt import load_eval_set
dataset = load_eval_set()  # Returns list of EvidenceEURecallData objects
```

## Notes

- Queries 1-7 (EN), 8-13 (DE), 14-20 (FR) — balanced across the 3 MVP languages
- Ground-truth passages are synthetic but based on real EU legislation
- This seed set targets domain-specific recall, not open-domain Q&A
- AdalFlow's `retriever_recall` evaluator checks if any ground-truth passage
  substring appears in the retrieved context
