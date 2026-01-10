# Atlas AI - Stratejik Yol Haritası

**Sürüm:** 2.0 | **Tarih:** Ocak 2026  
**Mimari:** Industry-Grade Hybrid (Oracle Cloud + Local RTX 4070)

---

## 📊 MEVCUT DURUM

**Baseline:** RC-11 (Stabil) | **HARD Gate:** %100 | **Core Memory:** Fonksiyonel

### Olgunluk Matrisi

| Kategori | Mevcut | Hedef | Durum |
|----------|--------|-------|-------|
| Hafıza Yazma (MWG) | %95 | %100 | ✅ |
| Hafıza Okuma (Retrieval) | %85 | %95 | 🟡 |
| Kullanıcı İzolasyonu | %100 | %100 | ✅ |
| Hibrit Mimari | %0 | %100 | 🔴 |
| GraphRAG | %40 | %90 | 🔴 |
| Diyalog Anlama | %30 | %90 | 🔴 |
| Lokal LLM Entegrasyonu | %0 | %80 | 🔴 |
| QA & Evaluation | %0 | %85 | 🔴 |

---

## 🏗️ YENİ MİMARİ VİZYONU

### Hybrid Edge-Cloud Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ATLAS HYBRID ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────┐     ┌─────────────────────────────────┐   │
│  │      ORACLE CLOUD           │     │       LOCAL WORKER (RTX 4070)   │   │
│  │      (Router/Brain)         │     │       (Edge Node)               │   │
│  │  ┌───────────────────────┐  │     │  ┌─────────────────────────┐    │   │
│  │  │ FastAPI Gateway       │  │     │  │ Worker API (FastAPI)    │    │   │
│  │  │ • Intent Routing      │  │     │  │ • Ollama (Llama-3)      │    │   │
│  │  │ • Orchestration       │◄─┼─────┼──┤ • Flux.1 (Image Gen)    │    │   │
│  │  │ • Memory Coordination │  │ CF  │  │ • Nightly Eval (Ragas)  │    │   │
│  │  └───────────────────────┘  │Tunnel│  └─────────────────────────┘    │   │
│  │  ┌───────────────────────┐  │     │                                  │   │
│  │  │ Neo4j AuraDB          │  │     │  Specs:                          │   │
│  │  │ • Graph Memory        │  │     │  • RTX 4070 12GB VRAM            │   │
│  │  │ • Vector Index        │  │     │  • 32GB RAM                      │   │
│  │  └───────────────────────┘  │     │  • Ollama + ComfyUI              │   │
│  │  ┌───────────────────────┐  │     │                                  │   │
│  │  │ Redis (Upstash)       │  │     └─────────────────────────────────┘   │
│  │  │ • Task Queue          │  │                                           │
│  │  │ • Semantic Cache      │  │     Constraint: Oracle 1GB RAM            │
│  │  └───────────────────────┘  │     Strategy: Logic/Routing only          │
│  └─────────────────────────────┘                                           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Throughput Strategy

| Katman | Konum | İşlev | RAM/VRAM |
|--------|-------|-------|----------|
| Router/Brain | Oracle Cloud | Intent, Orchestration, API | ~800MB |
| Memory | Neo4j AuraDB | Graph + Vector Storage | Managed |
| Cache | Redis (Upstash) | Semantic Cache, Task Queue | Managed |
| Worker | Local PC | LLM Gen, Image Gen, Eval | 12GB VRAM |

---

## 📋 ÖNCELIK MATRİSİ

| Öncelik | Faz | Kapsam | Süre | Durum |
|---------|-----|--------|------|-------|
| 🔴 P0 | FAZ-0 | Critical Bug Fixes | 1 gün | 🔄 Devam |
| 🔴 P0 | **FAZ-X** | **Hybrid Architecture Migration** | 5-7 gün | ⬜ Planlandı |
| 🔴 P0 | **FAZ-Y** | **GraphRAG & Advanced Memory** | 5-7 gün | ⬜ Planlandı |
| 🟡 P1 | FAZ-α | Dialogue Intelligence | 5-7 gün | ⬜ Planlandı |
| 🟡 P1 | **FAZ-W** | **Specialized Capabilities** | 4-5 gün | ⬜ Planlandı |
| 🟡 P1 | FAZ-β | Emotional & Temporal Intelligence | 5-7 gün | ⬜ Planlandı |
| 🟢 P2 | **FAZ-Z** | **Quality Assurance (The Judge)** | 3-5 gün | ⬜ Planlandı |
| 🟢 P2 | FAZ-γ | Relationship & Suggestion Engine | 7-10 gün | ⬜ Planlandı |

