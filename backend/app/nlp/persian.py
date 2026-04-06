"""Persian text processing pipeline using hazm.

Provides normalization, tokenization, lemmatization, and keyword extraction
for Persian (Farsi) text from news articles.
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# Try to import hazm — it's an optional dependency (in [nlp] extras)
try:
    from hazm import Lemmatizer, Normalizer, SentenceTokenizer, WordTokenizer

    _normalizer = Normalizer()
    _word_tokenizer = WordTokenizer()
    _sentence_tokenizer = SentenceTokenizer()
    _lemmatizer = Lemmatizer()
    HAZM_AVAILABLE = True
except ImportError:
    logger.warning("hazm not installed — Persian NLP features will use fallback processing")
    HAZM_AVAILABLE = False


# Common Persian stopwords for keyword extraction
PERSIAN_STOPWORDS = {
    "و", "در", "به", "از", "که", "این", "را", "با", "است", "برای",
    "آن", "یک", "خود", "تا", "بر", "هم", "نیز", "گفت", "اما", "یا",
    "هر", "شد", "می", "بود", "ها", "های", "شده", "کرد", "بین", "پس",
    "باید", "دو", "سه", "چند", "همه", "وی", "ای", "شود", "کرده",
    "نیست", "بودن", "شدن", "کردن", "داشتن", "دارد", "آنها", "ما",
    "او", "من", "هستند", "باشد", "همین", "بسیار", "پیش", "زیرا",
    "چون", "اگر", "مگر", "ولی", "کنند", "کنید", "بسیاری", "دارند",
    "درباره", "نسبت", "توسط", "طی", "ضمن", "هنگام",
}


def normalize(text: str) -> str:
    """Normalize Persian text for consistent processing.

    Uses hazm normalizer if available, otherwise applies basic normalization.
    """
    if not text:
        return ""

    if HAZM_AVAILABLE:
        text = _normalizer.normalize(text)
    else:
        # Fallback: basic Arabic→Persian char mapping
        replacements = {
            "\u0643": "\u06A9",  # Arabic kaf → Persian kaf
            "\u064A": "\u06CC",  # Arabic yeh → Persian yeh
            "\u0649": "\u06CC",  # Arabic alef maksura → Persian yeh
        }
        for arabic, persian in replacements.items():
            text = text.replace(arabic, persian)
        text = unicodedata.normalize("NFC", text)

    # Clean up whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    if not text:
        return []
    if HAZM_AVAILABLE:
        return _sentence_tokenizer.tokenize(text)
    # Fallback: split on Persian/Arabic sentence endings
    return [s.strip() for s in re.split(r"[.!?؟۔]\s+", text) if s.strip()]


def tokenize_words(text: str) -> list[str]:
    """Split text into words."""
    if not text:
        return []
    if HAZM_AVAILABLE:
        return _word_tokenizer.tokenize(text)
    # Fallback: simple whitespace + punctuation split
    return [w for w in re.split(r"[\s\u200c,.;:!?؟«»()\\[\\]{}\u060c\u061b]+", text) if w]


def lemmatize(word: str) -> str:
    """Get the lemma (base form) of a Persian word."""
    if HAZM_AVAILABLE:
        return _lemmatizer.lemmatize(word)
    return word


def extract_keywords(text: str, max_keywords: int = 15) -> list[str]:
    """Extract keywords from Persian text using frequency-based approach.

    Returns most frequent non-stopword lemmatized tokens.
    """
    if not text:
        return []

    normalized = normalize(text)
    words = tokenize_words(normalized)

    # Lemmatize and filter stopwords
    filtered = []
    for word in words:
        if len(word) < 2:
            continue
        if word in PERSIAN_STOPWORDS:
            continue
        lemma = lemmatize(word)
        if lemma in PERSIAN_STOPWORDS:
            continue
        # Skip pure numbers
        if re.match(r"^[\d۰-۹]+$", lemma):
            continue
        filtered.append(lemma)

    # Count frequencies
    freq: dict[str, int] = {}
    for word in filtered:
        freq[word] = freq.get(word, 0) + 1

    # Sort by frequency, return top N
    sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [word for word, _ in sorted_words[:max_keywords]]


def extract_text_for_embedding(title: str, body: str | None, max_tokens: int = 512) -> str:
    """Prepare text for embedding generation.

    Combines title and body text, truncated to approximately max_tokens words.
    """
    parts = [normalize(title)]
    if body:
        normalized_body = normalize(body)
        words = tokenize_words(normalized_body)
        # Title gets priority, body fills remaining space
        remaining = max_tokens - len(tokenize_words(parts[0]))
        if remaining > 0:
            body_truncated = " ".join(words[:remaining])
            parts.append(body_truncated)

    return " ".join(parts)
