from __future__ import annotations

from app.services.chat_guidance import (
    GroundingConfig,
    build_grounding_verdict,
    enforce_citation_grounding,
    extract_known_doc_ids,
)

# ── extract_known_doc_ids (DRY helper) ─────────────────────────────────────


def test_extract_known_doc_ids_from_document_id_field() -> None:
    results = [{"document_id": "doc-1", "id": "ignored", "text": "foo"}]
    ids = extract_known_doc_ids(results)
    assert ids == {"doc-1"}


def test_extract_known_doc_ids_falls_back_to_id_field() -> None:
    results = [{"id": "doc-2", "text": "bar"}]
    ids = extract_known_doc_ids(results)
    assert ids == {"doc-2"}


def test_extract_known_doc_ids_prefers_document_id() -> None:
    results = [{"document_id": "doc-1", "id": "doc-2"}]
    ids = extract_known_doc_ids(results)
    assert ids == {"doc-1"}


def test_extract_known_doc_ids_skips_results_without_ids() -> None:
    results: list[dict] = [{"text": "no id here"}, {}, {"id": "doc-1"}]
    ids = extract_known_doc_ids(results)
    assert ids == {"doc-1"}


def test_extract_known_doc_ids_empty_input() -> None:
    assert extract_known_doc_ids([]) == set()


# ── build_grounding_verdict (integration helper) ───────────────────────────


def test_build_grounding_verdict_disabled_returns_pass() -> None:
    config = GroundingConfig(enabled=False)
    result = build_grounding_verdict(
        "Some claim here.",
        [{"id": "doc-1"}],
        config=config,
    )
    assert result["verdict"] == "pass"
    assert result["claims"] == []


def test_build_grounding_verdict_enabled_extracts_ids_and_validates() -> None:
    config = GroundingConfig(enabled=True)
    result = build_grounding_verdict(
        "See doc-1 for residence permit rules. Some other fact.",
        [{"id": "doc-1"}],
        config=config,
    )
    assert result["total_claims"] == 2
    assert result["claims"][0]["grounded"] is True
    assert result["claims"][0]["matched_doc_ids"] == ["doc-1"]
    assert result["claims"][1]["grounded"] is False


def test_build_grounding_verdict_passes_entity_mentions() -> None:
    config = GroundingConfig(enabled=True)
    result = build_grounding_verdict(
        "Germany requires a work permit.",
        [{"id": "doc-1"}],
        config=config,
        entity_mentions={"Germany"},
    )
    assert result["total_claims"] == 1
    assert result["claims"][0]["matched_entities"] == ["Germany"]
    # Also matched by doc-1 mention in text? No — claim text doesn't contain "doc-1"
    assert result["claims"][0]["matched_doc_ids"] == []


# ── enforce_citation_grounding ─────────────────────────────────────────────


def test_enforce_citation_grounding_disabled_returns_pass() -> None:
    result = enforce_citation_grounding(
        "Any text here",
        known_doc_ids={"1", "2"},
        config=GroundingConfig(enabled=False),
    )
    assert result == {"verdict": "pass", "claims": [], "ungrounded_count": 0, "total_claims": 0}


def test_enforce_citation_grounding_empty_text_returns_pass() -> None:
    result = enforce_citation_grounding(
        "", known_doc_ids={"1"}, config=GroundingConfig(enabled=True)
    )
    assert result["verdict"] == "pass"
    assert result["total_claims"] == 0


def test_enforce_citation_grounding_all_grounded() -> None:
    result = enforce_citation_grounding(
        "Doc-1 residence permit is needed. The document ID is doc-1.",
        known_doc_ids={"doc-1"},
        config=GroundingConfig(enabled=True),
    )
    assert result["verdict"] == "pass"
    assert result["total_claims"] == 2
    assert result["ungrounded_count"] == 0
    assert result["claims"][0]["grounded"] is True
    assert result["claims"][1]["grounded"] is True


def test_enforce_citation_grounding_partial_grounding() -> None:
    result = enforce_citation_grounding(
        "Doc-1 is mentioned here. But this fact has no source. And this one neither.",
        known_doc_ids={"doc-1"},
        config=GroundingConfig(enabled=True),
    )
    assert result["verdict"] == "partial"
    assert result["total_claims"] == 3
    assert result["ungrounded_count"] == 2


