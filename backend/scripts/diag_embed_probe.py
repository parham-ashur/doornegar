"""Probe: does OpenAI embedding actually work in this environment?

If every article has a zero vector, either the API key path is broken
or the OpenAI embedding endpoint is throwing. This tests the call
directly, bypassing the pipeline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    from app.config import settings
    from app.nlp.embeddings import generate_embedding, generate_embeddings_batch

    print(f"openai_api_key set: {bool(settings.openai_api_key)}")
    print(f"  length: {len(settings.openai_api_key or '')}")
    print(f"  prefix: {(settings.openai_api_key or '')[:10]}...")

    sample = "آزمایش تولید بردار برای چند جمله فارسی"
    print(f"\nCalling generate_embedding(...) on: {sample!r}")
    try:
        vec = generate_embedding(sample)
        nonzero = sum(1 for v in vec if v != 0.0)
        print(f"  len={len(vec)}  nonzero_count={nonzero}  first5={vec[:5]}")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")

    print("\nCalling generate_embeddings_batch([...]) with 3 Farsi texts")
    try:
        vecs = generate_embeddings_batch([
            "آزمایش یک",
            "آزمایش دو",
            "آزمایش سه",
        ])
        for i, v in enumerate(vecs):
            nz = sum(1 for x in v if x != 0.0)
            print(f"  [{i}] len={len(v)}  nonzero_count={nz}  first3={v[:3]}")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
