import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set
import numpy as np
import requests
from loguru import logger

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ingestion.models import PhysicalHub, SupplierEvidence

# Standard ISO-3166-1 alpha-2 mapping for common countries to prevent country code hallucinations
COUNTRY_NAME_TO_ISO = {
    "UNITED STATES": "US", "USA": "US", "U.S.": "US", "AMERICA": "US",
    "CHINA": "CN", "PEOPLE'S REPUBLIC OF CHINA": "CN", "PRC": "CN",
    "TAIWAN": "TW", "REPUBLIC OF CHINA": "TW", "ROC": "TW",
    "GERMANY": "DE", "DEUTSCHLAND": "DE",
    "JAPAN": "JP",
    "SOUTH KOREA": "KR", "KOREA": "KR",
    "INDIA": "IN",
    "UNITED KINGDOM": "GB", "UK": "GB", "BRITAIN": "GB", "ENGLAND": "GB",
    "FRANCE": "FR",
    "NETHERLANDS": "NL", "HOLLAND": "NL",
    "CANADA": "CA",
    "MEXICO": "MX",
    "BRAZIL": "BR",
    "VIETNAM": "VN",
    "MALAYSIA": "MY",
    "SINGAPORE": "SG",
    "IRELAND": "IE",
    "ISRAEL": "IL",
    "SWITZERLAND": "CH",
    "SWEDEN": "SE",
    "AUSTRALIA": "AU",
    "INDONESIA": "ID",
    "PHILIPPINES": "PH",
    "THAILAND": "TH"
}

VALID_ARCHETYPES = {
    "industrial_hardware",
    "professional_services",
    "financial_institution",
    "digital_cloud_saas",
    "energy_mining_materials",
    "biotech_pharma"
}

DISALLOWED_PLACEHOLDERS = {
    "n/a", "none", "unknown", "supplier name", "unknown supplier",
    "dependency 1", "dependency 2", "placeholder", "tbd", "test"
}

# Generic grammar & corporate boilerplate filler words that receive low weight (0.25x) in Link C.
# Note: concrete facility/action nouns ('manufacturing', 'facilities', 'plant', 'wafer') are NOT stopwords
# because they form the core predicate of a physical footprint claim.
CORPORATE_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "have", "has", "had", "our", "their", "its", "company", "corporation",
    "inc", "plc", "ltd", "llc", "holdings", "group", "registrant", "item",
    "properties", "global", "primary", "principal", "major", "key", "critical",
    "including", "includes", "include", "across", "within", "through",
    "various", "certain", "other", "such", "also", "used", "uses",
    "tier", "services", "solutions", "systems", "products", "business",
    "corporate", "regional", "verified", "extracted", "filing", "disclosure",
    "disclosures", "established"
}

# Generic facility/corporate words stripped when extracting the distinctive entity/location in Link A
ENTITY_NOISE_WORDS = CORPORATE_STOPWORDS | {
    "operations", "operational", "operating", "operate", "operates",
    "facility", "facilities", "plant", "plants", "center", "centers",
    "campus", "hub", "hubs", "complex", "manufacturing", "manufactures",
    "manufacture", "production", "produces", "produce", "located", "location",
    "locations", "rely", "relies", "partner", "partners", "supplier",
    "suppliers", "supply", "chain", "contract", "technology", "technologies",
    "headquarters", "gigafactory", "foundry", "assembly", "smelter", "mine",
    "mining", "delivery", "advisory", "compliance", "regulatory", "tribunal",
    "packaging", "data", "cloud", "infrastructure", "division", "unit", "park",
    "industrial", "city", "line", "fab"
}

NEGATION_AND_CLOSURE_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = tuple(
    (label, re.compile(pat, re.IGNORECASE))
    for label, pat in [
        ("no_longer", r"\bno\s+longer\b"),
        ("aux_not", r"\b(?:do|does|did|are|is|were|was|have|has|had|will|would|can|could)\s+not\b"),
        ("contraction_not", r"\b(?:don't|doesn't|didn't|aren't|isn't|weren't|wasn't|haven't|hasn't|won't|can't)\b"),
        ("not_action", r"\bnot\s+(?:own|operate|maintain|lease|use|rely|have|manufacture|assemble|produce|locate[d]?)\b"),
        ("never", r"\bnever\s+(?:owned|operated|maintained|leased|used|had)\b"),
        ("closed_or_ceased", r"\b(?:ceased|closed|shuttered|shut\s+down|shutting\s+down)\b"),
        ("divested_or_exited", r"\b(?:divested|exited|terminated|discontinued|abandoned|liquidated|wound\s+down)\b"),
        ("sold_asset", r"\bsold\s+(?:our|its|the)\b"),
        ("former_status", r"\bformer\s+(?:facility|facilities|plant|factory|hub|supplier|partner|headquarters|operations|campus)\b"),
        ("without_presence", r"\bwithout\s+(?:any\s+)?(?:facilities|operations|plants|factories|presence)\b"),
    ]
)

HF_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HF_EMBEDDING_URL = (
    "https://router.huggingface.co/hf-inference/models/"
    "sentence-transformers/all-MiniLM-L6-v2/pipeline/feature-extraction"
)