def test_enforce_citation_grounding_none_grounded() -> None:
    result = enforce_citation_grounding(
        "No sources match this output at all.",
        known_doc_ids={"doc-1"},
        config=GroundingConfig(enabled=True),
    )
    assert result["verdict"] == "fail"
    assert result["total_claims"] == 1
    assert result["ungrounded_count"] == 1


def test_enforce_citation_grounding_handles_no_known_ids() -> None:
    result = enforce_citation_grounding(
        "Some claim here.",
        known_doc_ids=None,
        config=GroundingConfig(enabled=True),
    )
    assert result["total_claims"] == 1
    assert result["claims"][0]["grounded"] is False


def test_enforce_citation_grounding_handles_no_entity_mentions() -> None:
    result = enforce_citation_grounding(
        "Germany requires a permit.",
        known_doc_ids={"doc-1"},
        entity_mentions=None,
        config=GroundingConfig(enabled=True),
    )
    assert result["total_claims"] == 1
    # No entities provided, but doc-1 is not in the text
    assert result["claims"][0]["grounded"] is False


def test_enforce_citation_grounding_matches_by_entity() -> None:
    result = enforce_citation_grounding(
        "Germany requires a work permit.",
        entity_mentions={"Germany"},
        config=GroundingConfig(enabled=True),
    )
    assert result["total_claims"] == 1
    assert result["claims"][0]["grounded"] is True
    assert result["claims"][0]["matched_entities"] == ["Germany"]


def test_enforce_citation_grounding_default_config_when_none() -> None:
    """When config is None, grounding is disabled by default."""
    result = enforce_citation_grounding("Some claim.", known_doc_ids={"doc-1"})
    assert result["verdict"] == "pass"
    assert result["total_claims"] == 0


def test_enforce_citation_grounding_case_insensitive_doc_match() -> None:
    result = enforce_citation_grounding(
        "See DOC-1 for details.",
        known_doc_ids={"doc-1"},
        config=GroundingConfig(enabled=True),
    )
    assert result["claims"][0]["grounded"] is True


def test_enforce_citation_grounding_multi_sentence_claim() -> None:
    result = enforce_citation_grounding(
        "First sentence references doc-1. Second sentence has no source. "
        "Third sentence also references doc-1.",
        known_doc_ids={"doc-1"},
        config=GroundingConfig(enabled=True),
    )
    assert result["total_claims"] == 3
    assert result["claims"][0]["grounded"] is True
    assert result["claims"][1]["grounded"] is False
    assert result["claims"][2]["grounded"] is True
    assert result["verdict"] == "partial"


def test_every_emitted_option_query_resolves_to_curated_guidance() -> None:
    """No clickable guidance button may be dead.

    Every option query emitted by build_empty_result_guidance — both from the
    _X_guidance handler functions AND from the inline marker-routed blocks inside
    build_empty_result_guidance itself — must route to curated guidance
    (reason == 'national_law'), never to the generic fallback or to a follow-up
    answer. This is the regression guard for the dispatch-table refactor: if a
    button is added without being wired into _GUIDANCE_INTENTS, this fails.

    The inline blocks are scanned from source because their option strings are not
    produced by any _X_guidance function (that gap is exactly what let a dead
    button slip through before this test covered it).
    """
    import inspect as _inspect
    import re as _re

    import app.services.chat_guidance as mod

    emitted = set()

    # 1) Options produced by the _X_guidance handler functions.
    for name in dir(mod):
        if name.endswith("_guidance"):
            func = getattr(mod, name)
            if callable(func):
                try:
                    payload = func()
                except TypeError:
                    continue
                for option in payload.get("options", []):
                    q = option.get("query")
                    if q:
                        emitted.add(q)

    # 2) Options emitted by the inline marker-routed blocks inside
    #    build_empty_result_guidance (e.g. the Germany/Spain work-permit answers).
    src = _re.sub(r"#.*", "", _inspect.getsource(mod.build_empty_result_guidance))
    for match in _re.findall(r'"query"\s*:\s*f?\s*"([^"]*)"', src):
        # Skip the two template options that interpolate the user query at runtime
        # (they are not clickable fixed strings).
        if "{query}" in match:
            continue
        emitted.add(match)

    dead = [
        (q, mod.build_empty_result_guidance(q)["reason"])
        for q in sorted(emitted)
        if mod.build_empty_result_guidance(q)["reason"] != "national_law"
    ]
    assert not dead, f"dead guidance buttons: {dead}"


