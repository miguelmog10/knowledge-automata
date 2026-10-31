"""The Comparator (reconciliation): how a new draft relates to existing records (ADR-0017).

Retrieval first, then one judgement: embed the active records and the draft, keep the top K
by cosine similarity, rerank them, and ask the model to classify the draft against the top
N as ``new``, ``update``, ``reaffirmation`` or ``supersession``. Code checks the answer with
``validate_reconciliation`` and retries once with the errors, like the Registrar loop. This
module never reads or writes files: the pipeline passes the records in and applies the
classification.
"""

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from knowledge_automata.core.prompts import ERRORS_PLACEHOLDER, Prompt, retry_system_text
from knowledge_automata.core.registers import RegisterSpec
from knowledge_automata.core.retrieval import comparison_text, top_k
from knowledge_automata.core.schemas import RECONCILIATION_SCHEMA, load_schema
from knowledge_automata.core.validation import validate_reconciliation
from knowledge_automata.llm import CallContext, LanguageModel, LLMResponseError, Usage

TOP_K_VARIABLE = "KA_COMPARATOR_TOP_K"
TOP_N_VARIABLE = "KA_COMPARATOR_TOP_N"
DEFAULT_TOP_K = 10
DEFAULT_TOP_N = 3


class ComparatorConfigError(Exception):
    """A Comparator setting in the environment is invalid."""


