"""Lazy-loaded model + portable file index. No user input is persisted."""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent
ART = ROOT / "artifacts"

@lru_cache(maxsize=1)
def resources():
    manifest = json.loads((ART / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((ART / "catalog.json").read_text(encoding="utf-8"))
    vectors = np.load(ART / "embeddings.npy", allow_pickle=False)
    if len(catalog) != len(vectors) or manifest["video_count"] != len(catalog):
        raise ValueError("Index/catalog inconsistency; rebuild artifacts")
    model = SentenceTransformer(manifest["model"], device="cpu")
    return manifest, catalog, vectors, model

def recommend(text: str, top_k: int = 5):
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("text must contain 1–2000 characters")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 10:
        raise ValueError("top_k must be an integer between 1 and 10")
    manifest, catalog, vectors, model = resources()
    q = model.encode([text.strip()], normalize_embeddings=True, convert_to_numpy=True)[0]
    scores = vectors @ q
    best = np.argsort(-scores)[:top_k]
    return {
        "recommendations": [
            {"video_id": catalog[int(i)]["video_id"],
             "title": catalog[int(i)]["title"],
             "score": round(float(scores[i]), 4)} for i in best
        ],
        "model_version": manifest["model"],
        "catalog_version": manifest["catalog_sha256"][:16],
        "match_basis": "video titles only"
    }