---

## FAZ-0: Critical Bug Fixes

> **Hedef:** Hafıza sisteminin düzgün çalışması için kritik bug'ların düzeltilmesi.

### Görevler
- [ ] `api.py:306` - `extract_and_save`'e `user_id` gönder (şu an `session_id`)
- [ ] `api.py:475` - `extract_and_save`'e `user_id` gönder (şu an `session_id`)
- [ ] `app.js:416` - Notifications'da `test_user` → `getStableUserId()`
- [x] Dokümantasyon konsolidasyonu (CHANGELOG + ROADMAP)

### Başarı Kriterleri
- Hafıza yazma/okuma doğru user_id ile çalışıyor
- Manuel test: "Adımı hatırlıyor musun?" → Doğru cevap

---

## FAZ-X: Hybrid Architecture Migration (Edge-Cloud) 🔥

> **Hedef:** Monoliti böl. Oracle → Router/Brain, Local PC → Worker.

### X.1 Worker Node API
**Konum:** Local PC (RTX 4070)

```python
# worker/api.py
from fastapi import FastAPI
app = FastAPI(title="Atlas Worker Node")

@app.post("/generate/text")
async def generate_text(prompt: str, model: str = "llama3"):
    # Ollama çağrısı
    ...

@app.post("/generate/image")
async def generate_image(prompt: str):
    # Flux.1 / ComfyUI çağrısı
    ...
```

- [ ] `worker/api.py` - FastAPI Worker endpoint'leri
- [ ] Ollama integration (llama-3-8b, dolphin-mistral)
- [ ] Flux.1 / ComfyUI integration
- [ ] Health check endpoint (`/health`)

### X.2 Cloudflare Tunnel
- [ ] Cloudflare Tunnel kurulumu (Local → Public URL)
- [ ] `WORKER_TUNNEL_URL` environment variable
- [ ] SSL/TLS güvenliği

### X.3 WorkerClient (Cloud Side)
**Konum:** Oracle Cloud

```python
# Atlas/worker_client.py
class WorkerClient:
    def __init__(self, tunnel_url: str):
        self.base_url = tunnel_url
    
    async def generate_text(self, prompt: str, model: str) -> str:
        """Local LLM'e istek gönder"""
        ...
    
    async def generate_image(self, prompt: str) -> bytes:
        """Local Flux.1'e istek gönder"""
        ...
    
    async def is_available(self) -> bool:
        """Worker erişilebilir mi?"""
        ...
```

- [ ] `Atlas/worker_client.py` - HTTP client
- [ ] Timeout & retry logic
- [ ] Fallback to Gemini API (worker offline)

### X.4 Task Queue (Redis)
```python
# Atlas/task_queue.py
class TaskQueue:
    """Redis-based async job queue"""
    
    async def enqueue(self, task_type: str, payload: dict) -> str:
        """Job ekle, task_id döner"""
        ...
    
    async def get_result(self, task_id: str, timeout: int = 60) -> dict:
        """Sonuç bekle"""
        ...
```

- [ ] Redis (Upstash) integration
- [ ] Async job management
- [ ] Result polling mechanism

### Başarı Kriterleri
- Worker offline → Gemini fallback çalışıyor
- Image generation local'de çalışıyor
- Response time: Local LLM < 3s

---

## FAZ-Y: GraphRAG & Advanced Memory 🧠

> **Hedef:** Simple Graph → Hybrid (Vector + Graph) memory.

### Y.1 Neo4j Vector Index
```cypher
CREATE VECTOR INDEX episode_embeddings IF NOT EXISTS
FOR (e:Episode) ON (e.embedding)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 768,
    `vector.similarity_function`: 'cosine'
  }
}
```

- [ ] Vector index oluşturma (idempotent)
- [ ] Embedding dimension: 768 (Gemini uyumlu)
- [ ] Index health check

### Y.2 Gemini Embedding Integration
```python
# Atlas/memory/embeddings.py
class GeminiEmbedder:
    """Low-memory cloud embedding using Gemini API"""
    model = "models/text-embedding-004"
    
    async def embed(self, text: str) -> List[float]:
        # Gemini API call
        ...
```

- [ ] `GeminiEmbedder` class (text-embedding-004)
- [ ] Batch embedding support
- [ ] Rate limiting (60 RPM)

### Y.3 Semantic Cache (Redis)
```python
# Atlas/memory/semantic_cache.py
class SemanticCache:
    """Redis-based semantic cache for repeated queries"""
    
    async def get(self, query_embedding: List[float], threshold: float = 0.92) -> Optional[str]:
        """Benzer query varsa cached response döner"""
        ...
    
    async def set(self, query: str, response: str, ttl: int = 3600):
        """Query-response çiftini cache'le"""
        ...
```

