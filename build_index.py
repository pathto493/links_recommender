"""Build a reproducible, database-free semantic index from YouTube CSV titles."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def youtube_id(url: str) -> str | None:
    try:
        u = urlparse(url.strip())
        host = (u.hostname or "").lower()
        parts = [p for p in u.path.split("/") if p]
        if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
            if u.path == "/watch":
                candidate = parse_qs(u.query).get("v", [""])[0]
            elif parts and parts[0] in ("shorts", "embed", "live") and len(parts) > 1:
                candidate = parts[1]
            else:
                return None
        elif host in ("youtu.be", "www.youtu.be") and parts:
            candidate = parts[0]
        else:
            return None
        return candidate if len(candidate) == 11 and all(c.isalnum() or c in "-_" for c in candidate) else None
    except (ValueError, AttributeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Exported YouTube CSV with Title and URL headers")
    parser.add_argument("--out", default="artifacts")
    parser.add_argument("--device", choices=["cpu", "mps"], default="cpu")
    args = parser.parse_args()
    source = Path(args.csv)
    raw = source.read_bytes()
    by_id = {}
    with source.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Title", "URL"}
        if not required.issubset(set(reader.fieldnames or [])):
            raise SystemExit(f"CSV must have Title and URL headers; found: {reader.fieldnames}")
        for row in reader:
            title = (row.get("Title") or "").strip()
            url = (row.get("URL") or "").strip()
            vid = youtube_id(url)
            if not title or not vid:
                continue
            by_id.setdefault(vid, {"video_id": vid, "title": title})
    records = list(by_id.values())
    if not records:
        raise SystemExit("No usable titled YouTube video records found")
    print(f"Usable unique videos: {len(records)}")
    print(f"Loading embedding model: {MODEL} on {args.device}")
    model = SentenceTransformer(MODEL, device=args.device)
    vectors = model.encode([r["title"] for r in records], normalize_embeddings=True,
                           convert_to_numpy=True, show_progress_bar=True, batch_size=16)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "embeddings.npy", vectors.astype("float32"), allow_pickle=False)
    (out / "catalog.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({
        "model": MODEL, "catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "video_count": len(records), "dimensions": int(vectors.shape[1]),
        "index_format": "normalized-f32-cosine-v1"
    }, indent=2), encoding="utf-8")
    print(f"Built {out}/ with {len(records)} records. Model weights download/cache separately.")

if __name__ == "__main__":
    main()
