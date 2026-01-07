# Atlas Memory Roadmap (RC-1 to RC-5)

Bu doküman, Atlas projesinin hafıza katmanının sürümdür (Release Candidate) aşamalarını ve nihai "Production Readiness" hedeflerini içerir.

---

## ✅ RC-1: Hardening & Operational Safety
**Durum:** TAMAMLANDI (Merge Ready)
- [x] Scheduler gerçek zamanlı senkronizasyon (sync_scheduler_jobs).
- [x] Distributed Leader Lock (FARKLI instance'ların çatışmaması).
- [x] Due Scanner Cooldown (PT60M) ve Counter mekanizması.
- [x] JSON Serialization (Neo4j datetime uyumluluğu).

## ✅ RC-2: Identity, User Controls & Policy Persistence
**Durum:** TAMAMLANDI (rc-memory-2 branch)
- [x] `user_id` vs `session_id` ayrımı ve fallback mantığı.
- [x] Kalıcı kullanıcı politikaları (Neo4j node üzerinde storage).
- [x] Memory Management API (`GET /api/memory`, `POST /api/memory/forget`, `POST /api/policy`).
- [x] **OFF mode** tam izolasyon ve retrieval bypass.

## 🔋 RC-3: Performance & Scalability (Next)
**Durum:** Planlanıyor
- [ ] Neo4j Indexing (id, user_id, status alanları için).
- [ ] Context Packaging için Token Limit (Budget) yönetimi.
- [ ] Cache katmanı (Redis veya yerel LRU) entegrasyonu.

## 🧠 RC-4: Hybrid Memory (Graph + Simple Vector)
**Durum:** Beklemede
- [ ] Vektör tabanlı benzerlik araması (pgvector).
- [ ] Reranking mekanizması (Graph vs Vector sonuçları).

## 🎯 RC-5: Final Stability & Readiness
**Durum:** Beklemede
- [ ] PII (Kişisel Veri) Maskeleme (Hafızaya yazılmadan önce).
- [ ] Kapsamlı Stress Testleri ve FAZ 8-15 hazırlığı.

---

## 🔍 Neo4j Doğrulama Sorguları

### Kullanıcı Ayarlarını Kontrol Et
```cypher
MATCH (u:User {id: 'user_id'}) RETURN u
```

### Bildirim Sayaçlarını Kontrol Et
```cypher
MATCH (t:Task) 
WHERE t.notified_count > 0 
RETURN t.id, t.raw_text, t.notified_count, t.last_notified_at
```

## 🛠️ Test Komutları
- `python -m unittest Atlas.test_rc2_identity`
- `python -m unittest Atlas.test_rc2_policy`
- `python -m unittest Atlas.test_rc2_forget`
- `python -m unittest Atlas.test_rc2_api_contract`
