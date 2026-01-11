# Atlas Memory System - Changelog

Bu dosya, Atlas hafıza sisteminin geliştirme sürecini kronolojik olarak belgelemektedir.

---

## Mevcut Durum: RC-11+ (Ocak 2026)

**Son Stabil Sürüm** - HARD Quality Gate: %100

### Aktif Özellikler
- Conflict Detection (EXCLUSIVE facts)
- Confidence Scoring & Soft Signals
- Correction API (`/api/memory/correct`)
- Semantic Similarity (Hybrid Scoring)
- Observability & Context Trace
- Golden Set HARD PASS %100

---

## 2026-01-10: Dokumentasyon Konsolidasyonu

### Yapılan İşler
- [x] 10+ ayrı dokümantasyon dosyası birleştirildi
- [x] `CHANGELOG.md` oluşturuldu (tüm RC release notes)
- [x] `ROADMAP.md` oluşturuldu (gelecek vizyon + mevcut durum)
- [x] İnsansı AI analizi yapıldı
- [x] 8 yeni modül planlandı (FAZ-α, FAZ-β, FAZ-γ)
- [x] Mevcut altyapı dökümante edildi

### Silinen Dosyalar
```
docs/anayasa.md
docs/roadmap.md
docs/roadmap_memory.md
docs/ops_go_live_checklist.md
docs/pilot_readiness_pack.md
docs/rc2_release_notes.md
docs/rc3_release_notes.md
docs/rc6_release_notes.md
docs/rc7_release_notes.md
docs/rc9_release_notes.md
docs/rc10_release_notes.md
```

### Yeni Yapı
```
docs/
├── CHANGELOG.md   # Geçmiş (bu dosya)
├── ROADMAP.md     # Gelecek vizyon
└── archive/       # Faz raporları (referans)
```

---

## SÜRÜM GEÇMİŞİ

### RC-11: Conflict Detection & Correction
**Durum:** ✅ TAMAMLANDI

