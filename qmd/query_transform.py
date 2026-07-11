"""
query_transform.py — LLM-based query rewriting for hybrid search.

search_hybrid() sends the raw question to `vec` unchanged, and (if
enabled) to `hyde` unchanged - neither benefits from client-side
rewriting (vec just embeds whatever text it's given; hyde does its own
generation server-side and expects a question). This module rewrites
the query for exactly ONE sub-type - lex - which is pure lexical/BM25
term matching with no generation or embedding step, and clearly
benefits from a keyword-dense phrase instead of a full natural-language
question (stopwords and question-phrasing dilute term-overlap scoring).

Uses the same Azure OpenAI deployment as the main agent (see the
AZURE_OPENAI_* env vars read by agent.py's build_model()). Fails open:
if Azure OpenAI isn't configured, or the LLM call errors for any
reason, transform_query() falls back to returning the original question
unchanged - a broken/misconfigured transform step must never take
search down with it.

Toggle without touching code:
  QMD_QUERY_TRANSFORM=0   disable entirely (lex also gets raw text)
  QMD_QUERY_TRANSFORM=1   enabled (default)
"""
from __future__ import annotations

import os

from pydantic import BaseModel, Field

from flow_logger import log_call, logger

TRANSFORM_ENABLED = os.environ.get("QMD_QUERY_TRANSFORM", "1") != "0"

SYSTEM_PROMPT = """You rewrite a user's question into a short, \
keyword-dense phrase for a lexical/BM25 search engine.

Keep only names, nouns, technical terms, and entities. Strip stopwords \
and question phrasing entirely - no "what is", "which", "how does", \
"can you". Precision on the actual searchable terms matters more than \
fluency or grammar; this does not need to read as a sentence."""


class KeywordQuery(BaseModel):
    keyword_query: str = Field(
        ..., description="Keyword/entity-dense phrase for lexical/BM25 search."
    )


_model = None
_model_build_attempted = False


def _build_model():
    """Mirrors agent.py's build_model() Azure-detection logic, kept
    separate so this module has no import-time dependency on agent.py
    (avoids a circular import: agent.py -> tools.py -> qmd_retrieval.py
    -> query_transform.py)."""
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if not deployment:
        return None

    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_deployment=deployment,
        azure_endpoint=os.environ["AZURE_OPENAI_BASE_URL"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        temperature=0.3,
    )


def _get_model():
    global _model, _model_build_attempted
    if not _model_build_attempted:
        _model_build_attempted = True
        try:
            _model = _build_model()
        except Exception as e:  # noqa: BLE001 - fail open, never crash search over this
            logger.warning(f"query_transform: could not build model, falling back to passthrough: {e}")
            _model = None
    return _model


@log_call("transform_query")
def transform_query(question: str) -> str:
    """Return a keyword-dense rewrite of `question` for the lex
    sub-search. Falls back to the original question unchanged (old
    behavior) if transformation is disabled, unconfigured, or fails for
    any reason.
    """
    if not TRANSFORM_ENABLED:
        return question

    model = _get_model()
    if model is None:
        return question

    try:
        structured_model = model.with_structured_output(KeywordQuery)
        result: KeywordQuery = structured_model.invoke(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]
        )
        return result.keyword_query
    except Exception as e:  # noqa: BLE001 - fail open, never break search over this
        logger.warning(f"query_transform: LLM rewrite failed, falling back to passthrough: {e}")
        return question