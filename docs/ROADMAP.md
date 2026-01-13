# Atlas AI - Stratejik Yol Haritası

**Sürüm:** 2.1 | **Tarih:** 12 Ocak 2026  
**Mimari:** Industry-Grade Hybrid (Oracle Cloud + Local RTX 4070)

---

## 📊 MEVCUT DURUM

**Baseline:** RC-12 (Stabil) | **HARD Gate:** %100 | **Core Memory:** Fonksiyonel

### Olgunluk Matrisi

| Kategori | Mevcut | Hedef | Durum |
|----------|--------|-------|-------|
| Hafıza Yazma (MWG) | %100 | %100 | ✅ |
| Hafıza Okuma (Retrieval) | %95 | %100 | ✅ |
| Kullanıcı İzolasyonu | %100 | %100 | ✅ |
| Hibrit Mimari | %10 | %100 | 🟡 |
| GraphRAG (Cognitive) | %75 | %95 | 🟡 |
| Diyalog Zekası (DST) | %65 | %90 | 🟡 |
| Lokal LLM Entegrasyonu | %0 | %80 | 🔴 |
| QA & Evaluation | %20 | %85 | 🔴 |

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

| Öncelik | Faz | Kapsam | Durum |
|---------|-----|--------|-------|
| 🟢 P0 | **FAZ-0** | **Critical Bug Fixes** | ✅ Tamam |
| 🟢 P0 | **FAZ-Y** | **Advanced Memory (Cognitive)** | ✅ Tamam |
| 🟡 P1 | **FAZ-α** | **Dialogue Intelligence** | 🔄 Devam |
| 🔴 P1 | **FAZ-X** | **Hybrid Arch (Worker Node)** | ⬜ Planlandı |
| 🔴 P1 | **FAZ-W** | **Specialized Capabilities (Vision)**| ⬜ Planlandı |
| 🔴 P1 | **FAZ-β** | **Emotional Intelligence** | ⬜ Planlandı |
| 🔴 P2 | **FAZ-Z** | **Quality Assurance (The Judge)** | ⬜ Planlandı |
| 🔴 P2 | **FAZ-γ** | **Relationship Engine** | ⬜ Planlandı |

---

## ✅ FAZ-0: Critical Bug Fixes (Tamamlandı)

> **Hedef:** Hafıza sisteminin düzgün çalışması için kritik bug'ların düzeltilmesi.

- [x] **User_id Entegrasyonu:** Tüm API ve extractor katmanlarında (api.py, context.py) izolasyon sağlandı.
- [x] **Frontend Auth Sync:** JS katmanında (`atlas-main.js`) dinamik kullanıcı ve session yönetimi düzeltildi.
- [x] **Legacy Pruning:** Gereksiz heartbeat ve pasif fonksiyonlar temizlendi.
- [x] **Dokümantasyon:** CHANGELOG ve ROADMAP konsolide edildi.

---

## ✅ FAZ-Y: Advanced Memory & GraphRAG (Tamamlandı)

> **Hedef:** Atlas'ın sadece bilgiyi saklaması değil; diyalog akışını anlaması, çelişkileri fark etmesi ve "neden hatırladığını" açıklayabilmesi.

### Y.1 Altyapı & Performans (1GB RAM Dostu)
- [x] **BackgroundTasks Resilience:** Arka plan görevleri (`extractor` vb.) None objesine karşı korumalı hale getirildi.
- [x] **Recency Decay Fix:** Güncellik skorlaması math.exp tabanlı exponential decay algoritmasına geçirildi.
- [x] **Memory Pruning:** Düşük öncelikli ve eski tripletlerin temizlenmesi (Importance Scoring).
- [x] **Semantic Cache:** Redis (Upstash) entegreli anlamsal önbellek katmanı stabil hale getirildi.

### Y.2 Hibrit Retrieval & Derinlik (FAZ-Y.Plus)
- [x] **Multi-Source Fusion:** Vector + Graph + Recency ağırlıklı RRF birleştirme (0.35/0.35/0.20/0.10).
- [x] **2-Hop/Multi-hop Retrieval:** Neo4j üzerinden dolaylı ilişkilerin keşfi.
- [x] **Temporal Awareness:** Sorgudaki zaman ifadelerinin (`dateparser`) normalize edilip filtrelenmesi.
- [x] **Deduplication:** Anlamsal olarak mükerrer bilgilerin context'e girmeden önce temizlenmesi.

