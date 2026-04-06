"""Translation service for FA↔EN article titles and summaries.

Uses Helsinki-NLP opus-mt models (self-hosted, free) for translations.
Falls back to a simple pass-through if models aren't available.
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded models
_fa_to_en_model = None
_fa_to_en_tokenizer = None
_en_to_fa_model = None
_en_to_fa_tokenizer = None
_models_checked = False
_models_available = False


def _check_models():
    """Check if translation models are available."""
    global _models_checked, _models_available
    if _models_checked:
        return _models_available
    _models_checked = True
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: F401
        _models_available = True
        return True
    except ImportError:
        logger.warning(
            "transformers not installed — translation will be unavailable. "
            "Install with: pip install -e '.[nlp]'"
        )
        _models_available = False
        return False


def _load_fa_to_en():
    """Lazy-load the FA→EN translation model."""
    global _fa_to_en_model, _fa_to_en_tokenizer
    if _fa_to_en_model is not None:
        return _fa_to_en_model, _fa_to_en_tokenizer

    if not _check_models():
        return None, None

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_name = "Helsinki-NLP/opus-mt-fa-en"
    logger.info(f"Loading translation model: {model_name}")
    _fa_to_en_tokenizer = AutoTokenizer.from_pretrained(model_name)
    _fa_to_en_model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    logger.info("FA→EN translation model loaded")
    return _fa_to_en_model, _fa_to_en_tokenizer


def _load_en_to_fa():
    """Lazy-load the EN→FA translation model."""
    global _en_to_fa_model, _en_to_fa_tokenizer
    if _en_to_fa_model is not None:
        return _en_to_fa_model, _en_to_fa_tokenizer

    if not _check_models():
        return None, None

    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_name = "Helsinki-NLP/opus-mt-en-fa"
    logger.info(f"Loading translation model: {model_name}")
    _en_to_fa_tokenizer = AutoTokenizer.from_pretrained(model_name)
    _en_to_fa_model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
    logger.info("EN→FA translation model loaded")
    return _en_to_fa_model, _en_to_fa_tokenizer


def translate_fa_to_en(text: str) -> str | None:
    """Translate Persian text to English.

    Returns None if translation is unavailable.
    """
    model, tokenizer = _load_fa_to_en()
    if model is None:
        return None

    try:
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
        outputs = model.generate(**inputs, max_length=512)
        translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return translated
    except Exception as e:
        logger.error(f"FA→EN translation failed: {e}")
        return None


def translate_en_to_fa(text: str) -> str | None:
    """Translate English text to Persian.

    Returns None if translation is unavailable.
    """
    model, tokenizer = _load_en_to_fa()
    if model is None:
        return None

    try:
        inputs = tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
        outputs = model.generate(**inputs, max_length=512)
        translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
        return translated
    except Exception as e:
        logger.error(f"EN→FA translation failed: {e}")
        return None


def translate_batch_fa_to_en(texts: list[str]) -> list[str | None]:
    """Translate a batch of Persian texts to English."""
    model, tokenizer = _load_fa_to_en()
    if model is None:
        return [None] * len(texts)

    try:
        inputs = tokenizer(
            texts, return_tensors="pt", max_length=512,
            truncation=True, padding=True,
        )
        outputs = model.generate(**inputs, max_length=512)
        translations = [
            tokenizer.decode(out, skip_special_tokens=True)
            for out in outputs
        ]
        return translations
    except Exception as e:
        logger.error(f"Batch FA→EN translation failed: {e}")
        return [None] * len(texts)