- [ ] Semantic similarity search in Redis
- [ ] Cache hit/miss logging
- [ ] TTL management (1 hour default)
- [ ] Bypass flag: `BYPASS_SEMANTIC_CACHE`

### Y.4 Hybrid Retrieval Pipeline
```
Query → Embed → [Vector Search + Graph Traversal] → Rerank → Context
```

- [ ] Combined scoring: `0.4×Graph + 0.4×Vector + 0.2×Recency`
- [ ] GraphRAG traversal (2-hop max)
- [ ] Deduplication

### Başarı Kriterleri
- Semantic cache hit rate: >30%
- Retrieval latency: <100ms
- Embedding cost: <$0.01/1K queries

---

## FAZ-W: Specialized Capabilities (Uncensored & Vision) 🎨

> **Hedef:** Local RTX 4070'i tam kapasite kullan.

### W.1 Ollama Integration (Local LLM)
```python
# Atlas/tools/handlers/local_llm.py
async def local_llm_generate(prompt: str, model: str = "llama3-uncensored") -> str:
    """Worker üzerinden Ollama çağrısı"""
    return await worker_client.generate_text(prompt, model)
```

- [ ] `llama-3-8b-uncensored` model
- [ ] `dolphin-mistral-7b` model
- [ ] Tool registry entegrasyonu
- [ ] Orchestrator'da "uncensored" intent routing

### W.2 Flux.1 Local (Image Generation)
```python
# Atlas/tools/handlers/local_flux.py
async def local_flux_generate(prompt: str, **params) -> bytes:
    """Worker üzerinden Flux.1 çağrısı"""
    return await worker_client.generate_image(prompt, **params)
```

- [ ] ComfyUI API integration
- [ ] Flux.1-dev model
- [ ] Tool registry entegrasyonu
- [ ] Fallback: Gemini Image API (worker offline)

### W.3 Tool Registry Update
```python
# Atlas/tools/registry.py
TOOLS = {
    "search": SearchTool(),
    "weather": WeatherTool(),
    "local_llm": LocalLLMTool(),      # YENİ
    "local_flux": LocalFluxTool(),    # YENİ
}
```

- [ ] `LocalLLMTool` class
- [ ] `LocalFluxTool` class
- [ ] Dynamic tool availability checking

### Başarı Kriterleri
- Local LLM response: <3s
- Image generation: <15s
- Worker offline → graceful fallback

---

## FAZ-Z: Quality Assurance & Evaluation (The Judge) 📊

> **Hedef:** Otomatik kalite metrikleri ve nightly evaluation.

### Z.1 Ragas Framework Integration
```python
# worker/evaluation/ragas_eval.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

async def evaluate_daily_interactions(date: str) -> dict:
    """Günlük etkileşimleri puanla"""
    dataset = load_interactions(date)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
    return result.to_dict()
```

- [ ] Ragas kurulumu (Worker Node)
- [ ] Daily interaction export (Neo4j → Ragas format)
- [ ] Faithfulness metric
- [ ] Relevance metric

### Z.2 Nightly Evaluation Pipeline
```yaml
# Schedule: Her gece 03:00
Nightly Eval Pipeline:
  1. Export yesterday's interactions from Neo4j
  2. Run Ragas evaluation on Worker
  3. Store results in Neo4j
  4. Generate daily report
  5. Alert if scores drop below threshold
```

- [ ] Cron job (Worker side)
- [ ] Neo4j interaction export
- [ ] Result persistence
- [ ] Threshold alerting (Faithfulness < 0.7 → alert)

### Z.3 Dashboard Integration
- [ ] `/api/eval/daily` endpoint
- [ ] Historical trend tracking
- [ ] Regression detection

### Başarı Kriterleri
- Daily eval runs successfully
- Faithfulness: >0.8
- Relevance: >0.75

---

## FAZ-α: Dialogue Intelligence

> **Hedef:** AI'ın konuşma akışını anlaması ve referans çözümlemesi.

### Görevler
- [ ] `DialogueStateTracker` modülü
- [ ] Pronoun resolution ("bu", "o", "şu" → referans)
- [ ] Pending questions tracking
- [ ] Multi-turn reasoning support

### Başarı Kriterleri
- Referans çözümleme: %90+
- Context carryover: %85+

---

## FAZ-β: Emotional & Temporal Intelligence

> **Hedef:** Duygusal durum algılama ve zaman bazlı proaktivite.

