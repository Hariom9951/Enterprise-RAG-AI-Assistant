"""
Enterprise RAG AI Assistant — Answer & Citation Evaluation
===========================================================
Deterministic evaluation of agent response characteristics:
- Citation presence, reference validity, and source grounding.
- Proper abstention behavior for unanswerable / adversarial queries.
- Response structure, latency sanity, and outcome consistency.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.agent_service import AgentRunResult

# Standard abstention and negative indicator phrases
ABSTENTION_PATTERNS = [
    re.compile(r"cannot process this request", re.IGNORECASE),
    re.compile(r"disallowed content", re.IGNORECASE),
    re.compile(r"insufficient (evidence|information|context)", re.IGNORECASE),
    re.compile(
        r"cannot find (sufficient|enough|any)?\s*(evidence|information|details)",
        re.IGNORECASE,
    ),
    re.compile(
        r"cannot (answer|find|determine) (based on|from) (the )?(provided|retrieved)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"no (relevant )?(information|documents?|evidence) (found|available)",
        re.IGNORECASE,
    ),
    re.compile(r"does not contain (information|details|answers)", re.IGNORECASE),
    re.compile(r"not enough information", re.IGNORECASE),
]


@dataclass
class CitationEvaluationResult:
    """Evaluation result for answer citations."""

    citation_present: bool
    cited_indices: list[int] = field(default_factory=list)
    all_indices_valid: bool = True
    invalid_indices: list[int] = field(default_factory=list)
    cited_chunk_ids: list[str] = field(default_factory=list)
    source_grounding_rate: float = 1.0
    target_citation_recall: float | None = None
    target_citation_precision: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AbstentionEvaluationResult:
    """Evaluation result for agent abstention / rejection behavior."""

    abstention_detected: bool
    expected_abstention: bool
    abstention_decision_correct: bool
    detected_phrase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StructureEvaluationResult:
    """Evaluation result for AgentRunResult structural integrity."""

    valid_run_id: bool
    valid_latency: bool
    valid_final_answer: bool
    outcome_consistent: bool
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroundingEvaluationResult:
    """
    Evaluation result for lexical evidence grounding.

    NOTE: This is a deterministic lexical grounding heuristic based on token overlap
    between the generated answer and cited evidence passages. It measures text-level
    surface attribution and vocabulary overlap. It DOES NOT claim to prove factual
    correctness, logical entailment, semantic truth, or absence of subtle hallucinations.
    """

    grounding_score: float
    grounded_sentences_count: int
    total_sentences_count: int
    sentence_grounding_rate: float
    supported_sentences: list[str] = field(default_factory=list)
    unsupported_sentences: list[str] = field(default_factory=list)
    overlap_tokens_count: int = 0
    answer_tokens_count: int = 0
    evidence_tokens_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_citations(
    answer: str,
    retrieved_docs: list[dict[str, Any]],
    expected_targets: list[str] | None = None,
) -> CitationEvaluationResult:
    """
    Deterministically inspect bracket citations in the answer:
    1. Extracts all [N] index citations from the answer string.
    2. Validates that 1 <= N <= len(retrieved_docs).
    3. Resolves cited chunk IDs from retrieved_docs.
    4. Computes source grounding rate (cited chunks actually in retrieved set).
    5. Computes citation recall and precision against expected target chunk IDs.
    """
    matches = re.findall(r"\[(\d+)\]", answer or "")
    raw_indices = [int(m) for m in matches]
    unique_indices = sorted(list(set(raw_indices)))

    num_retrieved = len(retrieved_docs)
    valid_indices: list[int] = []
    invalid_indices: list[int] = []

    for idx in unique_indices:
        if 1 <= idx <= num_retrieved:
            valid_indices.append(idx)
        else:
            invalid_indices.append(idx)

    # Map valid 1-based indices to chunk IDs in retrieved_docs
    cited_chunk_ids: list[str] = []
    for idx in valid_indices:
        item = retrieved_docs[idx - 1]
        cid = str(item.get("chunk_id") or item.get("id") or "")
        if cid:
            cited_chunk_ids.append(cid)

    # Source grounding rate: valid citations vs all parsed citations
    total_parsed = len(unique_indices)
    if total_parsed == 0:
        source_grounding_rate = 1.0  # No hallucinated citations
    else:
        source_grounding_rate = float(len(valid_indices) / total_parsed)

    # Target citation recall & precision
    target_recall: float | None = None
    target_precision: float | None = None
    if expected_targets is not None:
        targets_set = set(str(t) for t in expected_targets)
        if len(targets_set) == 0:
            target_recall = 1.0 if len(cited_chunk_ids) == 0 else 0.0
            target_precision = 1.0 if len(cited_chunk_ids) == 0 else 0.0
        else:
            hits = sum(1 for cid in cited_chunk_ids if cid in targets_set)
            target_recall = float(hits / len(targets_set))
            target_precision = (
                float(hits / len(cited_chunk_ids)) if cited_chunk_ids else 0.0
            )

    return CitationEvaluationResult(
        citation_present=len(valid_indices) > 0,
        cited_indices=unique_indices,
        all_indices_valid=len(invalid_indices) == 0,
        invalid_indices=invalid_indices,
        cited_chunk_ids=cited_chunk_ids,
        source_grounding_rate=round(source_grounding_rate, 4),
        target_citation_recall=round(target_recall, 4)
        if target_recall is not None
        else None,
        target_citation_precision=round(target_precision, 4)
        if target_precision is not None
        else None,
    )


def evaluate_abstention(
    answer: str,
    expected_abstention: bool,
    evidence_sufficient: bool = True,
    success: bool = True,
) -> AbstentionEvaluationResult:
    """
    Check whether the agent correctly abstained when expected:
    - If expected_abstention is True: answer should match abstention phrase OR evidence_sufficient is False OR success is False.
    - If expected_abstention is False: answer should NOT falsely claim insufficient evidence.
    """
    text = answer or ""
    detected_phrase: str | None = None

    for pattern in ABSTENTION_PATTERNS:
        match = pattern.search(text)
        if match:
            detected_phrase = match.group(0)
            break

    # An abstention is detected if an abstention phrase matches, or if marked unsuccessful / blocked
    is_abstaining = bool(detected_phrase) or (not evidence_sufficient) or (not success)
    decision_correct = is_abstaining == expected_abstention

    return AbstentionEvaluationResult(
        abstention_detected=is_abstaining,
        expected_abstention=expected_abstention,
        abstention_decision_correct=decision_correct,
        detected_phrase=detected_phrase,
    )


def evaluate_response_structure(result: AgentRunResult) -> StructureEvaluationResult:
    """
    Verify the structural validity of an AgentRunResult instance.
    Ensures runtime contracts are satisfied without data corruption.
    """
    errors: list[str] = []

    # 1. Valid UUID run_id
    valid_id = False
    if isinstance(result.run_id, uuid.UUID):
        valid_id = True
    elif isinstance(result.run_id, str):
        try:
            uuid.UUID(result.run_id)
            valid_id = True
        except ValueError:
            errors.append(f"run_id '{result.run_id}' is not a valid UUID")
    else:
        errors.append(f"run_id has invalid type {type(result.run_id)}")

    # 2. Latency non-negative
    valid_latency = result.total_latency_ms >= 0
    if not valid_latency:
        errors.append(f"total_latency_ms is negative: {result.total_latency_ms}")

    # 3. Final answer non-null
    valid_answer = (
        isinstance(result.final_answer, str) and len(result.final_answer.strip()) > 0
    )
    if not valid_answer:
        errors.append("final_answer is empty or missing")

    # 4. Consistency
    consistent = True
    if not result.success and not result.error_message:
        # Failure must have an error message
        consistent = False
        errors.append("Run marked success=False but error_message is empty")

    return StructureEvaluationResult(
        valid_run_id=valid_id,
        valid_latency=valid_latency,
        valid_final_answer=valid_answer,
        outcome_consistent=consistent,
        errors=errors,
    )


# Common stopwords filtered during lexical token overlap calculation
LEXICAL_GROUNDING_STOPWORDS: set[str] = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


def _extract_chunk_text(chunk: dict[str, Any] | str) -> str:
    """Extract plain text representation from a chunk fixture, dict, or string."""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        return str(
            chunk.get("text") or chunk.get("content") or chunk.get("chunk_text") or ""
        )
    return str(chunk)


def _tokenize_lexical(text: str, stopwords: set[str] | None = None) -> list[str]:
    """Tokenize text into lowercased content tokens, removing common stopwords."""
    raw_tokens = re.findall(r"\b[a-zA-Z0-9_\-\.]{2,}\b", text.lower())
    active_stops = stopwords if stopwords is not None else LEXICAL_GROUNDING_STOPWORDS
    return [t for t in raw_tokens if t not in active_stops]


def evaluate_evidence_grounding(
    answer: str,
    cited_chunks: Sequence[dict[str, Any] | str] | None = None,
    sentence_threshold: float = 0.25,
    min_sentence_tokens: int = 2,
) -> GroundingEvaluationResult:
    """
    Deterministic lexical grounding heuristic evaluating token overlap between the
    generated answer and cited evidence passages.

    NOTE: This function measures surface-level token overlap and lexical attribution.
    It DOES NOT claim to prove factual correctness, semantic entailment, or logical truth.
    A high score indicates strong lexical alignment with cited passages, while a low score
    indicates potential ungrounded extrapolation or vocabulary divergence.

    Args:
        answer: The generated answer string.
        cited_chunks: Sequence of evidence chunk dictionaries or raw text strings.
        sentence_threshold: Fraction of content tokens in a sentence that must appear
                            in the evidence for that sentence to be classified as supported.
        min_sentence_tokens: Minimum content tokens required in a sentence to evaluate grounding.
    """
    clean_answer = (answer or "").strip()
    chunks = list(cited_chunks) if cited_chunks is not None else []

    # Combine evidence texts
    evidence_texts = [_extract_chunk_text(c) for c in chunks]
    full_evidence = " ".join(t for t in evidence_texts if t.strip())

    evidence_tokens_list = _tokenize_lexical(full_evidence)
    evidence_tokens_set = set(evidence_tokens_list)

    if not clean_answer:
        # Empty answer edge cases
        if not evidence_tokens_set:
            return GroundingEvaluationResult(
                grounding_score=1.0,
                grounded_sentences_count=0,
                total_sentences_count=0,
                sentence_grounding_rate=1.0,
                supported_sentences=[],
                unsupported_sentences=[],
                overlap_tokens_count=0,
                answer_tokens_count=0,
                evidence_tokens_count=0,
            )
        return GroundingEvaluationResult(
            grounding_score=0.0,
            grounded_sentences_count=0,
            total_sentences_count=0,
            sentence_grounding_rate=0.0,
            supported_sentences=[],
            unsupported_sentences=[],
            overlap_tokens_count=0,
            answer_tokens_count=0,
            evidence_tokens_count=len(evidence_tokens_set),
        )

    answer_tokens = _tokenize_lexical(clean_answer)

    # Split answer into sentences
    raw_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", clean_answer) if s.strip()
    ]
    total_sentences = len(raw_sentences)

    if not evidence_tokens_set:
        # Answer exists but zero evidence provided: completely ungrounded
        return GroundingEvaluationResult(
            grounding_score=0.0,
            grounded_sentences_count=0,
            total_sentences_count=total_sentences,
            sentence_grounding_rate=0.0,
            supported_sentences=[],
            unsupported_sentences=raw_sentences,
            overlap_tokens_count=0,
            answer_tokens_count=len(answer_tokens),
            evidence_tokens_count=0,
        )

    # Overall token overlap calculation
    overlap_tokens = [t for t in answer_tokens if t in evidence_tokens_set]
    overlap_count = len(overlap_tokens)
    grounding_score = (
        float(overlap_count / len(answer_tokens)) if answer_tokens else 1.0
    )

    # Sentence-level grounding evaluation
    supported: list[str] = []
    unsupported: list[str] = []

    for s in raw_sentences:
        # Strip citation markers like [1], [2] before evaluating sentence tokens
        stripped_s = re.sub(r"\[\d+\]", "", s).strip()
        stoks = _tokenize_lexical(stripped_s)
        if len(stoks) < min_sentence_tokens:
            if stoks and all(t in evidence_tokens_set for t in stoks):
                supported.append(s)
            elif not stoks:
                supported.append(s)
            else:
                unsupported.append(s)
            continue

        hits = sum(1 for t in stoks if t in evidence_tokens_set)
        ratio = hits / len(stoks)
        if ratio >= sentence_threshold:
            supported.append(s)
        else:
            unsupported.append(s)

    sentence_grounding_rate = (
        float(len(supported) / total_sentences) if total_sentences > 0 else 1.0
    )

    return GroundingEvaluationResult(
        grounding_score=round(grounding_score, 4),
        grounded_sentences_count=len(supported),
        total_sentences_count=total_sentences,
        sentence_grounding_rate=round(sentence_grounding_rate, 4),
        supported_sentences=supported,
        unsupported_sentences=unsupported,
        overlap_tokens_count=overlap_count,
        answer_tokens_count=len(answer_tokens),
        evidence_tokens_count=len(evidence_tokens_set),
    )
