"""Yorkshire Terrier Expert Chatbot — fake LLM for eval demos.

Simulates a RAG chatbot with realistic imperfections:
- Sometimes misses keywords (simulates retrieval failures)
- Occasionally adds irrelevant info (simulates hallucination)
- Response quality varies (simulates LLM non-determinism)
"""

from __future__ import annotations

import random

# Knowledge base — what a real RAG system would retrieve
YORKSHIRE_FACTS = {
    "size": "Yorkshire Terriers typically weigh between 2-3 kg. They come in teacup, mini, and standard sizes.",
    "grooming": "Yorkies with long coats need daily brushing. Seniors over 6 years need extra grooming care. Regular baths every 2-3 weeks.",
    "temperament": "Yorkies are bold, confident, and affectionate. Despite their small size, they are courageous and sometimes stubborn.",
    "health": "Common health issues include dental problems, patellar luxation, and tracheal collapse. Regular vet checkups recommended.",
    "training": "Yorkies are intelligent but can be stubborn. Positive reinforcement works best. Start training early for best results.",
    "diet": "Small breed formula recommended. Feed 2-3 small meals per day. Avoid chocolate, grapes, and onions.",
    "exercise": "30 minutes of daily exercise is sufficient. Short walks and indoor play. Avoid extreme temperatures.",
    "jobs": "Historically bred as ratters. Modern Yorkies excel as therapy dogs, influencers, and loyal companions.",
    "puppies": "Yorkshire puppies need extra care until 12 months. Socialization is critical in the first 6 months.",
    "seniors": "Senior Yorkies (8+ years) may slow down. Adjust exercise and diet. More frequent vet visits recommended.",
}


def yorkshire_chatbot(question: str) -> str:  # noqa: PLR0912
    """Fake chatbot that answers questions about Yorkshire Terriers.

    Simulates a RAG pipeline: keyword matching → fact retrieval → response generation.
    No LLM calls — pure string matching for deterministic eval testing.
    """
    question_lower = question.lower()

    # Find relevant facts by keyword matching
    relevant_facts: list[str] = []
    for topic, fact in YORKSHIRE_FACTS.items():
        if topic in question_lower or any(
            word in question_lower for word in topic.split()
        ):
            relevant_facts.append(fact)

    # Check for specific question patterns
    if "weight" in question_lower or "how heavy" in question_lower:
        relevant_facts.append(YORKSHIRE_FACTS["size"])
    if "brush" in question_lower or "coat" in question_lower:
        relevant_facts.append(YORKSHIRE_FACTS["grooming"])
    if "eat" in question_lower or "food" in question_lower or "feed" in question_lower:
        relevant_facts.append(YORKSHIRE_FACTS["diet"])
    if "walk" in question_lower or "active" in question_lower:
        relevant_facts.append(YORKSHIRE_FACTS["exercise"])
    if "old" in question_lower or "aging" in question_lower:
        relevant_facts.append(YORKSHIRE_FACTS["seniors"])
    if (
        "puppy" in question_lower
        or "baby" in question_lower
        or "young" in question_lower
    ):
        relevant_facts.append(YORKSHIRE_FACTS["puppies"])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_facts = []
    for fact in relevant_facts:
        if fact not in seen:
            seen.add(fact)
            unique_facts.append(fact)

    if not unique_facts:
        return "I'm not sure about that. I specialize in Yorkshire Terrier care and health."

    response = " ".join(unique_facts)

    # Simulate LLM imperfections
    # ~20% chance: drop a sentence (simulates retrieval miss)
    if random.random() < 0.2 and ". " in response:  # noqa: S311, PLR2004
        sentences = response.split(". ")
        drop_idx = random.randint(0, len(sentences) - 1)  # noqa: S311
        sentences.pop(drop_idx)
        response = ". ".join(sentences)

    # ~10% chance: add irrelevant filler (simulates rambling)
    if random.random() < 0.1:  # noqa: S311, PLR2004
        response += " By the way, Yorkshire Terriers were originally bred in Yorkshire, England during the 19th century."

    # ~5% chance: return a vague non-answer (simulates confusion)
    if random.random() < 0.05:  # noqa: S311, PLR2004
        response = (
            "That's a great question about Yorkies! There are many factors to consider."
        )

    return response