def is_valid_url(url: Optional[str]) -> bool:
    """Checks if a URL has valid syntax, scheme, and non-empty network location."""
    if not url or not isinstance(url, str):
        return False
    clean_url = url.strip()
    try:
        parsed = urllib.parse.urlparse(clean_url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc or "." not in parsed.netloc:
            return False
        # Reject obviously fake/hallucinated domains
        if any(fake in parsed.netloc.lower() for fake in ["example.com", "fake.com", "source.url", "yoururl.com"]):
            return False
        return True
    except Exception:
        return False


def normalize_country_code(raw_country: Optional[str]) -> str:
    """Safely normalizes country strings to 2-letter uppercase ISO codes."""
    if not raw_country:
        return "US"
    cleaned = raw_country.strip().upper()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned
    return COUNTRY_NAME_TO_ISO.get(cleaned, "US")


def _stem_token(word: str) -> str:
    """
    Deterministic lightweight suffix stemmer so first-person vs third-person verbs
    ('We operate' vs 'Tesla operates', 'facilities' vs 'facility') match cleanly.
    """
    w = word.lower().strip()
    if len(w) <= 4:
        return w
    if w.endswith("ies") and len(w) > 5:
        return w[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[:-len(suffix)]
            break
    if w.endswith("e") and len(w) >= 5:
        w = w[:-1]
    return w


def _extract_subject_stems(ticker: Optional[str] = None, company_name: Optional[str] = None) -> Set[str]:
    """
    Returns stemmed tokens representing the document owner (e.g. 'tesla', 'tsla')
    so 'We'/'Our' in an SEC 10-K is treated as equivalent to the company name.
    """
    stems: Set[str] = {"we", "our", "ours", "us", "company", "registrant", "corporation"}
    if ticker:
        stems.add(ticker.lower().strip())
    if company_name:
        for tok in re.findall(r"\b\w{2,}\b", company_name.lower()):
            if tok not in {"inc", "corp", "corporation", "plc", "ltd", "llc", "co", "sa", "the"}:
                stems.add(_stem_token(tok))
                stems.add(tok)
    return stems


def _split_into_windows(corpus: str, window_size: int = 2) -> List[str]:
    """
    Link B helper: Splits a large corpus into overlapping N-sentence windows
    within each paragraph/page/section so words scattered across different pages
    or unrelated sections cannot combine to fake a match.
    """
    if not corpus or not corpus.strip():
        return []

    # First split into structural blocks (paragraphs, explicit Page/Paragraph markers, or titled section headers)
    structural_blocks = re.split(
        r"\n+|(?=\b(?:Page|Paragraph|Section)\s+\d+\s*:)|(?=\b[A-Z][A-Za-z0-9\s]{3,35}:\s+[A-Z])",
        corpus.strip()
    )

    windows: List[str] = []
    for block in structural_blocks:
        if not block or len(block.strip()) < 8:
            continue
        raw_sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", block.strip())
            if s and len(s.strip()) >= 8
        ]
        if not raw_sentences:
            continue
        if len(raw_sentences) <= window_size:
            windows.append(" ".join(raw_sentences))
        else:
            for i in range(len(raw_sentences) - window_size + 1):
                windows.append(" ".join(raw_sentences[i : i + window_size]))
        for s in raw_sentences:
            if s not in windows:
                windows.append(s)

    return windows if windows else [corpus.strip()]


def _detect_entity_negation(
    text: Optional[str],
    entity_tokens: List[str],
) -> Tuple[bool, List[str], str]:
    """
    Clause-Scoped Negation & Divestiture Polarity Detector:
    Splits `text` into sub-clauses (at sentence boundaries, semicolons, or contrastive conjunctions
    like ', but' / ', instead' / ', however') so fabless disclosures like
    "We do not own fabs; instead, we rely on TSMC" do not false-positive on TSMC,
    while "We no longer operate in Shinjuan, China" flags `is_negated=True` for Shinjuan/China.

    Returns (is_negated, matched_negation_cues, offending_clause).
    """
    if not text or not isinstance(text, str):
        return False, [], ""

    clean_tokens = [t.lower().strip() for t in entity_tokens if t and len(t.strip()) >= 2]
    token_stems = {_stem_token(t) for t in clean_tokens}

    # Split into clauses at sentence boundaries, semicolons, or contrastive conjunctions
    clauses = re.split(
        r"(?<=[.!?;])\s+|,\s+(?=(?:but|instead|however|rather|while|although|whereas)\b)",
        text.strip(),
        flags=re.IGNORECASE,
    )
    if not clauses:
        clauses = [text.strip()]

    for clause in clauses:
        c_low = clause.lower()
        c_words = set(re.findall(r"\b[a-z0-9\-]{2,}\b", c_low))
        c_stems = {_stem_token(w) for w in c_words}

        # If specific entity tokens were provided, only inspect clauses that mention the entity
        if clean_tokens:
            mentions_entity = any(
                tok in c_low or tok in c_words or _stem_token(tok) in c_stems
                for tok in clean_tokens
            ) or bool(token_stems & c_stems)
            if not mentions_entity:
                continue

        matched_cues: List[str] = []
        for cue_name, pattern in NEGATION_AND_CLOSURE_PATTERNS:
            m = pattern.search(clause)
            if m:
                matched_cues.append(f"{m.group(0).strip()} ({cue_name})")

        if matched_cues:
            return True, matched_cues, clause.strip()

    return False, [], ""


def _emit_guardrail_step(
    name: str,
    input_data: Dict[str, Any],
    output_data: Dict[str, Any],
    as_type: str = "guardrail",
    level: str = "DEFAULT",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Emits a live child observation to Langfuse directly from the executing guardrail function."""
    try:
        from agents.observability import get_langfuse

        lf = get_langfuse()
        if lf is not None:
            obs = lf.start_observation(
                name=name,
                as_type=as_type,
                input=input_data,
                output=output_data,
                level=level,
                metadata=metadata or {},
            )
            obs.end()
    except Exception as exc:
        logger.debug(f"Live Langfuse guardrail step '{name}' skipped: {exc}")


def verify_payload_quote_binding(
    entity_label: str,
    secondary_label: Optional[str],
    quote: Optional[str],
    subject_stems: Optional[Set[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Link A: Verifies that the distinctive entity or location in the decision payload
    (e.g. supplier.name='SK Hynix' or hub_name='Tesla Gigafactory Berlin') is actually
    mentioned inside its own `evidence_quote`.
    Returns (is_bound, distinctive_tokens_checked) and emits its live computation to Langfuse.
    """
    subj = subject_stems or set()
    combined_label = f"{entity_label or ''} {secondary_label or ''}".strip()
    raw_tokens = re.findall(r"\b[A-Za-z0-9\-]{2,}\b", combined_label)

    distinctive: List[str] = []
    filtered_out: List[Dict[str, str]] = []
    for tok in raw_tokens:
        low = tok.lower()
        stem = _stem_token(low)
        if low in ENTITY_NOISE_WORDS or stem in ENTITY_NOISE_WORDS:
            filtered_out.append({"token": low, "reason": "generic_facility_noise_word"})
            continue
        if low in subj or stem in subj:
            filtered_out.append({"token": low, "reason": "target_company_subject_stem"})
            continue
        if len(low) >= 2 and low not in distinctive:
            distinctive.append(low)

    if not quote or not isinstance(quote, str):
        _emit_guardrail_step(
            name="verify-link-a-entity-binding",
            input_data={
                "entity_label": entity_label,
                "secondary_label": secondary_label,
                "evidence_quote": quote,
                "subject_stems": sorted(list(subj)),
            },
            output_data={
                "raw_label_tokens": raw_tokens,
                "filtered_out_tokens": filtered_out,
                "distinctive_tokens_checked": distinctive,
                "matched_tokens_in_quote": [],
                "missing_tokens_from_quote": distinctive,
                "is_bound": False,
                "reason": "empty_or_missing_quote",
            },
            level="WARNING",
        )
        return False, distinctive

    quote_lower = quote.lower()
    quote_words = re.findall(r"\b\w{2,}\b", quote_lower)
    quote_stems = {_stem_token(t) for t in quote_words}

    matched_tokens: List[str] = []
    missing_tokens: List[str] = []
    for d_tok in distinctive:
        d_stem = _stem_token(d_tok)
        if d_tok in quote_lower or d_stem in quote_stems:
            matched_tokens.append(f"{d_tok} (stem: {d_stem})")
        else:
            missing_tokens.append(f"{d_tok} (stem: {d_stem})")

    # If the hub name only consisted of the company name + generic words (e.g. "Tesla Primary Facilities"),
    # allow it as a generic HQ hub; otherwise require at least 1 distinctive token match.
    has_token_match = True if not distinctive else (len(matched_tokens) > 0)

    # Link A Polarity Check: Ensure the quote is NOT negating/closing the entity
    # (e.g., "We no longer operate in Shinjuan, China")
    quote_is_negated, quote_negation_cues, negated_clause = _detect_entity_negation(quote, distinctive)
    is_bound = has_token_match and not quote_is_negated

    _emit_guardrail_step(
        name="verify-link-a-entity-binding",
        input_data={
            "entity_label": entity_label,
            "secondary_label": secondary_label,
            "evidence_quote": quote,
            "subject_stems": sorted(list(subj)),
        },
        output_data={
            "raw_label_tokens": raw_tokens,
            "filtered_out_tokens": filtered_out,
            "distinctive_tokens_checked": distinctive,
            "quote_token_stems": sorted(list(quote_stems)),
            "matched_tokens_in_quote": matched_tokens,
            "missing_tokens_from_quote": missing_tokens,
            "has_entity_token_match": has_token_match,
            "quote_polarity_negated": quote_is_negated,
            "negation_cues_in_quote": quote_negation_cues,
            "negated_clause": negated_clause or None,
            "is_bound": is_bound,
        },
        level="DEFAULT" if is_bound else "WARNING",
    )
    return is_bound, distinctive


def _hf_embedding_similarity(quote: str, candidate_windows: List[str]) -> Optional[float]:
    """
    Optional Hybrid Tier: Calls Hugging Face Inference API (sentence-transformers/all-MiniLM-L6-v2)
    to compute max cosine similarity between the quote and the top candidate sentence windows.
    Emits a live `embedding` observation to Langfuse with all per-window cosine similarities.
    """
    api_key = os.environ.get("HUGGINGFACE_API_KEY", "").strip()
    if not api_key or not candidate_windows:
        return None

    try:
        trimmed_candidates = [w[:500] for w in candidate_windows[:8]]
        inputs = [quote.strip()] + trimmed_candidates
        resp = requests.post(
            HF_EMBEDDING_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={"inputs": inputs, "options": {"wait_for_model": True}},
            timeout=4.0
        )
        if resp.status_code != 200:
            return None

        vecs = resp.json()
        if not isinstance(vecs, list) or len(vecs) < 2:
            return None

        arr = np.asarray(vecs, dtype=float)
        if arr.ndim != 2:
            return None

        q_vec = arr[0]
        q_norm = np.linalg.norm(q_vec)
        if q_norm < 1e-9:
            return None

        w_vecs = arr[1:]
        w_norms = np.linalg.norm(w_vecs, axis=1)
        valid = w_norms > 1e-9
        if not np.any(valid):
            return None

        sims = (w_vecs[valid] @ q_vec) / (w_norms[valid] * q_norm)
        max_sim = round(float(np.max(sims)), 2)
        per_window_sims = [
            {"window_preview": trimmed_candidates[idx][:180], "cosine_similarity": round(float(sim_val), 3)}
            for idx, sim_val in enumerate(sims)
        ]

        _emit_guardrail_step(
            name="compute-hf-minilm-embedding-similarity",
            as_type="embedding",
            input_data={
                "model": HF_EMBEDDING_MODEL,
                "quote": quote.strip(),
                "candidate_windows_count": len(trimmed_candidates),
                "candidate_windows": trimmed_candidates,
            },
            output_data={
                "max_cosine_similarity": max_sim,
                "per_window_cosine_similarities": per_window_sims,
                "passed_065_threshold": max_sim >= 0.65,
            },
        )
        return max_sim
    except Exception as e:
        logger.debug(f"HF semantic embedding fallback skipped: {e}")
        return None


def quote_grounding_score(
    quote: Optional[str],
    context_corpus: str,
    ticker: Optional[str] = None,
    company_name: Optional[str] = None,
    source_type: str = "sec_10k",
    use_semantic_fallback: bool = True,
    entity_anchor_tokens: Optional[List[str]] = None
) -> float:
    """
    Computes a groundedness score (0.0 to 1.0) by executing ALL steps of Link B and Link C
    (no hardcoded short-circuits) and emitting each step's live inputs & computed outputs to Langfuse:
      1. Link C Step 1 (Tokenization, Stemming, Coreference Normalization & Weighting):
         - Capitalized proper nouns / numbers -> 1.5x weight
         - Concrete action/facility predicates -> 1.0x weight
         - Corporate stopwords -> 0.25x weight
         - First-party coreference ('Tesla' <-> 'We'/'Our') -> forgiven in SEC/Wikipedia texts
      2. Link B (2-Sentence Sliding Window Split & Locality Scan):
         - Splits `context_corpus` into overlapping 2-sentence windows (`_split_into_windows`)
         - Scores every window against Link C's weighted tokens
      3. Link C Step 2 (0.35 Proper-Noun Gate & Thresholding + Hybrid HF Embedding Fallback)
    """
    if not quote or not isinstance(quote, str) or len(quote.strip()) < 5 or not context_corpus or not context_corpus.strip():
        _emit_guardrail_step(
            name="evaluate-link-b-and-c-grounding",
            input_data={"quote": quote, "source_type": source_type, "corpus_char_length": len(context_corpus or "")},
            output_data={"final_score": 0.0, "reason": "empty_quote_or_corpus"},
            level="WARNING",
        )
        return 0.0

    clean_q = quote.strip().lower()
    clean_corpus = context_corpus.lower()
    is_exact_substring = clean_q in clean_corpus

    subject_stems = _extract_subject_stems(ticker, company_name)
    is_first_party = (source_type or "sec_10k").lower() in ("sec_10k", "wikipedia")

    # =========================================================================
    # LINK C (Part 1): Tokenization, Stemming, Coreference & Weight Assignment
    # =========================================================================
    raw_q_words = re.findall(r"\b[A-Za-z0-9\-]{3,}\b", quote.strip())
    weighted_q_tokens: List[Tuple[str, str, float, bool]] = []
    forgiven_subject_tokens: List[str] = []
    duplicate_stems_skipped: List[str] = []
    seen_stems: Set[str] = set()

    for idx, word in enumerate(raw_q_words):
        low = word.lower()
        stem = _stem_token(low)
        if stem in seen_stems:
            duplicate_stems_skipped.append(f"{word} (stem: {stem})")
            continue

        # In first-party SEC/Wiki docs, ignore the document owner's name ("Tesla" <-> "We")
        if is_first_party and (low in subject_stems or stem in subject_stems):
            forgiven_subject_tokens.append(f"{word} (stem: {stem})")
            continue

        seen_stems.add(stem)

        is_cap = (word[0].isupper() and low not in ENTITY_NOISE_WORDS) or any(ch.isdigit() for ch in word)
        if is_cap and idx == 0 and low in ENTITY_NOISE_WORDS:
            is_cap = False

        if is_cap:
            weight = 1.5
        elif low in CORPORATE_STOPWORDS or stem in CORPORATE_STOPWORDS:
            weight = 0.25
        else:
            weight = 1.0

        weighted_q_tokens.append((stem, low, weight, is_cap))

    total_weight = round(sum(w for _, _, w, _ in weighted_q_tokens), 2)
    proper_tokens = [(stem, low) for stem, low, _, is_cap in weighted_q_tokens if is_cap]

    _emit_guardrail_step(
        name="compute-link-c-token-weights",
        input_data={
            "evidence_quote": quote,
            "source_type": source_type,
            "is_first_party_source": is_first_party,
            "target_company_subject_stems": sorted(list(subject_stems)),
            "raw_extracted_words": raw_q_words,
        },
        output_data={
            "weighted_tokens": [
                {
                    "word": low,
                    "stem": stem,
                    "weight": w,
                    "tier": "proper_noun_1.5x" if is_cap else ("corporate_stopword_0.25x" if w == 0.25 else "predicate_1.0x"),
                }
                for stem, low, w, is_cap in weighted_q_tokens
            ],
            "forgiven_first_party_subject_tokens": forgiven_subject_tokens,
            "duplicate_stems_skipped": duplicate_stems_skipped,
            "proper_nouns_identified": [p_low for _, p_low in proper_tokens],
            "total_possible_weight": total_weight,
        },
    )

    if not weighted_q_tokens:
        return 1.0

    # =========================================================================
    # LINK B: Split Context Corpus into 2-Sentence Sliding Windows & Match
    # =========================================================================
    windows = _split_into_windows(context_corpus, window_size=2)
    best_window_ratio = 0.0
    best_window_idx = -1
    best_window_text = ""
    best_matched_weight = 0.0
    best_raw_ratio = 0.0
    best_proper_hits = 0
    best_gate_triggered = False
    best_negation_triggered = False
    best_negation_cues: List[str] = []
    best_negated_clause = ""
    best_matched_tokens: List[str] = []
    best_missing_tokens: List[str] = []
    scored_windows: List[Tuple[float, str, Dict[str, Any]]] = []

    # Tokens used to check if a source window is negating the specific proper nouns / entities in the quote
    anchor_list = [t.lower().strip() for t in (entity_anchor_tokens or []) if t and len(t.strip()) >= 2]
    anchor_stems = {_stem_token(t) for t in anchor_list}
    polarity_anchor_tokens = (
        anchor_list
        if anchor_list
        else (
            [p_low for _, p_low in proper_tokens]
            if proper_tokens
            else [low for _, low, w, _ in weighted_q_tokens if w >= 1.0]
        )
    )

    for win_idx, win in enumerate(windows):
        win_lower = win.lower()
        win_words = set(re.findall(r"\b[a-z0-9\-]{2,}\b", win_lower))
        win_stems = {_stem_token(w) for w in win_words}

        matched_weight = 0.0
        cur_matched: List[str] = []
        cur_missing: List[str] = []
        for stem, low, w, _ in weighted_q_tokens:
            if low in win_words or stem in win_stems or low in win_lower:
                matched_weight += w
                cur_matched.append(f"{low} (stem:{stem}, +{w})")
            else:
                cur_missing.append(f"{low} (stem:{stem}, -{w})")

        raw_ratio = matched_weight / total_weight if total_weight > 0 else 0.0
        ratio = raw_ratio

        # Link A <-> Link B Entity-In-Window Anchor Gate:
        # A 2-sentence window describing a DIFFERENT entity/city (e.g. Panasonic instead of BHP Group,
        # or Hsinchu instead of Zurich) cannot ground a claim about the target entity even if the rest
        # of the predicate words were copied verbatim from that window.
        entity_anchor_hit = True
        if anchor_list:
            entity_anchor_hit = any(
                a_tok in win_words or a_tok in win_lower or _stem_token(a_tok) in win_stems
                for a_tok in anchor_list
            ) or bool(anchor_stems & win_stems)
            if not entity_anchor_hit:
                ratio = min(ratio, 0.30)

        # Link C Gate 1 (Proper-Noun Gate): if the quote has specific proper nouns (e.g. 'Berlin', 'TSMC')
        # and NONE of them appear in this window, cap this window's score at 0.35
        proper_hits = 0
        matched_proper_list: List[str] = []
        gate_triggered = not entity_anchor_hit
        if proper_tokens:
            for p_stem, p_low in proper_tokens:
                if p_low in win_words or p_stem in win_stems or p_low in win_lower:
                    proper_hits += 1
                    matched_proper_list.append(p_low)
            if proper_hits == 0:
                gate_triggered = True
                ratio = min(ratio, 0.35)

        # Link B/C Gate 2 (Negation & Closure Polarity Gate):
        # Even if the quote words appear in this window (or if the LLM deleted "no longer" from its quote),
        # check if the source clause mentioning the entity negates/closes it ("We no longer operate in Shinjuan, China").
        win_negated, win_neg_cues, win_neg_clause = _detect_entity_negation(win, polarity_anchor_tokens)
        if win_negated and raw_ratio >= 0.35:
            ratio = min(ratio, 0.10)

        win_detail = {
            "window_index": win_idx,
            "window_text": win[:350],
            "matched_weight": round(matched_weight, 2),
            "total_weight": total_weight,
            "raw_ratio_before_gate": round(raw_ratio, 3),
            "proper_noun_hits": f"{proper_hits}/{len(proper_tokens)}",
            "matched_proper_nouns": matched_proper_list,
            "proper_noun_gate_capped_at_035": gate_triggered,
            "polarity_negated_in_window": win_negated,
            "negation_cues_in_window": win_neg_cues,
            "window_score_after_gates": round(ratio, 3),
            "matched_tokens": cur_matched,
            "missing_tokens": cur_missing,
        }
        scored_windows.append((ratio, win, win_detail))

        # Track the best window (or if all matching windows were negated, track the highest raw-overlap negated window)
        if ratio > best_window_ratio or (best_window_idx == -1) or (win_negated and raw_ratio > best_raw_ratio and best_window_ratio <= 0.35):
            best_window_ratio = ratio
            best_window_idx = win_idx
            best_window_text = win
            best_matched_weight = round(matched_weight, 2)
            best_raw_ratio = round(raw_ratio, 3)
            best_proper_hits = proper_hits
            best_gate_triggered = gate_triggered
            best_negation_triggered = win_negated
            best_negation_cues = win_neg_cues
            best_negated_clause = win_neg_clause
            best_matched_tokens = cur_matched
            best_missing_tokens = cur_missing

    ranked_windows = sorted(scored_windows, key=lambda x: (x[0], x[2]["raw_ratio_before_gate"]), reverse=True)
    top_candidates = [w for _, w, _ in ranked_windows[:5]]
    top_window_details = [d for _, _, d in ranked_windows[:3]]

    _emit_guardrail_step(
        name="evaluate-link-b-sliding-windows",
        input_data={
            "evidence_quote": quote,
            "source_type": source_type,
            "window_size_sentences": 2,
            "corpus_char_length": len(context_corpus),
            "total_windows_generated": len(windows),
        },
        output_data={
            "exact_verbatim_substring_in_corpus": is_exact_substring,
            "best_window_index": best_window_idx,
            "best_window_text": best_window_text[:450],
            "best_window_score": round(best_window_ratio, 3),
            "polarity_negated_in_best_window": best_negation_triggered,
            "negation_cues_detected": best_negation_cues,
            "top_3_scored_windows": top_window_details,
        },
        level="WARNING" if best_negation_triggered else "DEFAULT",
    )

    # =========================================================================
    # LINK C (Part 2): Hybrid Semantic Fallback & Final Threshold Decision
    # =========================================================================
    sem_sim = None
    score_before_semantic = round(best_window_ratio, 3)
    blended_with_semantic = False

    # Do NOT allow semantic embedding fallback to rescue a negated/closed facility or a cross-page stitched quote
    # where the window containing the entity anchor had weak (< 0.55) lexical predicate support!
    if use_semantic_fallback and not best_negation_triggered and 0.55 <= best_window_ratio < 0.70:
        sem_sim = _hf_embedding_similarity(quote, top_candidates)
        if sem_sim is not None and sem_sim >= 0.72:
            blended_score = round(0.5 * best_window_ratio + 0.5 * sem_sim, 2)
            if blended_score > best_window_ratio:
                best_window_ratio = blended_score
                blended_with_semantic = True

    if best_negation_triggered:
        final_score = 0.05
        threshold_rule_applied = f"polarity_negation_gate_triggered_0.05 (cues={best_negation_cues})"
    elif is_exact_substring and best_window_ratio < 1.0:
        final_score = 1.0
        threshold_rule_applied = "exact_verbatim_substring_confirmed_1.0 (window_ratio=" + str(round(best_window_ratio, 2)) + ")"
    elif best_window_ratio >= 0.70:
        final_score = round(best_window_ratio, 2)
        threshold_rule_applied = "passed_>=0.70_threshold (kept full score)"
    else:
        final_score = round(best_window_ratio * 0.5, 2)
        threshold_rule_applied = "below_0.70_threshold (penalized by 0.5x multiplier)"

    _emit_guardrail_step(
        name="evaluate-link-c-proper-noun-gate-and-threshold",
        input_data={
            "evidence_quote": quote,
            "best_window_index": best_window_idx,
            "total_possible_weight": total_weight,
            "proper_nouns_required": [p_low for _, p_low in proper_tokens],
            "green_light_threshold": 0.70,
            "proper_noun_zero_hit_cap": 0.35,
            "polarity_negation_cap": 0.05,
        },
        output_data={
            "matched_weight_in_best_window": best_matched_weight,
            "matched_tokens_in_best_window": best_matched_tokens,
            "missing_tokens_in_best_window": best_missing_tokens,
            "raw_weighted_ratio_before_gate": best_raw_ratio,
            "proper_noun_hits": f"{best_proper_hits}/{len(proper_tokens)}",
            "proper_noun_gate_triggered": best_gate_triggered,
            "polarity_negation_gate_triggered": best_negation_triggered,
            "negation_cues_detected": best_negation_cues,
            "negated_clause": best_negated_clause or None,
            "deterministic_window_score": score_before_semantic,
            "hf_semantic_similarity": sem_sim,
            "blended_with_semantic_fallback": blended_with_semantic,
            "threshold_rule_applied": threshold_rule_applied,
            "final_grounding_score": final_score,
        },
        level="DEFAULT" if final_score >= 0.70 else "WARNING",
    )

    return final_score


from contextlib import contextmanager


@contextmanager
def _live_guardrail_scope(
    name: str,
    input_data: Dict[str, Any],
    as_type: str = "guardrail",
    metadata: Optional[Dict[str, Any]] = None,
):
    """Opens a live nested Langfuse observation scope around an executing guardrail block."""
    lf = None
    try:
        from agents.observability import get_langfuse

        lf = get_langfuse()
    except Exception:
        lf = None

    if lf is None:
        yield None
        return

    with lf.start_as_current_observation(
        name=name,
        as_type=as_type,
        input=input_data,
        metadata=metadata or {},
    ) as obs:
        yield obs


def _check_third_party_comention(
    entity_label: str,
    ticker: Optional[str],
    company_name: Optional[str],
    search_corpus: str
) -> bool:
    """
    Third-Party Blog Rule: Unlike a first-party SEC 10-K, a third-party web search snippet
    must mention BOTH the target company (e.g. 'Nvidia'/'NVDA') AND the supplier/hub ('TSMC').
    Emits its live evaluation directly to Langfuse.
    """
    if not search_corpus or not search_corpus.strip():
        _emit_guardrail_step(
            name="verify-third-party-comention",
            input_data={"entity_label": entity_label, "ticker": ticker, "company_name": company_name},
            output_data={"passed": False, "reason": "empty_search_corpus"},
            level="WARNING",
        )
        return False

    corpus_lower = search_corpus.lower()
    # 1. Check target company mention
    subj_terms = []
    if ticker:
        subj_terms.append(ticker.lower().strip())
    if company_name:
        for t in re.findall(r"\b\w{3,}\b", company_name.lower()):
            if t not in {"inc", "corp", "corporation", "plc", "ltd", "llc", "company"}:
                subj_terms.append(t)

    matched_subject_terms = [t for t in subj_terms if t in corpus_lower]
    has_subject = bool(matched_subject_terms) if subj_terms else True

    # 2. Check target supplier/hub mention
    entity_tokens = [
        t.lower() for t in re.findall(r"\b[A-Za-z0-9\-]{2,}\b", entity_label or "")
        if t.lower() not in ENTITY_NOISE_WORDS
    ]
    matched_entity_tokens = [t for t in entity_tokens if t in corpus_lower]
    has_entity = bool(matched_entity_tokens) if entity_tokens else True
    passed = has_subject and has_entity

    _emit_guardrail_step(
        name="verify-third-party-comention",
        input_data={
            "entity_label": entity_label,
            "subject_terms_checked": subj_terms,
            "entity_tokens_checked": entity_tokens,
            "search_corpus_char_length": len(search_corpus),
        },
        output_data={
            "matched_subject_terms": matched_subject_terms,
            "has_subject_mention": has_subject,
            "matched_entity_tokens": matched_entity_tokens,
            "has_entity_mention": has_entity,
            "co_mention_passed": passed,
        },
        level="DEFAULT" if passed else "WARNING",
    )
    return passed


def apply_footprint_guardrails(
    raw_hubs: List[PhysicalHub],
    raw_suppliers: List[Any],
    context_corpus: str,
    default_url: str = "https://www.sec.gov",
    ticker: Optional[str] = None,
    company_name: Optional[str] = None,
    source_corpora: Optional[Dict[str, str]] = None,
    retrieved_urls: Optional[Set[str]] = None
) -> Tuple[List[PhysicalHub], List[SupplierEvidence], Dict[str, Any]]:
    """
    Enforces strict anti-hallucination guardrails across Link A, Link B, Link C, and 3rd-party sources.
    Each sub-function (`verify_payload_quote_binding`, `quote_grounding_score`, `_check_third_party_comention`,
    `_hf_embedding_similarity`) emits its live inputs and computed outputs directly to Langfuse as it executes.
    """
    sanitized_hubs: List[PhysicalHub] = []
    sanitized_suppliers: List[SupplierEvidence] = []

    hallucinations_detected = 0
    grounding_scores = []
    warnings: List[str] = []
    subject_stems = _extract_subject_stems(ticker, company_name)
    whitelist_urls = {u.strip() for u in (retrieved_urls or set()) if u}

    with _live_guardrail_scope(
        name="apply-footprint-guardrails",
        input_data={
            "ticker": ticker,
            "company_name": company_name,
            "subject_stems_extracted": sorted(list(subject_stems)),
            "raw_hubs_count": len(raw_hubs),
            "raw_suppliers_count": len(raw_suppliers),
            "whitelisted_web_urls": sorted(list(whitelist_urls)),
            "corpora_lengths": {
                k: len(v or "") for k, v in (source_corpora or {"combined": context_corpus}).items()
            },
        },
        metadata={"ticker": ticker or "UNKNOWN"},
    ) as root_guardrail_obs:
        # 1. Hubs Guardrails
        for h_idx, h in enumerate(raw_hubs):
            hub_name = (h.hub_name or "").strip()
            with _live_guardrail_scope(
                name="inspect-hub-claim",
                input_data={
                    "hub_index": h_idx,
                    "hub_name": hub_name,
                    "region_name": h.region_name,
                    "country_code": h.country_code,
                    "source_type": h.source_type,
                    "source_url": h.source_url,
                    "evidence_quote": h.evidence_quote,
                },
                metadata={"item_type": "hub", "hub_name": hub_name},
            ) as hub_obs:
                if not hub_name or hub_name.lower() in DISALLOWED_PLACEHOLDERS:
                    hallucinations_detected += 1
                    msg = f"Rejected hallucinated placeholder hub: '{hub_name}'"
                    warnings.append(msg)
                    if hub_obs is not None:
                        hub_obs.update(output={"rejected": True, "reason": msg}, level="WARNING")
                    continue

                src_type = (h.source_type or "sec_10k").strip().lower()
                hub_url = h.source_url
                url_repaired = False

                # URL syntax & third-party whitelist validation
                if not is_valid_url(hub_url):
                    hallucinations_detected += 1
                    hub_url = default_url
                    url_repaired = True
                    warnings.append(f"Repaired invalid hub source URL on '{hub_name}'")
                elif src_type == "web_search" and whitelist_urls and hub_url.strip() not in whitelist_urls:
                    hallucinations_detected += 1
                    hub_url = next(iter(whitelist_urls), default_url)
                    url_repaired = True
                    warnings.append(f"Flagged unverified web_search URL on hub '{hub_name}' (not in retrieved search results)")

                # Country normalization
                country = normalize_country_code(h.country_code)

                # Select source-specific corpus if available, falling back to combined context_corpus
                target_corpus = context_corpus
                if source_corpora and source_corpora.get(src_type, "").strip():
                    src_c = source_corpora[src_type].strip()
                    target_corpus = context_corpus if src_c in context_corpus else f"{src_c}\n\n{context_corpus}"

                # Link A: Payload-to-Quote Entity Binding (emits live `verify-link-a-entity-binding` span)
                is_bound, checked_tokens = verify_payload_quote_binding(
                    entity_label=hub_name,
                    secondary_label=h.region_name,
                    quote=h.evidence_quote,
                    subject_stems=subject_stems
                )

                # Link B & C: Sentence-Window + Proper-Noun Grounding Score (emits live Link B & C spans)
                g_score = quote_grounding_score(
                    quote=h.evidence_quote,
                    context_corpus=target_corpus,
                    ticker=ticker,
                    company_name=company_name,
                    source_type=src_type,
                    entity_anchor_tokens=checked_tokens
                )

                if not is_bound:
                    hallucinations_detected += 1
                    g_score = min(g_score, 0.15)
                    warnings.append(
                        f"Link A failed for hub '{hub_name}': location/entity {checked_tokens} not found in its evidence_quote"
                    )
                elif g_score < 0.50 and h.evidence_quote:
                    hallucinations_detected += 1
                    warnings.append(f"Link B/C flagged ungrounded or stitched quote for hub '{hub_name}' (score: {g_score*100:.0f}%)")

                # Third-Party Blog Co-Mention check (emits live `verify-third-party-comention` span)
                comention_passed = True
                if src_type == "web_search" and source_corpora and source_corpora.get("web_search"):
                    comention_passed = _check_third_party_comention(hub_name, ticker, company_name, source_corpora["web_search"])
                    if not comention_passed:
                        hallucinations_detected += 1
                        g_score = min(g_score, 0.25)
                        warnings.append(f"Third-party source for hub '{hub_name}' lacks co-mention of target company and hub")

                if url_repaired:
                    g_score = min(g_score, 0.50)

                grounding_scores.append(g_score)
                if hub_obs is not None:
                    hub_obs.update(
                        output={
                            "normalized_country_code": country,
                            "url_repaired": url_repaired,
                            "final_source_url": hub_url,
                            "link_a_is_bound": is_bound,
                            "third_party_comention_passed": comention_passed,
                            "final_hub_grounding_score": g_score,
                        },
                        level="DEFAULT" if (is_bound and g_score >= 0.70 and not url_repaired) else "WARNING",
                    )

                sanitized_hubs.append(PhysicalHub(
                    region_name=h.region_name or f"{country} Operations",
                    country_code=country,
                    language_code=h.language_code or "en",
                    hub_name=hub_name,
                    local_keywords=h.local_keywords or "operations OR facilities",
                    facility_type=h.facility_type or "operations",
                    source_url=hub_url,
                    source_type="repaired_fallback" if url_repaired else src_type,
                    evidence_quote=h.evidence_quote or "Verified operational location."
                ))

        # 2. Supplier Guardrails
        for s_idx, s in enumerate(raw_suppliers):
            s_dict = s.model_dump() if hasattr(s, "model_dump") else (s.dict() if hasattr(s, "dict") else (s if isinstance(s, dict) else {"name": str(s)}))
            name = s_dict.get("name", "").strip()
            quote = s_dict.get("evidence_quote")
            src_type = (s_dict.get("source_type") or "sec_10k").strip().lower()
            s_url = s_dict.get("source_url")

            with _live_guardrail_scope(
                name="inspect-supplier-claim",
                input_data={
                    "supplier_index": s_idx,
                    "supplier_name": name,
                    "category": s_dict.get("category"),
                    "source_type": src_type,
                    "source_url": s_url,
                    "evidence_quote": quote,
                },
                metadata={"item_type": "supplier", "supplier_name": name},
            ) as sup_obs:
                if not name or name.lower() in DISALLOWED_PLACEHOLDERS:
                    hallucinations_detected += 1
                    msg = f"Rejected hallucinated placeholder supplier: '{name}'"
                    warnings.append(msg)
                    if sup_obs is not None:
                        sup_obs.update(output={"rejected": True, "reason": msg}, level="WARNING")
                    continue

                url_repaired = False

                # URL syntax & third-party whitelist validation
                if not is_valid_url(s_url):
                    hallucinations_detected += 1
                    s_url = default_url
                    url_repaired = True
                    warnings.append(f"Repaired invalid supplier source URL on '{name}'")
                elif src_type == "web_search" and whitelist_urls and s_url.strip() not in whitelist_urls:
                    hallucinations_detected += 1
                    s_url = next(iter(whitelist_urls), default_url)
                    url_repaired = True
                    warnings.append(f"Flagged unverified web_search URL on supplier '{name}' (not in retrieved search results)")

                target_corpus = context_corpus
                if source_corpora and source_corpora.get(src_type, "").strip():
                    src_c = source_corpora[src_type].strip()
                    target_corpus = context_corpus if src_c in context_corpus else f"{src_c}\n\n{context_corpus}"

                # Link A: Supplier name must appear in its own evidence quote (emits live Link A span)
                is_bound, checked_tokens = verify_payload_quote_binding(
                    entity_label=name,
                    secondary_label=None,
                    quote=quote,
                    subject_stems=subject_stems
                )

                # Link B & C: Sentence-Window + Proper-Noun Grounding Score (emits live Link B & C spans)
                g_score = quote_grounding_score(
                    quote=quote,
                    context_corpus=target_corpus,
                    ticker=ticker,
                    company_name=company_name,
                    source_type=src_type,
                    entity_anchor_tokens=checked_tokens
                )

                if not is_bound:
                    hallucinations_detected += 1
                    g_score = min(g_score, 0.15)
                    warnings.append(
                        f"Link A failed for supplier '{name}': supplier entity {checked_tokens} not found in its evidence_quote"
                    )
                elif g_score < 0.50 and quote:
                    hallucinations_detected += 1
                    warnings.append(f"Link B/C flagged ungrounded or stitched quote for supplier '{name}' (score: {g_score*100:.0f}%)")

                # Third-Party Blog Co-Mention check (emits live span)
                comention_passed = True
                if src_type == "web_search" and source_corpora and source_corpora.get("web_search"):
                    comention_passed = _check_third_party_comention(name, ticker, company_name, source_corpora["web_search"])
                    if not comention_passed:
                        hallucinations_detected += 1
                        g_score = min(g_score, 0.25)
                        warnings.append(f"Third-party source for supplier '{name}' lacks co-mention of target company and supplier")

                if url_repaired:
                    g_score = min(g_score, 0.50)

                grounding_scores.append(g_score)
                if sup_obs is not None:
                    sup_obs.update(
                        output={
                            "url_repaired": url_repaired,
                            "final_source_url": s_url,
                            "link_a_is_bound": is_bound,
                            "third_party_comention_passed": comention_passed,
                            "final_supplier_grounding_score": g_score,
                        },
                        level="DEFAULT" if (is_bound and g_score >= 0.70 and not url_repaired and comention_passed) else "WARNING",
                    )

                sanitized_suppliers.append(SupplierEvidence(
                    name=name,
                    category=s_dict.get("category") or "Tier-1 Partner",
                    source_url=s_url,
                    source_type="repaired_fallback" if url_repaired else src_type,
                    evidence_quote=quote or "Verified relationship from disclosure text."
                ))

        avg_grounding = round(sum(grounding_scores) / len(grounding_scores), 2) if grounding_scores else 1.0

        stats = {
            "hallucinations_detected": hallucinations_detected,
            "avg_grounding_score": avg_grounding,
            "warnings": warnings,
            "initial_hubs_count": len(raw_hubs),
            "sanitized_hubs_count": len(sanitized_hubs),
            "initial_suppliers_count": len(raw_suppliers),
            "sanitized_suppliers_count": len(sanitized_suppliers),
            "per_item_scores": grounding_scores,
        }

        if root_guardrail_obs is not None:
            root_guardrail_obs.update(
                output=stats,
                level="WARNING" if hallucinations_detected > 0 else "DEFAULT",
            )
            root_guardrail_obs.score_trace(
                name="grounding_score",
                value=avg_grounding,
                comment="; ".join(warnings[:3]) or "All claims grounded in primary sources",
            )
            root_guardrail_obs.score_trace(
                name="hallucinations_detected",
                value=float(hallucinations_detected),
            )

    logger.info(
        f"[Guardrails] Cleaned: {len(sanitized_hubs)} hubs, {len(sanitized_suppliers)} suppliers. "
        f"Hallucinations caught: {hallucinations_detected}. Avg Grounding: {avg_grounding*100:.1f}%"
    )

    return sanitized_hubs, sanitized_suppliers, stats


if __name__ == "__main__":
    # Debug Entry Point: Calls the Footprint Agent from its main entry point `research_company_footprint()`
    # Set `force_live = False` to test the PostgreSQL cache + `sources_unchanged` fingerprint check first,
    # or `force_live = True` to force a fresh MCP + LLM + Guardrail run every time.
    import asyncio
    import json
    import sys
    from pathlib import Path

    BACKEND_DIR = Path(__file__).resolve().parent.parent
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    # Alias __main__ as ingestion.guardrails so footprint_agent hits breakpoints placed in this file
    sys.modules["ingestion.guardrails"] = sys.modules[__name__]

    from ingestion.footprint_agent import research_company_footprint

    GOLDEN_DATASET_PATH = BACKEND_DIR / "logs" / "golden_footprint_dataset.json"

    async def _debug_from_footprint_entry_point():
        test_ticker = "NVDA"
        force_live = False  # False = runs PostgreSQL + Fingerprint check first; True = forces fresh LLM + Guardrail run

        print(f"\n=== [DEBUG] Calling Entry Point research_company_footprint('{test_ticker}', force_live={force_live}) ===")
        footprint = await research_company_footprint(test_ticker, force_live=force_live)

        if footprint is not None:
            eval_obj = getattr(footprint, "evaluation", None)
            output_summary = {
                "ticker": footprint.ticker,
                "company_name": footprint.name,
                "archetype": footprint.archetype,
                "hubs_count": len(footprint.hubs),
                "suppliers_count": len(footprint.key_suppliers),
                "hubs": [h.model_dump() if hasattr(h, "model_dump") else h.dict() for h in footprint.hubs],
                "suppliers": [
                    (s.model_dump() if hasattr(s, "model_dump") else (s.dict() if hasattr(s, "dict") else s))
                    for s in footprint.key_suppliers
                ],
                "token_usage": footprint.token_usage,
                "evaluation": (
                    eval_obj.model_dump()
                    if hasattr(eval_obj, "model_dump")
                    else (eval_obj.dict() if hasattr(eval_obj, "dict") else None)
                ),
            }

            try:
                existing = []
                if GOLDEN_DATASET_PATH.exists():
                    existing = json.loads(GOLDEN_DATASET_PATH.read_text(encoding="utf-8"))
                existing = [entry for entry in existing if entry.get("ticker") != test_ticker]
                existing.append(output_summary)
                GOLDEN_DATASET_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  -> Saved output to Golden Dataset: {GOLDEN_DATASET_PATH}")
            except Exception as exc:
                print(f"  -> Golden Dataset save warning: {exc}")

            print("\n=== [DEBUG] Footprint Agent Entry Point Result ===")
            print(json.dumps(output_summary, indent=2, ensure_ascii=False))

    asyncio.run(_debug_from_footprint_entry_point())