### Y.3 Meta-Biliş & Şeffaflık (Cognitive Memory)
- [x] **Explainability:** Hatırlanan bilginin kaynağının (Graf/Vektör) sentezleyiciye aktarılması.
- [x] **Meta-Cognition Rules:** Eski (6ay+) veya düşük güvenli (0.6-) bilgilerde "Yanlış hatırlamıyorsam..." gibi insansı şerhler.
- [x] **Conflict Detection:** Mevcut hafıza ile çelişen yeni bilgilerin tespiti ve kullanıcıya teyit sorusu sorulması.

---

## 🔄 FAZ-α: Dialogue Intelligence (Devam Ediyor)

> **Hedef:** Konuşma akışını anlama, konu takibi ve referans çözümleme.

- [x] **Topic Tracker:** Konuşmanın ana konusunun otomatik tespiti (Orchestrator).
- [x] **Smooth Transitions:** Konu değiştiğinde (örn: Futbol -> Fizik) sentezleyici üzerinden yumuşak geçiş köprüleri kurulması.
- [ ] **DialogueStateTracker (DST):** Aktif görevlerin ve kullanıcıdan beklenen yanıtların takibi.
- [ ] **Coreference Resolution:** "O nerede?" gibi sorulardaki zamirlerin Neo4j nesne haritası üzerinden çözümlenmesi.
- [ ] **Recurring Event Logic:** Rutin olayların (her Pazartesi vb.) 'Pattern' olarak saklanması.

---

## ⬜ FAZ-X: Hybrid Architecture Migration (Planlandı)

- [ ] **Worker API:** Local PC (RTX 4070) üzerinde FastAPI tabanlı uzman node oluşturulması.
- [ ] **Cloudflare Tunnel:** Local PC'yi Oracle Cloud'a güvenli şekilde bağlayan tünel mimarisi.
- [ ] **WorkerClient:** Oracle tarafında HTTP client ve fallback (Gemini/Groq) mekanizması.
- [ ] **Task Queue:** Redis tabanlı asenkron iş kuyruğu ve sonuç polling sistemi.

---

## ⬜ FAZ-W: Specialized Capabilities (Planlandı)

- [ ] **Local LLM Integration:** Ollama üzerinden sansürsüz (llama3-uncensored) modellerin kullanımı.
- [ ] **Local Flux.1 Entegrasyonu:** ComfyUI API üzerinden hızlı grafik üretimi.
- [ ] **Visual Memory RAG:** Görsel içeriklerin (embeddings) metin ile aranabilmesi ve referanslanması.

---

## ⬜ FAZ-Z: QA & Evaluation (The Judge) (Planlandı)

- [ ] **Ragas Framework:** Sadakat (faithfulness) ve ilgi (relevance) metriklerinin worker üzerinde ölçülmesi.
- [ ] **Nightly Eval Pipeline:** Günlük diyalogların her gece otomatik olarak değerlendirilmesi ve raporlanması.
- [ ] **Dashboard:** Performans trendlerinin ve regresyonların takibi.

---

## ⚙️ OPERASYONEL NOTLAR

### Kill-Switches (config.py)
- `BYPASS_MEMORY_INJECTION`: Semantic + Episodic kapalı
- `BYPASS_ADAPTIVE_BUDGET`: Intent profilleri kapalı
- `BYPASS_WORKER_NODE`: Worker kapalı → Gemini fallback
- `BYPASS_SEMANTIC_CACHE`: Semantic cache kapalı

### Resource Allocation
- **ORACLE (1GB RAM):** Gateway, Orchestration, Redis/Neo4j Clients.
- **LOCAL (12GB VRAM):** Ollama LLM, Flux.1, Ragas Evaluation.

---

## 📊 BAŞARI KRİTERLERİ (v2.1)
- Semantic Cache Hit: >30%
- Retrieval Latency: <150ms
- Neo4j Query Depth: 2-Hop
- Context Stability: %95

---

*Son güncelleme: 12 Ocak 2026 | Mimari: Hybrid Edge-Cloud v2.1*