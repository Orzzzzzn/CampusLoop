"""Hybrid retrieval over live ride records and local Markdown, then local Ollama generation."""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
import urllib.error
import urllib.request

from .domain import ROOT, Problem, list_trips

LOG = logging.getLogger('campusloop.rag')

def _keep_alive():
    """Keep models resident between requests. -1 = never unload."""
    raw = os.getenv('OLLAMA_KEEP_ALIVE', '-1').strip()
    if raw == '-1':
        return -1
    try:
        return int(raw)
    except ValueError:
        return raw


KEEP_ALIVE = _keep_alive()


class Ollama:
    def __init__(self, base_url=None):
        self.base = (base_url or os.getenv('OLLAMA_URL', 'http://localhost:11434')).rstrip('/')
        # 0.5b is much faster on CPU Docker than 1.5b; override with CHAT_MODEL=qwen2.5:1.5b for quality.
        self.chat_model = os.getenv('CHAT_MODEL', 'qwen2.5:0.5b')
        self.embed_model = os.getenv('EMBED_MODEL', 'nomic-embed-text:v1.5')
        self.num_predict = int(os.getenv('RAG_NUM_PREDICT', '140'))
        self.num_ctx = int(os.getenv('RAG_NUM_CTX', '1024'))
        self._ready = None

    def post(self, path, payload, timeout=90):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            self._ready = False
            raise Problem(
                503,
                'The local AI model is not ready. Check the Ollama and model-init containers, '
                'or wait for model downloads to finish.',
            ) from exc

    def get(self, path, timeout=5):
        request = urllib.request.Request(self.base + path, method='GET')
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise Problem(
                503,
                'The local AI model is not ready. Check the Ollama and model-init containers.',
            ) from exc

    def ensure_ready(self):
        if self._ready is True:
            return
        tags = self.get('/api/tags')
        names = {m.get('name') or m.get('model') for m in tags.get('models', []) if m}

        def present(wanted):
            family = wanted.split(':', 1)[0]
            return wanted in names or any(n == wanted or (n and n.split(':', 1)[0] == family) for n in names)

        if not present(self.chat_model) or not present(self.embed_model):
            raise Problem(
                503,
                'Required Ollama models are still downloading. Wait for the model-init container to finish, then try again.',
            )
        self._ready = True

    def embed(self, texts):
        self.ensure_ready()
        vectors = self.post(
            '/api/embed',
            {'model': self.embed_model, 'input': texts, 'truncate': True, 'keep_alive': KEEP_ALIVE},
            timeout=60,
        )['embeddings']
        if len(vectors) != len(texts) or not vectors or not all(
            isinstance(v, list) and v and all(type(x) in (int, float) and math.isfinite(x) for x in v) for v in vectors
        ):
            raise Problem(502, 'Embedding service returned invalid vectors.')
        if len({len(v) for v in vectors}) != 1:
            raise Problem(502, 'Embedding dimensions do not match.')
        return vectors

    def generate(self, question, contexts):
        self.ensure_ready()
        # Cap each source so the prompt stays short — large contexts dominate CPU time.
        chunks = []
        for s in contexts:
            body = s['text']
            if len(body) > 420:
                body = body[:420].rsplit(' ', 1)[0] + '…'
            chunks.append(f"[{s['citation']}] {s['title']}\n{body}")
        sources = '\n\n'.join(chunks)
        system = (
            'CampusLoop carpool assistant. Use ONLY the supplied sources. '
            'Never book, approve, cancel, or change data. Cite with [S1], [S2], etc. '
            'If sources are insufficient, say so. Answer briefly in English. '
            'Distinguish available seats from pending or waitlisted requests.'
        )
        result = self.post(
            '/api/generate',
            {
                'model': self.chat_model,
                'system': system,
                'prompt': f'<retrieved_sources>\n{sources}\n</retrieved_sources>\nQuestion: {question}\nAnswer briefly with citations:',
                'stream': False,
                'keep_alive': KEEP_ALIVE,
                'options': {
                    'temperature': 0.1,
                    'num_predict': self.num_predict,
                    'num_ctx': self.num_ctx,
                },
            },
            timeout=90,
        )
        answer = result.get('response', '').strip()
        if not answer:
            raise Problem(502, 'The local model returned an empty answer.')
        valid = {s['citation'] for s in contexts}
        answer = re.sub(r'\[(S\d+)\]', lambda m: m.group(0) if m.group(1) in valid else '', answer)
        return answer

    def warm(self):
        """Load chat weights with the same num_ctx as real asks (ctx changes force a slow reload)."""
        import time
        last = None
        for attempt in range(1, 6):
            try:
                self.ensure_ready()
                self.post(
                    '/api/generate',
                    {
                        'model': self.chat_model,
                        'prompt': 'ping',
                        'stream': False,
                        'keep_alive': KEEP_ALIVE,
                        'options': {'num_predict': 1, 'num_ctx': self.num_ctx},
                    },
                    timeout=180,
                )
                if os.getenv('RAG_SEMANTIC', '0') == '1':
                    self.embed(['warmup'])
                return
            except Problem as exc:
                last = exc
                time.sleep(2 * attempt)
        if last:
            raise last


