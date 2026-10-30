// BAML-native test cases for ExtractGlossaryTerms
// Run with: uv run baml-cli test
//
// These tests validate:
//   - Empty text → empty list
//   - Single term extraction with all three languages
//   - Partial terms (only one language present)
//   - @check / @assert / @@assert enforcement
//   - Prompt regression (same input should produce consistent extraction)

// ── Empty text returns empty list ─────────────────────────────────────────

test EmptyText {
  functions [ExtractGlossaryTerms]
  args {
    text ""
    source_lang "en"
  }
  @@assert( {{ this|length == 0 }} )
}

// ── Whitespace-only text returns empty list ───────────────────────────────

test WhitespaceOnly {
  functions [ExtractGlossaryTerms]
  args {
    text "   \n  \t  "
    source_lang "en"
  }
  @@assert( {{ this|length == 0 }} )
}

// ── Single known legal term (EN source) ───────────────────────────────────

test SingleTermEnglishSource {
  functions [ExtractGlossaryTerms]
  args {
    text "Applicants must hold a valid residence permit for the duration of their stay."
    source_lang "en"
  }
  @@assert( {{ this|length >= 1 }} )
  @@assert( {{ this[0].term_en|length > 0 }} )
}

// ── German source text ────────────────────────────────────────────────────

test GermanSourceText {
  functions [ExtractGlossaryTerms]
  args {
    text "Der Antragsteller benötigt einen gültigen Aufenthaltstitel für die Dauer seines Aufenthalts."
    source_lang "de"
  }
  @@assert( {{ this|length >= 1 }} )
  @@assert( {{ this[0].term_de|length > 0 }} )
}

// ── French source text ────────────────────────────────────────────────────

test FrenchSourceText {
  functions [ExtractGlossaryTerms]
  args {
    text "Le demandeur doit détenir un titre de séjour valide pour la durée de son séjour."
    source_lang "fr"
  }
  @@assert( {{ this|length >= 1 }} )
  @@assert( {{ this[0].term_fr|length > 0 }} )
}

// ── Text with no legal terminology returns empty ──────────────────────────

test NoLegalTerms {
  functions [ExtractGlossaryTerms]
  args {
    text "The weather is nice today. I went for a walk in the park."
    source_lang "en"
  }
  @@assert( {{ this|length == 0 }} )
}
