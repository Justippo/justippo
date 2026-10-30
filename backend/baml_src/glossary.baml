// ExtractGlossaryTerms — Extract legal/administrative terminology from a document
// text chunk, returning canonical forms in EN, DE, and FR with definitions.
//
// ADR-005: Domain Glossary & Terminology Management
// ADR-010: BAML as LLM generation interface (this is the first generation call)
//
// Validation strategy:
//   @check  — Soft (non-blocking): wraps field in Checked<T>, inspectable at runtime
//   @assert — Hard (blocking): raises BamlValidationError on failure
//   @@assert — Class-level hard check

class GlossaryTerm {
  // term_en: soft-checked non-empty (Checked[str] in Python — access via .value)
  // We use @check (not @assert) here because:
  //   1. source_lang may be "de" or "fr" where term_en can legitimately be empty
  //   2. The service layer enforces source_lang=="en" → term_en required
  //   3. @@assert below ensures at least ONE language term is non-empty
  term_en string @check(term_en_nonempty, {{ this|length > 0 }})

  term_de string
  term_fr string

  // definition: must be 10-500 characters (hard constraint)
  // Shorter = too vague; longer = likely hallucination or copied text
  definition string @assert(
    definition_length,
    {{ this|length >= 10 and this|length <= 500 }}
  )

  // Class-level: at least one of the three language terms must be non-empty.
  // Prevents the LLM from returning a GlossaryTerm with all-empty fields.
  @@assert(
    at_least_one_language_term,
    {{ this.term_en|length > 0 or this.term_de|length > 0 or this.term_fr|length > 0 }}
  )
}

function ExtractGlossaryTerms(text: string, source_lang: string) -> GlossaryTerm[] {
  client GlossaryClient
  prompt #"
You are a multilingual legal terminology extraction system for European Union document processing.

Given a text chunk from an EU legal or administrative document, extract domain-specific
terminology where a near-synonym could change the legal meaning.

Rules:
1. Identify terms that have specific legal/administrative meaning (e.g., "residence permit",
   not generic words like "document" or "person").
2. For each term, provide the canonical form in English (term_en), German (term_de),
   and French (term_fr).
3. Provide a concise legal definition in English (definition), between 10 and 500 characters.
4. If a term only exists in one or two languages, leave the others as empty strings.
5. Extract every qualifying term — do not skip terms that appear only once.
6. Do NOT hallucinate terms not present in the text.
7. If no legal terminology is found, return an empty list.
8. At least one of term_en, term_de, or term_fr must be non-empty for each extracted term.

Source language: {{ source_lang }}
Text language is expected to be one of: en, de, fr.

{{ ctx.output_format }}

Text:
---
{{ text }}
---
"#
}

// Generator configuration — generates baml_client/ with Pydantic types + sync/async clients
generator python {
  version "0.222.0"
  output_type "python/pydantic"
  output_dir "../baml_client"
  default_client_mode "sync"
}