- [x] Conflict Detection (EXCLUSIVE predicate'lerde çakışma tespiti)
- [x] Confidence scoring (`MEMORY_CONFIDENCE_SETTINGS`)
- [x] Soft signal decay mekanizması (`decay_soft_signals()`)
- [x] Correction API: replace/retract modları
- [x] `correct_memory()` Neo4j entegrasyonu

### RC-10: Semantic Similarity Retrieval
**Durum:** ✅ TAMAMLANDI

- [x] Hybrid Scoring Modeli (45% Keyword, 35% Semantic, 20% Recency)
- [x] Deterministik `HashEmbedder` (test ortamı için)
- [x] Sentence-Transformers desteği (prod ortamı için)
- [x] `EMBEDDING_SETTINGS` konfigürasyonu
- [x] Episode embedding storage ve retrieval

### RC-9: Observability & Explainability
**Durum:** ✅ TAMAMLANDI

- [x] Context Tracing (`ContextTrace` dataclass)
- [x] Explainability (bütçe dağılımı gerekçeleri)
- [x] Performance Monitoring (build latency ölçümü)
- [x] Debug Trace API (`debug_trace: true` parametresi)

### RC-8: Relevance & Precision
**Durum:** ✅ TAMAMLANDI

- [x] Intent Classifier (`intent.py`)
- [x] Adaptive Budgeting (`CONTEXT_BUDGET_PROFILES`)
- [x] Precision Filtering (token overlap bazlı)
- [x] Kill-Switches (`BYPASS_MEMORY_INJECTION`, `BYPASS_ADAPTIVE_BUDGET`)
- [x] Admin Purge endpoint (`/api/admin/purge_test_data`)

### RC-7: Quality Gates
**Durum:** ✅ TAMAMLANDI

- [x] Golden Set (60 senaryo)
- [x] Metrik Raporlama (`golden_metrics.py`)
- [x] CI Gate (GitHub Actions)
- [x] HARD Gate: %100 (OFF_MODE, MULTI_USER, LEAK kategorileri)

### RC-6: Retention & Consolidation
**Durum:** ✅ TAMAMLANDI

- [x] Turn Retention (30 gün / 400 mesaj limiti)
- [x] Notification & Task Retention
- [x] Episode Retention (180 gün)
- [x] Episodic Consolidation (10 REGULAR → 1 CONSOLIDATED)
- [x] Maintenance Jobs (03:30 günlük)

### RC-5: Identity Resolution
**Durum:** ✅ TAMAMLANDI

- [x] `identity_resolver.py` modülü
- [x] Ben/Sen/O çözümlemesi
- [x] Alias graph yönetimi
- [x] `__USER__::session_id` anchor pattern

### RC-4: Memory Write Gate
**Durum:** ✅ TAMAMLANDI

- [x] MWG Engine (`mwg.py`)
- [x] Memory Policy (`memory_policy.py`)
- [x] OFF/STANDARD/FULL modları
- [x] Predicate Catalog (`predicate_catalog.py`)
- [x] EPHEMERAL/SESSION/LONG_TERM karar mantığı

### RC-3: Hybrid Memory
**Durum:** ✅ TAMAMLANDI

- [x] Neo4j tabanlı kalıcı transcript (`:Turn` node)
- [x] Episodik özetleme (`:Episode` node, 20 mesajda bir)
- [x] Hibrit Bağlam Paketleme (Transcript + Episodic + Semantic)
- [x] `build_chat_context_v1` fonksiyonu

### RC-2: Identity & User Controls
**Durum:** ✅ TAMAMLANDI

- [x] user_id vs session_id ayrımı
- [x] Kalıcı politikalar (Neo4j User node)
- [x] Memory Management API (`/api/memory`, `/api/memory/forget`, `/api/policy`)
- [x] OFF mode tam izolasyon

### RC-1: Hardening & Operational Safety
**Durum:** ✅ TAMAMLANDI

- [x] Scheduler senkronizasyonu (`sync_scheduler_jobs`)
- [x] Distributed Leader Lock
- [x] Due Scanner Cooldown (PT60M)
- [x] JSON Serialization (Neo4j datetime uyumluluğu)

---

## ANAYASA FAZ GEÇMİŞİ

Aşağıdaki fazlar, Atlas Hafıza Anayasası'nda tanımlanan temel geliştirme adımlarıdır.

### ✅ FAZ 0.1: Çoklu Kullanıcı İzolasyonu
- User-scoped FACT ilişkileri
- Safe deletion (shared Entity node koruması)
- user_id vs session_id standardizasyonu

### ✅ FAZ 1: Predicate Catalog
- Canonical predicate tanımları
- EXCLUSIVE vs ADDITIVE tip ayrımı
- LLM predicate → catalog mapping

### ✅ FAZ 2: Claim Model & Provenance
- source_turn_id izlenebilirlik
- Schema version 2 alanları
- Status filtresi (ACTIVE/SUPERSEDED)

### ✅ FAZ 3: Identity Resolver
- Speaker-aware anchoring
- Alias çözümleme
- AMBIGUOUS_REF yönetimi

### ✅ FAZ 4: Memory Write Gate (MWG)
- DISCARD/SESSION/EPHEMERAL/LONG_TERM kararları
- Utility/Stability/Confidence skorlama
- Policy mod entegrasyonu

### ✅ FAZ 5: Lifecycle & Conflict Engine
- EXCLUSIVE supersede mantığı
- ADDITIVE birikimli güncelleme
- Provenance (superseded_by_turn_id)

### ✅ FAZ 6: Retrieval Orchestrator
- Hard/Soft/Open Questions paketleme
- Truncation limits
- OFF mode context

### ✅ FAZ 7: Prospective & Proactive Motor
- Notification persistence (Neo4j)
- Observer gatekeeping (opt-in, quiet hours, fatigue)
- DueAt parsing (Türkçe tarih desteği)
- Dynamic Scheduler

---

## TEKNİK MİMARİ

### Aktif Modüller (`Atlas/memory/`)
```
context.py          # Bağlam oluşturma (908 satır)
neo4j_manager.py    # Graf DB yönetimi (899 satır)
extractor.py        # Triplet çıkarma
intent.py           # Niyet sınıflama
mwg.py              # Write Gate
lifecycle_engine.py # Conflict resolution
embeddings.py       # Vektör embedding
predicate_catalog.py# Predicate tanımları
identity_resolver.py# Kimlik çözümleme
prospective_store.py# Task yönetimi
trace.py            # Observability
golden_metrics.py   # Test metrikleri
```

### API Endpoint'leri (`Atlas/api.py`)
```
POST /api/chat              # Ana sohbet
POST /api/chat/stream       # SSE stream
GET  /api/memory            # Hafıza durumu
POST /api/memory/forget     # Silme
POST /api/memory/correct    # Düzeltme (RC-11)
POST /api/policy            # Politika güncelleme
GET  /api/notifications     # Bildirimler
GET  /api/tasks             # Görevler
```

---

*Son güncelleme: 2026-01-10*