def _whole_number(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ComparatorConfigError(f"{name} must be a whole number of at least 1, got {raw!r}")
    return value


@dataclass(frozen=True)
class ComparatorSettings:
    """How many records retrieval keeps: ``top_k`` by cosine, then ``top_n`` after Rerank."""

    top_k: int = DEFAULT_TOP_K
    top_n: int = DEFAULT_TOP_N

    def __post_init__(self) -> None:
        if self.top_k < 1 or self.top_n < 1:
            raise ComparatorConfigError(f"{TOP_K_VARIABLE} and {TOP_N_VARIABLE} must be at least 1")
        if self.top_n > self.top_k:
            raise ComparatorConfigError(
                f"{TOP_N_VARIABLE} ({self.top_n}) cannot be greater than "
                f"{TOP_K_VARIABLE} ({self.top_k})"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "ComparatorSettings":
        """Read both settings; unset or empty is the default."""
        return cls(
            top_k=_whole_number(env, TOP_K_VARIABLE, DEFAULT_TOP_K),
            top_n=_whole_number(env, TOP_N_VARIABLE, DEFAULT_TOP_N),
        )


@dataclass(frozen=True)
class Comparator:
    agent: str  # used in CallContext and events: "comparator"
    spec: RegisterSpec
    prompt: Prompt
    retry_prompt: Prompt
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {self.max_attempts}")
        if ERRORS_PLACEHOLDER not in self.retry_prompt.text:
            raise ValueError(f"The retry prompt must contain {ERRORS_PLACEHOLDER}")

    @property
    def retry_version(self) -> str:
        return f"{self.prompt.version}+{self.retry_prompt.version}"


@dataclass(frozen=True)
class Candidate:
    record_id: str
    score: float  # Rerank relevance score; never shown to the model


@dataclass(frozen=True)
class ComparisonOutcome:
    """The Comparator's classification, or why it was rejected.

    With no active records there is no comparison: ``classification`` is ``new``,
    ``candidates`` is empty and no call was made.
    """

    classification: str | None  # None when rejected
    target_id: str | None
    reason: str | None  # model text: printed, never stored
    candidates: tuple[Candidate, ...]  # in Rerank order
    attempts: int  # chat attempts; 0 when there was no comparison
    model: str | None  # model of the accepted answer
    prompt_version: str | None  # of the accepted or last attempt; None with no comparison
    embed_usage: tuple[Usage, ...] = ()
    rerank_usage: tuple[Usage, ...] = ()
    chat_usage: tuple[Usage, ...] = ()
    errors: tuple[str, ...] = ()  # errors of the last attempt when rejected
    error_type: str | None = None  # exception class name when the last response was unusable

    @property
    def accepted(self) -> bool:
        return self.classification is not None

    @property
    def compared(self) -> bool:
        return bool(self.candidates)


def user_message(
    draft: Mapping[str, Any],
    shown: Sequence[Mapping[str, Any]],
    *,
    artifact_date: str | None,
) -> str:
    """One JSON object between ``<comparison>`` lines, with every ``<`` escaped.

    Escaping ``<`` as ``\\u003c`` keeps the JSON equal while making sure no text inside it
    can close the tag. Candidates appear in Rerank order, without their scores.
    """
    new_decision: dict[str, Any] = {}
    if artifact_date is not None:
        new_decision["artifact_date"] = artifact_date
    new_decision["content"] = draft["content"]
    new_decision["evidence"] = draft["evidence"]
    payload = {
        "new_decision": new_decision,
        "existing_records": [
            {"id": record["id"], "content": record["content"]} for record in shown
        ],
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2).replace("<", "\\u003c")
    return "<comparison>\n" + body + "\n</comparison>"


def _shortlist(
    comparator: Comparator,
    llm: LanguageModel,
    *,
    draft: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    artifact_id: str,
    settings: ComparatorSettings,
) -> tuple[list[Candidate], Usage, Usage, Usage]:
    """Embed, keep the top K by cosine, rerank to the top N. Errors propagate."""
    context = CallContext(comparator.agent, artifact_id)
    texts = {record["id"]: comparison_text(record["content"]) for record in records}
    query = comparison_text(draft["content"])
    documents = llm.embed(list(texts.values()), input_type="document", context=context)
    queried = llm.embed([query], input_type="query", context=context)
    if len(documents.vectors) != len(texts) or len(queried.vectors) != 1:
        raise LLMResponseError(
            f"Embed returned {len(documents.vectors)} and {len(queried.vectors)} vectors "
            f"for {len(texts)} records and 1 draft"
        )
    vectors = dict(zip(texts, documents.vectors, strict=True))
    shortlist = top_k(queried.vectors[0], vectors, settings.top_k)
    top_n = min(settings.top_n, len(shortlist))
    reranked = llm.rerank(
        query, [texts[record_id] for record_id in shortlist], top_n=top_n, context=context
    )
    indexes = [result.index for result in reranked.results[:top_n]]
    if not indexes:
        raise LLMResponseError(f"Rerank returned no results for {len(shortlist)} documents")
    if len(set(indexes)) != len(indexes) or not all(0 <= i < len(shortlist) for i in indexes):
        raise LLMResponseError(f"Rerank returned invalid document indexes: {indexes}")
    candidates = [
        Candidate(shortlist[result.index], result.score) for result in reranked.results[:top_n]
    ]
    return candidates, documents.usage, queried.usage, reranked.usage


def compare(
    comparator: Comparator,
    llm: LanguageModel,
    *,
    draft: Mapping[str, Any],
    active_records: Sequence[Mapping[str, Any]],
    artifact_id: str,
    artifact_date: str | None,
    settings: ComparatorSettings,
) -> ComparisonOutcome:
    """Classify an accepted draft against the register's active records.

    ``LLMResponseError`` from the classification call counts as a failed attempt; every
    other ``LLMError``, and any error from Embed or Rerank, propagates unchanged.
    """
    if not active_records:
        return ComparisonOutcome(
            classification="new",
            target_id=None,
            reason=None,
            candidates=(),
            attempts=0,
            model=None,
            prompt_version=None,
        )

    candidates, embed_documents, embed_query, rerank_usage = _shortlist(
        comparator,
        llm,
        draft=draft,
        records=active_records,
        artifact_id=artifact_id,
        settings=settings,
    )
    by_id = {record["id"]: record for record in active_records}
    shown = {candidate.record_id: by_id[candidate.record_id] for candidate in candidates}
    user = user_message(draft, list(shown.values()), artifact_date=artifact_date)
    schema = load_schema(RECONCILIATION_SCHEMA)
    usage: list[Usage] = []
    errors: tuple[str, ...] = ()
    error_type: str | None = None
    version = comparator.prompt.version
    common = {
        "candidates": tuple(candidates),
        "embed_usage": (embed_documents, embed_query),
        "rerank_usage": (rerank_usage,),
    }

    for attempt in range(1, comparator.max_attempts + 1):
        if attempt == 1:
            system, version = comparator.prompt.text, comparator.prompt.version
        else:
            system = retry_system_text(comparator.prompt, comparator.retry_prompt, errors)
            version = comparator.retry_version
        context = CallContext(comparator.agent, artifact_id, version)
        try:
            result = llm.chat_json(system=system, user=user, schema=schema, context=context)
        except LLMResponseError as error:
            if error.usage is not None:
                usage.append(error.usage)
            errors, error_type = (str(error),), type(error).__name__
            continue
        usage.append(result.usage)
        validation = validate_reconciliation(result.data, comparator.spec, shown)
        if validation.ok:
            return ComparisonOutcome(
                classification=result.data["classification"],
                target_id=result.data.get("target_id"),
                reason=result.data["reason"],
                attempts=attempt,
                model=result.model,
                prompt_version=version,
                chat_usage=tuple(usage),
                **common,
            )
        errors, error_type = validation.errors, None

    return ComparisonOutcome(
        classification=None,
        target_id=None,
        reason=None,
        attempts=comparator.max_attempts,
        model=None,
        prompt_version=version,
        chat_usage=tuple(usage),
        errors=errors,
        error_type=error_type,
        **common,
    )