def test_specific_questions_route_to_correct_handler() -> None:
    """Distinct topical questions must resolve to their SPECIFIC handler.

    Regression guard for the over-broad-matching bug: previously
    'What are the EU Blue Card requirements for Germany?', the skilled-worker permit
    question, and the qualification-recognition question all collapsed into the same
    generic non-EU job-offer answer. Each must return its dedicated handler's answer.
    """
    import app.services.chat_guidance as mod

    expectations = [
        ("What are the EU Blue Card requirements for Germany?", "_germany_blue_card_guidance"),
        (
            "What are the requirements for the German skilled worker residence permit?",
            "_germany_skilled_worker_guidance",
        ),
        (
            "How do I get my qualifications recognized for working in Germany?",
            "_germany_qualification_recognition_guidance",
        ),
        (
            "What are the requirements for germany's opportunity card?",
            "_germany_opportunity_card_guidance",
        ),
        (
            "What are the requirements for a self-employment residence permit in germany?",
            "_germany_self_employment_guidance",
        ),
        (
            "can i come to germany for vocational training as a non-eu citizen?",
            "_germany_vocational_training_guidance",
        ),
        ("What are the eu blue card requirements for spain?", "_spain_blue_card_guidance"),
        (
            "What are the requirements for the highly qualified professional permit in spain?",
            "_spain_highly_qualified_guidance",
        ),
        (
            "Which occupations are on Spain's shortage occupation list?",
            "_spain_shortage_occupations_guidance",
        ),
        ("What are the student visa requirements for spain?", "_spain_student_visa_guidance"),
        (
            "What are the requirements for spain's digital nomad visa?",
            "_spain_digital_nomad_guidance",
        ),
        (
            "What are the requirements for spain's entrepreneur visa?",
            "_spain_entrepreneur_visa_guidance",
        ),
        (
            "What are the requirements for spain's non-lucrative residence visa?",
            "_spain_non_lucrative_visa_guidance",
        ),
        (
            "I am an EU, EEA, or Swiss citizen and want to work in Germany.",
            "_germany_eu_citizen_guidance",
        ),
        (
            "I am an EU, EEA, or Swiss citizen and want to work in Spain.",
            "_spain_eu_registration_guidance",
        ),
        (
            "I am a non-EU citizen and already have a job offer in Germany.",
            "_germany_non_eu_job_offer_guidance",
        ),
        (
            "I am a non-EU citizen and do not yet have a job offer in Germany.",
            "_germany_non_eu_no_job_guidance",
        ),
        (
            "I am a non-EU citizen and already have a job offer in Spain.",
            "_spain_non_eu_job_offer_guidance",
        ),
        (
            "I am a non-EU citizen and do not yet have a job offer in Spain.",
            "_spain_non_eu_no_job_guidance",
        ),
    ]

    mismatched = []
    for query, expected_handler in expectations:
        result = mod.build_empty_result_guidance(query)
        expected_msg = getattr(mod, expected_handler)()["message"]
        if result["reason"] != "national_law" or result["message"] != expected_msg:
            mismatched.append((query, expected_handler, result["reason"]))
    assert not mismatched, f"specific question routed to wrong handler: {mismatched}"


def test_dispatch_is_specific_first() -> None:
    """Longer (more specific) triggers must win over broader ones.

    Guards against a broad substring swallowing a specific question.
    """
    import app.services.chat_guidance as mod

    # 'blue card germany' (broad) must NOT override the specific full-sentence question.
    r = mod.build_empty_result_guidance("What are the EU Blue Card requirements for Germany?")
    assert r["message"] == mod._germany_blue_card_guidance()["message"]


def test_non_de_es_and_corpus_questions_fall_through_to_rag() -> None:
    """Curated guidance must NOT answer questions outside its DE/ES scope.

    Anything about France, Italy, a generic EU directive, or the user's OWN uploaded
    documents must fall through to RAG (reason == 'no_verified_source'), never be
    silently answered by the curated graph. This is the 'works for any question about
    our corpus, not just Germany and Spain' guarantee: the curated layer is a
    supplement for general DE/ES law, and must yield to Hindsight for everything else.
    """
    import app.services.chat_guidance as mod

    must_fall_through = [
        "What are the immigration policies in France?",
        "How do I get a work visa for France?",
        "How do I register a birth in Italy?",
        "What are my rights under the EU Free Movement Directive 2004/38/EC?",
        "What is the difference between EU Blue Card and national visa?",
        "I need help with a French student visa",
        # Corpus-intent about DE/ES must reach the user's document, not curated:
        "Summarize the document I uploaded about German residence permits",
        "What does my uploaded Spanish visa PDF say?",
        "Extract the deadlines from the file I uploaded",
    ]
    wrongly_answered = [
        q
        for q in must_fall_through
        if mod.build_empty_result_guidance(q)["reason"] == "national_law"
    ]
    assert not wrongly_answered, (
        f"curated guidance wrongly answered non-scope query: {wrongly_answered}"
    )


