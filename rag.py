"""Tiny local RAG: markdown notes -> chunks -> embeddings -> cosine search.
No vector DB needed; a few trails fit in a JSON file."""
import hashlib
import json
import math
import re

import ollama

import config


def _load_chunks():
    """Split each trail file into chunks, one per '## ' section."""
    chunks = []
    for path in sorted(config.DATA_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
            heading, _, body = section.partition("\n")
            chunks.append({
                "source": path.name,
                "trail": title,
                "text": f"{title} - {heading.strip()}\n{body.strip()}",
            })
    return chunks


def _fingerprint(chunks):
    joined = "".join(c["text"] for c in chunks) + config.EMBED_MODEL
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _embed(texts):
    return ollama.embed(model=config.EMBED_MODEL, input=texts)["embeddings"]


def build_index():
    """Load the cached index, or rebuild it if the notes changed."""
    chunks = _load_chunks()
    if not chunks:
        raise SystemExit(f"No .md notes found in {config.DATA_DIR}")

    fp = _fingerprint(chunks)
    if config.INDEX_FILE.exists():
        cached = json.loads(config.INDEX_FILE.read_text(encoding="utf-8"))
        if cached.get("fingerprint") == fp:
            return cached["chunks"]

    print("Indexing trail notes (first run or notes changed)...")
    vectors = _embed([c["text"] for c in chunks])
    for chunk, vec in zip(chunks, vectors):
        chunk["vector"] = vec
    config.INDEX_FILE.write_text(
        json.dumps({"fingerprint": fp, "chunks": chunks}), encoding="utf-8"
    )
    return chunks


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def search(query, index, k=config.TOP_K):
    q_vec = _embed([query])[0]
    scored = sorted(index, key=lambda c: _cosine(q_vec, c["vector"]), reverse=True)
    return scored[:k]