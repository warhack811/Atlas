# ATLAS MEMORY SYSTEM — ROADMAP

Bu roadmap, Atlas bellek sisteminin RC-11 sonrası durumundan itibaren
üretim (prod) güvenliği, ekip içi test edilebilirlik ve insansı kaliteyi
kademeli olarak artırmayı hedefler.

Temel ilke:
- HARD kalite kapıları (leak, isolation) asla bozulmaz
- Her faz tek başına prod’da çalışabilir durumda tamamlanır
- Geliştirme ekibi prod ortamda (Oracle) test yapabilir

---

## BASELINE (MEVCUT DURUM) — RC-11
**Durum:** DONE ✅

- [x] Conflict Detection (EXCLUSIVE facts)
- [x] Confidence scoring & soft_signal
- [x] Correction API (/api/memory/correct)
- [x] Semantic Similarity (Hybrid scoring)
- [x] Observability & Context Trace
- [x] Golden Set HARD PASS %100
- [x] CI/CD v4 Actions
- [x] Repo hygiene (.gitignore)

Bu roadmap, bu noktadan sonrası içindir.

---

## FAZ-0 — Repo & Deploy Hygiene (Foundation)

### Hedef
Prod deploy pipeline’a yalnızca gerekli dosyaların girmesi.
Local debug / test artefaktlarının repo’ya ve Oracle deploy’a sızmaması.

### Checklist
- [ ] Standalone router ve alt klasörlerde çöp dosyaların temizlenmesi
- [ ] `.gitignore` tüm log, debug, temp, test_err artefaktlarını kapsıyor
- [ ] Oracle deploy paketinde yalnızca runtime gerekli dosyalar var
- [ ] `git status` her zaman temiz

### Done Kriteri
- Yeni clone + build sonrası **sıfır untracked file**
- CI deploy artefakt boyutu sabit ve minimal
- Oracle ortamında “debug/test file not found” hatası yok

### Ölçüm
- `git status` → clean
- CI artifact size stabil
- Deploy sonrası runtime hata yok

### Owner
- Backend / Infra

---

## FAZ-1 — Production Hardening (Safety First)

### Hedef
Prod ortamda veri güvenliği ve operasyonel stabilite.

### Checklist
#### PII Redaction
- [ ] Hafıza **write path** öncesi PII scrub
- [ ] Trace & log output’larında PII scrub
- [ ] `/api/memory/correct` input scrub
- [ ] Regex + allowlist yaklaşımı

#### Vector Index Automation
- [ ] Neo4j vector index varlık kontrolü
- [ ] Yoksa idempotent create
- [ ] Dimension/config uyum kontrolü
- [ ] Index rebuild runbook

### Done Kriteri
- Graph’ta ham PII bulunamıyor
- Semantic retrieval prod’da index üzerinden çalışıyor
- Uygulama restart → index hatası yok

### Ölçüm
- Neo4j sample scan → PII match = 0
- Retrieval latency stabil
- Trace’te index_used=true

### Owner
- Backend / Data

---

## FAZ-2 — User Control & Transparency

### Hedef
Kullanıcı (ve ekip) hafıza üzerinde **kontrollü ve anlaşılır** yetkiye sahip.

### Checklist
- [ ] Correction API UI-ready (replace / retract)
- [ ] “Beni unut” (forget user/session) akışı
- [ ] Conflict’lerin Open Questions katmanında net sunumu
- [ ] Debug trace yalnızca DEBUG / internal modda

### Done Kriteri
- Kullanıcı düzeltmesi → graph anında güncelleniyor
- Conflict’ler sessizce overwrite edilmiyor
- OFF mode sızdırmazlığı korunuyor

### Ölçüm
- Correction sonrası trace doğruluğu
- Golden set: leak = 0
- Manual test senaryoları %100

### Owner
- Backend / Product

---

## FAZ-3 — Intelligence Quality (Reasoning & Ranking)

### Hedef
Belleğin **daha doğru, seçici ve tutarlı** sonuç üretmesi.

### Checklist
- [ ] Graph vs Vector sonuçları için Reranker
- [ ] Reranker feature set (confidence, recency, semantic score)
- [ ] Golden set metriklerine etkisi ölçülüyor
- [ ] Trace’te rerank gerekçeleri görünür

### Done Kriteri
- HARD kapılar korunuyor
- SOFT pass oranı anlamlı şekilde artıyor
- “Yanlış ama emin” cevaplar azalıyor

### Ölçüm
- SOFT pass %↑
- Rerank contribution trace’te ölçülebilir
- Manual eval senaryoları

### Owner
- Backend / ML

---

## FAZ-4 — Human-like Interaction (UX Intelligence)

### Hedef
Sistemin “insansı” ve bağlama uyumlu hissettirmesi.

### Checklist
- [ ] Mirroring (kısa/uzun, resmi/samimi)
- [ ] Synthesizer modları (task vs personal)
- [ ] Duygu/ton sinyallerinin hafızaya yazılmaması (read-only)
- [ ] Feature flag ile kontrollü açılış

### Done Kriteri
- Aynı bilgi → farklı kullanıcı stiline uygun sunuluyor
- Mirroring OFF iken legacy davranış korunuyor

### Ölçüm
- UX test geri bildirimleri
- Style consistency testleri

### Owner
- Product / ML

---

## FAZ-5 — Ecosystem & Scale

### Hedef
Dış tool’lar ve yüksek yük altında stabil çalışma.

### Checklist
- [ ] External tools (Calendar, Flux vb.) feature-flag’li
- [ ] Tool failure isolation
- [ ] Parallel turn load test
- [ ] Cache (Redis vb.) stratejisi

### Done Kriteri
- Tool hataları core memory’yi etkilemiyor
- Yük altında context build süresi stabil

### Ölçüm
- Load test latency
- Error isolation metrics

### Owner
- Infra / Backend

---

## NOTLAR
- Her faz bağımsız olarak prod’da çalışabilir olmalıdır.
- HARD quality gate ihlali → faz tamamlanmış sayılmaz.
- Trace & observability her fazda güncel tutulur.
