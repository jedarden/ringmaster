"""Match new task candidates against existing tasks.

Uses text similarity to find duplicates or related tasks that could
be updated instead of creating new ones.
"""

import re
from collections import Counter

from ringmaster.domain import Epic, Subtask, Task


def tokenize(text: str) -> list[str]:
    """Tokenize text into words for comparison."""
    # Lowercase and extract words
    words = re.findall(r"\b\w+\b", text.lower())

    # Filter out common stop words
    stop_words = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "must", "shall",
        "this", "that", "these", "those", "it", "its", "i", "we", "you",
        "they", "he", "she", "all", "each", "every", "both", "any", "some",
    }

    return [w for w in words if w not in stop_words and len(w) > 2]


def jaccard_similarity(tokens1: list[str], tokens2: list[str]) -> float:
    """Calculate Jaccard similarity between two token lists."""
    if not tokens1 or not tokens2:
        return 0.0

    set1 = set(tokens1)
    set2 = set(tokens2)

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def cosine_similarity(tokens1: list[str], tokens2: list[str]) -> float:
    """Calculate cosine similarity using term frequency."""
    if not tokens1 or not tokens2:
        return 0.0

    counter1 = Counter(tokens1)
    counter2 = Counter(tokens2)

    # Get all unique terms
    all_terms = set(counter1.keys()) | set(counter2.keys())

    # Calculate dot product and magnitudes
    dot_product = sum(counter1[term] * counter2[term] for term in all_terms)
    magnitude1 = sum(v ** 2 for v in counter1.values()) ** 0.5
    magnitude2 = sum(v ** 2 for v in counter2.values()) ** 0.5

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)


def similarity_score(text1: str, text2: str) -> float:
    """Calculate overall similarity between two texts.

    Uses a combination of Jaccard and Cosine similarity.
    Returns a score between 0 and 1.
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    if not tokens1 or not tokens2:
        return 0.0

    jaccard = jaccard_similarity(tokens1, tokens2)
    cosine = cosine_similarity(tokens1, tokens2)

    # Weighted average (cosine tends to be more accurate for longer texts)
    return 0.4 * jaccard + 0.6 * cosine


def find_matching_task(
    candidate_text: str,
    existing_tasks: list[Task | Epic | Subtask],
    threshold: float = 0.6,
) -> tuple[Task | Epic | Subtask | None, float]:
    """Find an existing task that matches the candidate text.

    Returns (matching_task, similarity_score) or (None, 0) if no match found.
    """
    best_match: Task | Epic | Subtask | None = None
    best_score = 0.0

    for task in existing_tasks:
        # Compare against title and description
        task_text = task.title
        if task.description:
            task_text += " " + task.description

        score = similarity_score(candidate_text, task_text)

        if score > best_score and score >= threshold:
            best_score = score
            best_match = task

    return best_match, best_score


def find_related_tasks(
    candidate_text: str,
    existing_tasks: list[Task | Epic | Subtask],
    threshold: float = 0.3,
    max_results: int = 5,
) -> list[tuple[Task | Epic | Subtask, float]]:
    """Find existing tasks related to the candidate text.

    Returns a list of (task, score) tuples sorted by score descending.
    Useful for suggesting dependencies or context.
    """
    scored_tasks: list[tuple[Task | Epic | Subtask, float]] = []

    for task in existing_tasks:
        task_text = task.title
        if task.description:
            task_text += " " + task.description

        score = similarity_score(candidate_text, task_text)

        if score >= threshold:
            scored_tasks.append((task, score))

    # Sort by score descending and limit results
    scored_tasks.sort(key=lambda x: x[1], reverse=True)
    return scored_tasks[:max_results]