### Görevler
- [ ] Emotion detector module
- [ ] Session greeting personalization
- [ ] Temporal reference resolution
- [ ] Response tone adaptation

### Başarı Kriterleri
- Duygu algılama: %75+
- Session greeting: %90+

---

## FAZ-γ: Relationship & Suggestion Engine

> **Hedef:** Kullanıcı ilişki modeli ve akıllı öneriler.

### Görevler
- [ ] Relationship model (inner circle tracking)
- [ ] Suggestion engine
- [ ] Proactive notification enhancement

### Başarı Kriterleri
- Relationship recall: %90+
- Suggestion acceptance: %60+

---

## ⚙️ OPERASYONEL NOTLAR

### Kill-Switches
```python
# Atlas/config.py
BYPASS_MEMORY_INJECTION = False    # Semantic + Episodic kapalı
BYPASS_ADAPTIVE_BUDGET = False     # Intent profilleri kapalı
BYPASS_WORKER_NODE = False         # Worker kapalı → Gemini fallback
BYPASS_SEMANTIC_CACHE = False      # Semantic cache kapalı
BYPASS_LOCAL_LLM = False           # Local LLM kapalı → Gemini
BYPASS_LOCAL_FLUX = False          # Local Flux kapalı → Gemini Image
BYPASS_NIGHTLY_EVAL = False        # Nightly evaluation kapalı
```

### Environment Variables
```bash
# Cloud (Oracle)
NEO4J_URI=neo4j+s://xxx.databases.neo4j.io
REDIS_URL=redis://xxx.upstash.io:6379
WORKER_TUNNEL_URL=https://atlas-worker.xxx.cf

# Worker (Local)
OLLAMA_HOST=http://localhost:11434
COMFYUI_HOST=http://localhost:8188
ORACLE_CALLBACK_URL=https://atlas-api.xxx.com/callback
```

### Resource Allocation
```
┌─────────────────────────────────────────────────────────────┐
│                    RESOURCE STRATEGY                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ORACLE (1GB RAM Constraint)     LOCAL (12GB VRAM)          │
│  ─────────────────────────────   ─────────────────────      │
│  • FastAPI Gateway (~200MB)      • Ollama (~6GB)            │
│  • Orchestration Logic (~100MB)  • Flux.1 (~4GB)            │
│  • Redis Client (~50MB)          • ComfyUI (~2GB)           │
│  • Neo4j Client (~50MB)          • Ragas Eval (~4GB)        │
│  • Buffer Headroom (~400MB)                                 │
│                                                             │
│  Total: ~800MB / 1GB             Total: ~10GB / 12GB        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Deployment Commands
```bash
# Oracle Cloud
docker build -t atlas-cloud .
docker run -d -p 8080:8080 --name atlas atlas-cloud

# Local Worker
ollama run llama3-uncensored
python -m worker.api --port 7860
cloudflared tunnel run atlas-worker
```

---

## 📁 YENİ MODÜL YAPISI

```
standalone_router/
├── Atlas/
│   ├── api.py                    # Gateway
│   ├── orchestrator.py           # Brain
│   ├── worker_client.py          # [YENİ] Worker HTTP Client
│   ├── task_queue.py             # [YENİ] Redis Job Queue
│   │
│   ├── memory/
│   │   ├── context.py            # Context Builder
│   │   ├── neo4j_manager.py      # Graph DB
│   │   ├── embeddings.py         # [GÜNCELLE] + GeminiEmbedder
│   │   ├── semantic_cache.py     # [YENİ] Redis Semantic Cache
│   │   └── ...
│   │
│   └── tools/
│       ├── registry.py           # [GÜNCELLE] + local_llm, local_flux
│       └── handlers/
│           ├── local_llm.py      # [YENİ]
│           └── local_flux.py     # [YENİ]
│
└── worker/                        # [YENİ] Local Worker Node
    ├── api.py                     # FastAPI Worker
    ├── ollama_client.py           # Ollama wrapper
    ├── comfyui_client.py          # ComfyUI wrapper
    └── evaluation/
        └── ragas_eval.py          # Nightly Ragas
```

---

## ✅ KALİTE KAPILARI

### HARD Kapılar (Asla Bozulmaz)
- OFF mode sızıntısı: 0
- Kullanıcı izolasyonu: %100
- Worker offline → graceful fallback
- PII exposure: 0

### SOFT Kapılar (İyileştirme Hedefi)
- Retrieval relevance: %80+
- Context build: <100ms
- Semantic cache hit: %30+
- Faithfulness (Ragas): >0.8
- Local LLM latency: <3s

---

*Son güncelleme: 2026-01-10 | Mimari: Hybrid Edge-Cloud v2.0*