def test_legal_thresholds_rendered_in_guidance() -> None:
    """Verify the curated guidance renders the CURRENT (2026) verified thresholds.

    Legal figures are served as authoritative fact (guidance bypasses RAG grounding),
    so they must match LEGAL_THRESHOLDS_2026. If a string drifts or a constant is
    changed without updating the rendered text, this fails. Run annually after the
    January threshold review.
    """
    from app.services.chat_guidance import (
        LEGAL_THRESHOLDS_2026,
        _eur,
        _germany_blue_card_guidance,
        _germany_eu_health_insurance_guidance,
        _germany_opportunity_card_guidance,
        _spain_blue_card_guidance,
        _spain_digital_nomad_guidance,
        _spain_non_lucrative_visa_guidance,
    )

    rendered = " ".join(
        fn()["message"]
        for fn in (
            _germany_blue_card_guidance,
            _germany_opportunity_card_guidance,
            _germany_eu_health_insurance_guidance,
            _spain_blue_card_guidance,
            _spain_digital_nomad_guidance,
            _spain_non_lucrative_visa_guidance,
        )
    )

    expected_substrings = [
        _eur(LEGAL_THRESHOLDS_2026.de_blue_card_general),
        _eur(LEGAL_THRESHOLDS_2026.de_blue_card_shortage),
        _eur(LEGAL_THRESHOLDS_2026.de_opportunity_card_blocked_pm),
        _eur(LEGAL_THRESHOLDS_2026.de_gkv_threshold),
        _eur(LEGAL_THRESHOLDS_2026.es_blue_card_general),
        _eur(LEGAL_THRESHOLDS_2026.es_blue_card_reduced),
        _eur(LEGAL_THRESHOLDS_2026.es_digital_nomad_main_pm),
        _eur(LEGAL_THRESHOLDS_2026.es_digital_nomad_dep1_pm),
        _eur(LEGAL_THRESHOLDS_2026.es_non_lucrative_main),
        _eur(LEGAL_THRESHOLDS_2026.es_non_lucrative_dep),
    ]
    missing = [s for s in expected_substrings if s not in rendered]
    assert not missing, f"threshold figures not rendered in guidance: {missing}"


def test_legal_thresholds_have_sources() -> None:
    """Every threshold field must cite its authoritative source (DRY/auditability)."""
    from app.services.chat_guidance import LEGAL_THRESHOLDS_2026

    assert LEGAL_THRESHOLDS_2026.sources, "sources dict must not be empty"
    assert all(LEGAL_THRESHOLDS_2026.sources.values()), "every source needs a URL"


def test_followup_options_return_distinct_answers_from_parent() -> None:
    """Clicking a follow-up label must give a NARROWER, distinct answer.

    This is the 'different responses for broad vs narrow questions' guarantee.
    Every curated handler emits follow-up option `query` strings; each must
    resolve (via the dispatch table) to an answer DIFFERENT from the parent
    handler's own answer. If a follow-up maps back to the parent (the bug seen
    in the live transcript — e.g. 'renew my student visa' returning the same
    generic blob as 'student visa requirements'), this fails.
    """
    import app.services.chat_guidance as mod

    regressions = []
    for name in dir(mod):
        if not name.endswith("_guidance") or name == "build_empty_result_guidance":
            continue
        factory = getattr(mod, name)
        if not callable(factory):
            continue
        try:
            parent = factory()
        except TypeError:
            # handlers that take args are skipped
            continue
        if not isinstance(parent, dict) or "options" not in parent:
            continue
        parent_msg = parent.get("message", "")
        for opt in parent.get("options", []):
            q = opt.get("query")
            if not q:
                continue
            child = mod.build_empty_result_guidance(q)
            if child.get("message") == parent_msg:
                regressions.append((name, q))
    assert not regressions, (
        "follow-up option returned the identical parent answer "
        f"(broad vs narrow collapse): {regressions}"
    )
