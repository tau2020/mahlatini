"""
RAG Pipeline
=============
Retrieval-Augmented Generation: combines vector search with LLM generation
to answer travel queries grounded in Mahlatini website content.
"""

import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.services.vector_store import search_knowledge_base
from app.services.llm import get_llm, compress_response

logger = logging.getLogger(__name__)


def _load_prompt(name: str) -> str:
    """Load a prompt template from disk."""
    path = settings.prompts_dir / f"{name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning(f"Prompt template not found: {path}")
    return ""


def _build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    if not chunks:
        return "No relevant information found in the knowledge base."

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("page_title", "Unknown")
        url = chunk.get("source_url", "")
        text = chunk.get("text", "")
        score = chunk.get("score", 0)
        context_parts.append(
            f"[Source {i}: {source} ({url}) — relevance: {score:.2f}]\n{text}"
        )

    return "\n\n---\n\n".join(context_parts)


def _build_history(messages: list[dict], max_messages: int = 5) -> str:
    """Format recent conversation history."""
    if not messages:
        return "No previous messages."

    recent = messages[-max_messages:]
    history_parts = []
    for msg in recent:
        role = "Client" if msg.get("role") == "user" else "Concierge"
        history_parts.append(f"{role}: {msg['content']}")

    return "\n".join(history_parts)


def compute_confidence(chunks: list[dict]) -> float:
    """
    Compute retrieval confidence score based on similarity scores
    of the top retrieved chunks.
    """
    if not chunks:
        return 0.0

    scores = [c.get("score", 0) for c in chunks]
    top_score = max(scores)
    avg_top3 = sum(scores[:3]) / min(len(scores), 3)

    # Weighted: 60% top score, 40% average of top 3
    confidence = (top_score * 0.6) + (avg_top3 * 0.4)
    return round(confidence, 3)


def confidence_action(confidence: float) -> str:
    """Determine action based on confidence level."""
    if confidence >= settings.rag_confidence_high:
        return "respond"
    elif confidence >= settings.rag_confidence_medium:
        return "respond_with_caveat"
    else:
        return "escalate"


async def answer_query(
    question: str,
    conversation_history: list[dict] = None,
    category_filter: Optional[str] = None,
    destination_filter: Optional[str] = None,
    provider: Optional[str] = None,
    collection_context: str = "",
) -> dict:
    """
    Full RAG pipeline: retrieve relevant context, then generate an answer.

    Args:
        question: User's question
        conversation_history: Previous messages for context
        category_filter: Optional content category filter
        destination_filter: Optional destination filter
        provider: LLM provider to use ("groq" or "claude")
        collection_context: Enquiry status injected into the prompt

    Returns:
        Dict with: reply, confidence, action, sources, provider
    """
    if conversation_history is None:
        conversation_history = []

    # Get the requested LLM provider
    llm = get_llm(provider)

    # Step 1: Retrieve relevant chunks
    chunks = search_knowledge_base(
        query=question,
        top_k=settings.rag_top_k,
        category_filter=category_filter,
        destination_filter=destination_filter,
    )

    # Step 2: Compute confidence
    confidence = compute_confidence(chunks)
    action = confidence_action(confidence)

    # Step 3: Build prompts
    system_prompt = _load_prompt("system")
    rag_template = _load_prompt("rag_query")

    context = _build_context(chunks)
    history = _build_history(conversation_history)

    user_prompt = rag_template.format(
        context=context,
        history=history,
        question=question,
        collection_context=collection_context,
    )

    # Step 4: Add caveat instruction if medium confidence
    # Skip escalation/caveat overrides when actively collecting enquiry details
    # — the collection context already tells the LLM what to ask next.
    is_collecting = collection_context and ("ENQUIRY STATUS" in collection_context and "exploring" not in collection_context.lower())

    if not is_collecting:
        if action == "respond_with_caveat":
            user_prompt += (
                "\n\nNote: Your confidence in this information is moderate. "
                "Briefly suggest the client confirm details with the team "
                "at +27 213 002 325 or mahlatini.com/contact — but keep it natural, "
                "not apologetic."
            )
        elif action == "escalate":
            # Low confidence — generate a graceful handoff message
            user_prompt = (
                "You don't have enough information to answer this confidently. "
                "Let the client know warmly and suggest they speak with "
                "one of Mahlatini's travel experts for the best advice. "
                "Keep it to 1-2 sentences.\n\n"
                f"CLIENT: {question}"
            )

    # Step 5: Determine temperature and penalties
    if action == "respond":
        temperature = settings.llm_temperature_chat
    else:
        temperature = settings.llm_temperature_caveat

    # Step 6: Generate response via selected provider
    try:
        reply = await llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=settings.llm_max_tokens_chat,
            frequency_penalty=settings.llm_frequency_penalty,
            presence_penalty=settings.llm_presence_penalty,
        )
    except Exception as e:
        logger.error(f"[{llm.provider_name}] LLM generation failed: {e}")
        reply = (
            "I'm having a moment — sorry about that. "
            "You can reach our travel experts directly at +27 213 002 325 "
            "and they'll take great care of you."
        )
        confidence = 0.0
        action = "escalate"

    # Step 7: Post-process for brevity and conversational tone
    try:
        reply = await compress_response(
            response=reply,
            sentence_limit=settings.llm_compress_sentence_limit,
            provider=provider,
        )
    except Exception as e:
        logger.warning(f"Response compression failed, using original: {e}")

    # Compile sources
    sources = [
        {
            "title": c.get("page_title", ""),
            "url": c.get("source_url", ""),
            "score": c.get("score", 0),
        }
        for c in chunks[:3]
    ]

    return {
        "reply": reply,
        "confidence": confidence,
        "action": action,
        "sources": sources,
        "chunks_retrieved": len(chunks),
        "provider": llm.provider_name,
    }
