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


# ─── Boilerplate stripping ────────────────────────────────────────────
# Article bodies often carry text that has nothing to do with the
# article topic: scrape-failure placeholders ("Transferring to the
# website..."), comments-section chrome, recurring image captions on
# unrelated articles. Without stripping, this content poisons the
# embedding and pulls unrelated pieces toward common boilerplate-
# driven cosines. Observed in the 2026-04-26 embedder comparison: three
# Iran International articles about wholly different topics matched
# the same wrong story because they shared a recurring image caption.

# Universal patterns. Order matters: greedy comments-section trailers
# match before line-anchored meta strips would have swallowed them.
_UNIVERSAL_BOILERPLATE_PATTERNS = [
    # Scrape-failure placeholder (Tasnim, khabaronline, etc.). Match
    # the literal English phrase, the Persian variant, and the Persian
    # form using Arabic presentation glyphs (ﺣ instead of ح) since
    # some HTML scrapes return the rendered ligatures.
    re.compile(r"Transferring to the website\.\.\.", re.IGNORECASE),
    re.compile(r"در\s*[\u062Dﺡﺢﺣﺤ]ال\s*انتقال\s*به\s*سایت[\s\S]*$"),
    # Tabnak-family comments-section trailing block. Anchored on the
    # «گزارش خطا» link that always precedes the comments scaffold.
    re.compile(r"گزارش\s+خطا[\s\S]*"),
    # Article-meta lines that show up mid-body in some sources.
    re.compile(r"^\s*کد\s+خبر:?\s*[\d۰-۹]+\s*$", re.MULTILINE),
    re.compile(r"^\s*\|\s*\|\s*[\d۰-۹]+\s+بازدید\s*$", re.MULTILINE),
    re.compile(r"^\s*تعداد\s+بازدید:?.*$", re.MULTILINE),
]

# Per-source patterns. Add as you observe specific outlets bleeding
# templated content into article bodies.
_SOURCE_BOILERPLATE_PATTERNS: dict[str, list] = {
    # Iran International ships an image caption that gets concatenated
    # into many article bodies regardless of topic. Match the templated
    # prefix and stop at the first sentence terminator so we swallow the
    # caption without clipping the legit text that follows.
    "iran-international": [
        re.compile(r"تصاویر\s+رسیده\s+به\s+ایران\s+اینترنشنال[^.؛\n]*[.؛]"),
    ],
}


def strip_boilerplate(text: str | None, source_slug: str | None = None) -> str:
    """Remove scrape placeholders, comments-section chrome, and
    per-source recurring captions from an article body before it
    feeds the embedder.

    Empty input returns empty. Universal patterns apply to every
    article; per-source patterns are layered on when ``source_slug``
    matches an entry in ``_SOURCE_BOILERPLATE_PATTERNS``.

    Callers should treat a very short return value (< ~80 chars) as a
    signal that the article had no real content — better to embed
    title only than to embed a one-sentence remnant.
    """
    if not text:
        return ""
    out = text
    for pat in _UNIVERSAL_BOILERPLATE_PATTERNS:
        out = pat.sub("", out)
    if source_slug:
        for pat in _SOURCE_BOILERPLATE_PATTERNS.get(source_slug, []):
            out = pat.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


def extract_text_for_embedding(
    title: str,
    body: str | None,
    max_tokens: int = 512,
    source_slug: str | None = None,
) -> str:
    """Prepare text for embedding generation.

    Combines title and body text, truncated to approximately
    max_tokens words. When ``source_slug`` is provided, runs the body
    through ``strip_boilerplate`` first so source-specific noise
    doesn't pollute the resulting vector.
    """
    parts = [normalize(title)]
    if body:
        cleaned = strip_boilerplate(body, source_slug=source_slug) if source_slug else body
        normalized_body = normalize(cleaned)
        words = tokenize_words(normalized_body)
        # Title gets priority, body fills remaining space
        remaining = max_tokens - len(tokenize_words(parts[0]))
        if remaining > 0:
            body_truncated = " ".join(words[:remaining])
            parts.append(body_truncated)

    return " ".join(parts)