def tokenize(text):
    return re.findall(r'[\w]+', text.lower())


def bm25(query, documents):
    tokens = [tokenize(doc['text'] + ' ' + doc['title']) for doc in documents]
    average = sum(map(len, tokens)) / max(1, len(tokens)) or 1
    counters = list(map(Counter, tokens))
    scores = [0.0] * len(tokens)
    for term in set(tokenize(query)):
        frequency = sum(term in c for c in counters)
        idf = math.log(1 + (len(tokens) - frequency + 0.5) / (frequency + 0.5))
        for i, c in enumerate(counters):
            count = c[term]
            if count:
                scores[i] += idf * (count * 2.5) / (count + 1.5 * (0.25 + 0.75 * len(tokens[i]) / average))
    return scores


def cosine(a, b):
    if len(a) != len(b):
        return 0
    denominator = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / denominator if denominator else 0


class RAG:
    def __init__(self, store, client=None, knowledge=None, warm=None):
        self.store, self.client = store, client or Ollama()
        self.knowledge = Path(knowledge or ROOT / 'knowledge')
        self.limit = threading.BoundedSemaphore(2)
        if warm is None:
            # Compose sets RAG_WARMUP=1. Default off so unit tests do not hit Ollama.
            warm = os.getenv('RAG_WARMUP', '0') == '1'
        if warm:
            threading.Thread(target=self._warm_models, name='rag-warmup', daemon=True).start()

    def _warm_models(self):
        try:
            self.client.warm()
            LOG.info('Ollama models warmed (keep_alive=%s)', KEEP_ALIVE)
        except Exception as exc:  # noqa: BLE001 — warmup must never break the app
            LOG.warning('Ollama warmup skipped: %s', exc)

    def documents(self, user, criteria):
        docs = []
        for path in sorted(self.knowledge.glob('*.md')):
            content = path.read_text(encoding='utf-8')
            for i, start in enumerate(range(0, len(content), 750)):
                docs.append({
                    'id': f'policy:{path.name}:{i}',
                    'title': path.stem.replace('_', ' '),
                    'text': content[start:start + 900],
                    'kind': 'policy',
                })
        with self.store.read() as db:
            # Cap rides aggressively — BM25 over hundreds of long docs is fine; prompts are not.
            rides = list_trips(db, user['id'], criteria)[:40]
        for r in rides:
            source = {
                'id': f"ride:{r['id']}",
                'title': f"{r['owner_name']} · {r['trip_date']} · {r['departure_hour']:02}:00",
                'kind': 'ride',
                'occurrence_id': r['id'],
            }
            listed_price='Google price unavailable' if not r.get('pricing_status',{}).get('ready',True) else '$%.2f/passenger' % (r['price_cents']/100)
            source['text'] = (
                f"Date {r['trip_date']}; role {r['role']}; owner {r['owner_name']}. "
                f"Pickup {r['origin']['label']} ({r['origin']['mode']}, {r['origin']['radius_miles']} mi). "
                f"Drop-off {r['destination']['label']} ({r['destination']['mode']}, {r['destination']['radius_miles']} mi). "
                f"Depart {r['departure_hour']:02}:00; arrive-by {r['arrive_by']:02}:00; "
                f"seats {r['available_seats']}/{r['capacity']}; "
                f"{listed_price}; type {r['kind']}. Note: {r['note']}"
            )
            docs.append(source)
        return docs

    def vectors(self, texts):
        hashes = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        found = {}
        with self.store.read() as db:
            for h in hashes:
                row = db.execute(
                    'SELECT vector FROM embeddings WHERE content_hash=? AND model=?',
                    (h, self.client.embed_model),
                ).fetchone()
                if row:
                    found[h] = json.loads(row['vector'])
        missing = list(dict.fromkeys(h for h in hashes if h not in found))
        lookup = dict(zip(hashes, texts))
        for start in range(0, len(missing), 16):
            batch = missing[start:start + 16]
            vectors = self.client.embed([lookup[h] for h in batch])
            with self.store.tx() as db:
                for h, vec in zip(batch, vectors):
                    db.execute(
                        'INSERT OR REPLACE INTO embeddings(content_hash,model,vector) VALUES(?,?,?)',
                        (h, self.client.embed_model, json.dumps(vec)),
                    )
                    found[h] = vec
        return [found[h] for h in hashes]

    def retrieve(self, question, docs, semantic=None):
        if semantic is None:
            # Keyword retrieval is fast and enough for policy Q&A; embeddings add a second cold model load.
            semantic = os.getenv('RAG_SEMANTIC', '0') == '1'
        lexical = bm25(question, docs)
        ranks = sorted(range(len(docs)), key=lambda i: lexical[i], reverse=True)
        fusion = {i: 1 / (60 + rank) for rank, i in enumerate(ranks) if lexical[i] > 0}
        method = 'bm25'
        warning = None
        candidates = [i for i in ranks if lexical[i] > 0][:8] or ranks[:8]
        if semantic and candidates:
            try:
                subset = [docs[i] for i in candidates]
                vecs = self.vectors([d['text'] for d in subset] + [question])
                query_vec = vecs[-1]
                semantic_order = sorted(
                    range(len(candidates)),
                    key=lambda j: cosine(vecs[j], query_vec),
                    reverse=True,
                )
                for rank, j in enumerate(semantic_order):
                    i = candidates[j]
                    fusion[i] = fusion.get(i, 0) + 1 / (60 + rank)
                method = 'hybrid_bm25_vector'
            except (Problem, KeyError, TypeError, ValueError) as exc:
                warning = getattr(exc, 'message', None) or 'Embedding model unavailable; keyword retrieval was used.'
                if 'still downloading' not in str(warning).lower() and 'not ready' not in str(warning).lower():
                    warning = 'Embedding model unavailable; keyword retrieval was used.'
        if not fusion:
            fusion = {i: 1 / (60 + rank) for rank, i in enumerate(ranks[:3])}
        best = sorted(fusion, key=fusion.get, reverse=True)[:3]
        result = [{**docs[i], 'citation': f'S{n+1}', 'score': round(fusion[i], 6)} for n, i in enumerate(best)]
        return result, method, warning

    def ask(self, user, question, criteria, semantic=None):
        if not self.limit.acquire(blocking=False):
            raise Problem(429, 'Two AI requests are already running. Please try again shortly.')
        try:
            sources, method, warning = self.retrieve(question, self.documents(user, criteria), semantic=semantic)
            if not sources:
                return dict(answer='I could not find supporting sources for those conditions.', sources=[], mode='no_sources', warning=None)
            try:
                answer = self.client.generate(question, sources)
            except Problem as exc:
                return dict(answer=None, sources=sources, mode='retrieval_only', warning=exc.message, retrieval=method)
            return dict(answer=answer, sources=sources, mode='rag', retrieval=method, warning=warning, model=self.client.chat_model)
        finally:
            self.limit.release()
