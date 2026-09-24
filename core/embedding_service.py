"""One serialized ONNX model/cache per model name, shared by desktop consumers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import os
import tempfile
import numpy as np

MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
_worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-embeddings')
_models = {}
_memory = {}
_directory = Path(__file__).resolve().parents[1] / 'data' / 'embedding_cache'


def _load(name):
    if name not in _models:
        from fastembed import TextEmbedding
        _models[name] = TextEmbedding(model_name=name)
    return _models[name]


def model(name=MODEL):
    return _worker.submit(_load, name).result()


def _embed(text, name):
    key = hashlib.sha256(f'v2-fulltext-model-aware\0{name}\0{text}'.encode()).hexdigest()
    if key in _memory:
        return _memory[key]
    path = _directory / (key + '.npy')
    try:
        vector = np.load(path, allow_pickle=False)
        if vector.ndim != 1 or not np.isfinite(vector).all():
            raise ValueError('Invalid embedding cache')
    except (OSError, ValueError, EOFError):
        vector = next(_load(name).embed([text]))
        _directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(dir=_directory, suffix='.npy')
            with os.fdopen(fd, 'wb') as target:
                np.save(target, vector)
            os.replace(temporary, path)
        except OSError:
            pass
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    if len(_memory) >= 512:
        _memory.pop(next(iter(_memory)))
    _memory[key] = vector
    return vector


def embed(text, name=MODEL):
    return _worker.submit(_embed, text, name).result()
