from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

KEYWORD_TAG_MAP: dict[str, list[str]] = {
    "Artificial Intelligence": [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "neural network", "neural", "nlp", "natural language", "computer vision",
        "robotics", "autonomous", "reinforcement learning", "generative",
        "transformer", "large language model", "llm",
    ],
    "Health / Medicine": [
        "biomedical", "clinical", "patient", "disease", "health", "medical",
        "pharmaceutical", "epidemi", "therapy", "diagnostic", "genomic",
        "mental health", "substance", "aging", "dementia", "alzheimer",
    ],
    "Infrastructure": [
        "civil", "bridge", "transportation", "urban", "infrastructure",
        "highway", "construction", "building", "structural", "water system",
    ],
    "Environment / Climate": [
        "climate", "environment", "sustainability", "renewable", "emission",
        "conservation", "ecology", "biodiversity", "pollution", "carbon",
        "geoscience", "atmospheric",
    ],
    "Education": [
        "education", "student", "curriculum", "stem", "pedagogy",
        "k-12", "k12", "undergraduate", "graduate", "fellowship",
        "training", "workforce development",
    ],
    "Agriculture": [
        "agriculture", "crop", "farming", "livestock", "soil",
        "food security", "irrigation", "agronomic", "horticulture",
    ],
    "Cybersecurity": [
        "cybersecurity", "cyber", "encryption", "malware", "phishing",
        "network security", "vulnerability", "threat",
    ],
    "Space / Aerospace": [
        "space", "aerospace", "satellite", "nasa", "orbital",
        "rocket", "launch vehicle", "astro",
    ],
    "Energy": [
        "energy", "solar", "wind power", "nuclear", "battery",
        "grid", "power generation", "fuel cell", "hydrogen",
    ],
    "Humanities / Arts": [
        "humanities", "arts", "culture", "heritage", "museum",
        "literature", "history", "archaeology", "language", "music",
        "dance", "theatre", "theater", "manuscript", "digitization",
    ],
    "Social Sciences": [
        "social", "sociology", "psychology", "economics", "political",
        "behavioral", "demographic", "community", "equity", "justice",
    ],
}

TFIDF_CATEGORY_DESCRIPTIONS = {
    "Artificial Intelligence": (
        "Research in artificial intelligence, machine learning, deep learning, "
        "neural networks, natural language processing, computer vision, robotics, "
        "autonomous systems, and generative AI models."
    ),
    "Health / Medicine": (
        "Biomedical research, clinical trials, patient care, disease prevention, "
        "public health, pharmaceutical development, mental health, genomics, "
        "epidemiology, and medical diagnostics."
    ),
    "Infrastructure": (
        "Civil engineering, transportation systems, urban planning, bridge design, "
        "construction technology, water systems, and structural engineering."
    ),
    "Environment / Climate": (
        "Climate change research, environmental science, renewable energy, "
        "carbon emissions, conservation, ecology, biodiversity, and pollution control."
    ),
    "Education": (
        "Educational research, STEM education, curriculum development, K-12 programs, "
        "higher education, fellowships, workforce development, and pedagogy."
    ),
    "Agriculture": (
        "Agricultural research, crop science, farming technology, food security, "
        "soil science, livestock management, irrigation, and horticulture."
    ),
    "Cybersecurity": (
        "Cybersecurity research, network security, encryption, threat detection, "
        "malware analysis, vulnerability assessment, and cyber defense."
    ),
    "Space / Aerospace": (
        "Space exploration, aerospace engineering, satellite technology, "
        "orbital mechanics, launch vehicles, and planetary science."
    ),
    "Energy": (
        "Energy research, solar power, wind energy, nuclear energy, battery technology, "
        "smart grids, hydrogen fuel cells, and power generation."
    ),
    "Humanities / Arts": (
        "Humanities research, arts and culture, cultural heritage preservation, "
        "museum studies, literature, history, archaeology, music, dance, theatre, "
        "manuscript digitization, and language studies."
    ),
    "Social Sciences": (
        "Social science research, sociology, psychology, economics, political science, "
        "behavioral studies, demographics, community development, equity, and justice."
    ),
}


def tag_by_keywords(title: str, description: str) -> list[str]:
    combined = (title + " " + description).lower()
    matched_tags = []

    for tag, keywords in KEYWORD_TAG_MAP.items():
        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, combined):
                matched_tags.append(tag)
                break

    return sorted(set(matched_tags))


def tag_by_tfidf(
    title: str,
    description: str,
    threshold: float = 0.08,
) -> list[str]:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        logger.warning("scikit-learn not installed; skipping TF-IDF tagging")
        return []

    combined_text = f"{title} {description}"
    if len(combined_text.strip()) < 10:
        return []

    categories = list(TFIDF_CATEGORY_DESCRIPTIONS.keys())
    corpus = list(TFIDF_CATEGORY_DESCRIPTIONS.values())
    corpus.append(combined_text)

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=5000,
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)

    doc_vector = tfidf_matrix[-1]
    category_vectors = tfidf_matrix[:-1]

    similarities = cosine_similarity(doc_vector, category_vectors).flatten()

    matched = []
    for idx, score in enumerate(similarities):
        if score >= threshold:
            matched.append((categories[idx], score))

    matched.sort(key=lambda x: x[1], reverse=True)
    return [cat for cat, _ in matched]


def apply_tags(
    title: str,
    description: str,
    use_nlp: bool = True,
    tfidf_threshold: float = 0.08,
) -> list[str]:
    keyword_tags = tag_by_keywords(title, description)

    if use_nlp:
        nlp_tags = tag_by_tfidf(title, description, threshold=tfidf_threshold)
        all_tags = list(dict.fromkeys(keyword_tags + nlp_tags))
    else:
        all_tags = keyword_tags

    return all_tags
