"""
Seed the evidence-eu-docs bank in a self-hosted Hindsight instance.

Usage:
    python3 backend/scripts/seed_hindsight.py --base-url <url> --auth-token <token>

The documents are excerpts of real EU regulations (Directive 2004/38/EC,
GDPR, Regulation 883/2004) with canonical EUR-Lex metadata so the RAG
service's provenance resolution works end-to-end.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BANK_ID = "evidence-eu-docs"

DOCUMENTS = [
    {
        "document_id": "eurlex-32004L0038-en",
        "content": (
            "Directive 2004/38/EC of the European Parliament and of the Council "
            "on the right of citizens of the Union and their family members to "
            "move and reside freely within the territory of the Member States. "
            "Article 6: Right of residence for up to three months. Union citizens "
            "have the right of residence in the territory of another Member State "
            "for a period of up to three months without any conditions or any "
            "formalities other than holding a valid identity card or passport. "
            "Article 7: Right of residence for more than three months. Every Union "
            "citizen has the right of residence for more than three months in another "
            "Member State provided they have sufficient resources and comprehensive "
            "sickness insurance. Family members who are not nationals of a Member State "
            "have the right of residence for more than three months if they accompany "
            "or join the Union citizen. Article 16: Permanent residence after five years "
            "of continuous legal residence. Union citizens who have resided legally in a "
            "host Member State for a continuous period of five years acquire the right of "
            "permanent residence. Article 8: Administrative formalities for residence "
            "permits. Residence cards are issued to family members who are not nationals "
            "of a Member State. The residence card is valid for five years from the date "
            "of issue and is renewable. Article 9: The right of residence of family "
            "members who are not nationals of a Member State shall not be affected by "
            "divorce, annulment of marriage, or termination of registered partnership."
        ),
        "metadata": {
            "document_id": "eurlex-32004L0038",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004L0038",
            "regulation_id": "Directive 2004/38/EC",
            "source_title": "Directive 2004/38/EC — Right to move and reside freely",
            "source_language": "en",
            "language": "en",
            "tags": ["residence", "mobility", "eu-citizens"],
        },
    },
    {
        "document_id": "eurlex-32004L0038-de",
        "content": (
            "Richtlinie 2004/38/EG des Europäischen Parlaments und des Rates über "
            "das Recht der Unionsbürger und ihrer Familienangehörigen, sich im "
            "Hoheitsgebiet der Mitgliedstaaten frei zu bewegen und aufzuhalten. "
            "Artikel 6: Aufenthaltsrecht bis zu drei Monaten. Unionsbürger haben "
            "das Recht, sich bis zu drei Monaten im Hoheitsgebiet eines anderen "
            "Mitgliedstaats aufzuhalten. Artikel 7: Aufenthaltsrecht für mehr als "
            "drei Monate. Jeder Unionsbürger hat das Aufenthaltsrecht für mehr als "
            "drei Monate in einem anderen Mitgliedstaat, wenn er über ausreichende "
            "Existenzmittel und einen umfassenden Krankenversicherungsschutz verfügt. "
            "Artikel 16: Daueraufenthaltsrecht nach fünf Jahren. Unionsbürger, die "
            "sich seit fünf Jahren ununterbrochen legal in einem Aufnahmemitgliedstaat "
            "aufhalten, erwerben das Daueraufenthaltsrecht. Artikel 8: "
            "Verwaltungsformalitäten für Aufenthaltskarten. Aufenthaltskarten werden "
            "an Familienangehörige ausgestellt, die nicht die Staatsangehörigkeit "
            "eines Mitgliedstaats besitzen. Die Aufenthaltskarte ist fünf Jahre lang "
            "gültig und verlängerbar."
        ),
        "metadata": {
            "document_id": "eurlex-32004L0038",
            "source_url": "https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32004L0038",
            "regulation_id": "Directive 2004/38/EC",
            "source_title": "Richtlinie 2004/38/EG — Freizügigkeit und Aufenthaltsrecht",
            "source_language": "de",
            "language": "de",
            "tags": ["aufenthalt", "mobilität", "unionsbürger"],
        },
    },
    {
        "document_id": "eurlex-32016R0679-en",
        "content": (
            "Regulation (EU) 2016/679 (General Data Protection Regulation, GDPR). "
            "Article 17: Right to erasure ('right to be forgotten'). The data subject "
            "shall have the right to obtain from the controller the erasure of personal "
            "data concerning him or her without undue delay and the controller shall have "
            "the obligation to erase personal data without undue delay. Article 6: "
            "Lawfulness of processing. Processing shall be lawful only if at least one of "
            "the legal bases applies: consent, contract, legal obligation, vital interests, "
            "public task, or legitimate interests. Article 15: Right of access by the data "
            "subject. The data subject shall have the right to obtain from the controller "
            "confirmation as to whether personal data concerning him or her are being "
            "processed and access to the data. Article 13: Information to be provided where "
            "personal data are collected from the data subject."
        ),
        "metadata": {
            "document_id": "eurlex-32016R0679",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679",
            "regulation_id": "Regulation (EU) 2016/679",
            "source_title": "GDPR — General Data Protection Regulation",
            "source_language": "en",
            "language": "en",
            "tags": ["data-protection", "privacy", "gdpr"],
        },
    },
    {
        "document_id": "eurlex-32004R0883-en",
        "content": (
            "Regulation (EC) No 883/2004 on the coordination of social security systems. "
            "Article 4: Equality of treatment. Persons to whom this Regulation applies "
            "shall enjoy the same benefits and be subject to the same obligations under "
            "the legislation of any Member State as the nationals thereof. Article 5: "
            "Export of benefits. Cash benefits acquired under the legislation of a Member "
            "State shall not be subject to any reduction, modification, suspension, "
            "withdrawal or confiscation merely because the beneficiary resides in a "
            "different Member State. Article 6: Waiver of residence clauses. The right "
            "to benefits in cash shall not be affected by the fact that the person "
            "resides in a Member State other than that in which the institution "
            "competent to grant the benefits is situated."
        ),
        "metadata": {
            "document_id": "eurlex-32004R0883",
            "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32004R0883",
            "regulation_id": "Regulation (EC) No 883/2004",
            "source_title": "Regulation 883/2004 — Social Security Coordination",
            "source_language": "en",
            "language": "en",
            "tags": ["social-security", "cross-border", "benefits"],
        },
    },
    {
        "document_id": "eurlex-32004L0038-fr",
        "content": (
            "Directive 2004/38/CE du Parlement européen et du Conseil relative au "
            "droit des citoyens de l'Union et des membres de leurs familles de se "
            "déplacer et de séjourner librement sur le territoire des États membres. "
            "Article 6: Droit de séjour jusqu'à trois mois. Les citoyens de l'Union "
            "ont le droit de séjourner sur le territoire d'un autre État membre "
            "pour une durée maximale de trois mois. Article 7: Droit de séjour de "
            "plus de trois mois. Tout citoyen de l'Union dispose du droit de séjour "
            "pour une durée supérieure à trois mois dans un autre État membre s'il "
            "dispose de ressources suffisantes et d'une assurance maladie complète. "
            "Article 16: Droit de séjour permanent après cinq années de résidence "
            "légale ininterrompue. Les citoyens de l'Union qui ont résidé légalement "
            "pendant cinq années consécutives dans l'État membre d'accueil acquièrent "
            "le droit de séjour permanent."
        ),
        "metadata": {
            "document_id": "eurlex-32004L0038",
            "source_url": "https://eur-lex.europa.eu/legal-content/FR/TXT/HTML/?uri=CELEX:32004L0038",
            "regulation_id": "Directive 2004/38/EC",
            "source_title": "Directive 2004/38/CE — Droit de séjour et de circulation",
            "source_language": "fr",
            "language": "fr",
            "tags": ["séjour", "mobilité", "citoyens-union"],
        },
    },
]


def seed(base_url: str, auth_token: str) -> None:
    """Seed the bank via the Hindsight REST API."""
    url = f"{base_url.rstrip('/')}/v1/default/banks/{BANK_ID}/memories"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
    }

    total_items = 0
    for doc in DOCUMENTS:
        # Split content into ~800 char chunks (matching _CHUNK_SIZE in rag_service.py)
        content = doc["content"]
        chunk_size = 800
        chunks = [
            content[i : i + chunk_size]
            for i in range(0, len(content), chunk_size)
        ]

        # metadata values must be strings — move tags to item-level
        metadata = {k: v for k, v in doc["metadata"].items() if k != "tags"}
        items = [
            {
                "content": chunk,
                "document_id": f"{doc['document_id']}-chunk-{i}",
                "metadata": metadata,
                "tags": doc["metadata"].get("tags", []),
            }
            for i, chunk in enumerate(chunks)
            if chunk.strip()
        ]

        if not items:
            continue

        payload = json.dumps({"items": items}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                status = resp.status
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")[:500]
            print(f"  ERROR ingesting {doc['document_id']}: HTTP {exc.code}: {err_body}", file=sys.stderr)
            continue
        except Exception as exc:
            print(f"  ERROR ingesting {doc['document_id']}: {exc}", file=sys.stderr)
            continue

        print(f"  {doc['document_id']}: {len(items)} chunks → HTTP {status}")
        total_items += len(items)

        # Small delay to avoid Mistral rate limits
        import time
        time.sleep(2)

    print(f"\nSeeded {total_items} chunks across {len(DOCUMENTS)} documents into bank '{BANK_ID}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Hindsight bank with EU regulation documents")
    parser.add_argument("--base-url", required=True, help="Hindsight API base URL")
    parser.add_argument("--auth-token", required=True, help="Hindsight auth bearer token")
    args = parser.parse_args()

    print(f"Seeding bank '{BANK_ID}' at {args.base_url}...")
    seed(args.base_url, args.auth_token)


if __name__ == "__main__":
    main()
