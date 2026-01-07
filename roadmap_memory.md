# Atlas Memory Roadmap (RC-1 to RC-5)

Bu doküman, Atlas projesinin hafıza katmanının sürümdür (Release Candidate) aşamalarını ve nihai "Production Readiness" hedeflerini içerir.

---

## 🚀 RC-1: Hardening & Operational Safety (Current)
- **Hedef:** Mevcut FAZ7 özelliklerinin her türlü hata durumuna karşı dayanıklı hale getirilmesi.
- **Kritik Gelişmeler:**
    - Scheduler gerçek zamanlı senkronizasyon (sync_scheduler_jobs).
    - Distributed Leader Lock (FARKLI instance'ların çatışmaması).
    - Due Scanner Cooldown (PT60M) ve Counter mekanizması.
    - JSON Serialization (Neo4j datetime uyumluluğu).
- **Exit Criteria:** Tüm FAZ7 ve RC-1 testlerinin %100 başarılı olması.

## 🔋 RC-2: Performance & Scalability
- **Hedef:** Büyük veri setlerinde retrieval performansının optimize edilmesi.
- **Kritik Gelişmeler:**
    - Neo4j Indexing (id, user_id, status alanları için).
    - Context Packaging için Token Limit (Budget) yönetimi.
    - Cache katmanı (Redis veya yerel LRU) entegrasyonu.

## 🧠 RC-3: Hybrid Memory (Graph + Simple Vector)
- **Hedef:** İlişkisel olmayan ama anlamsal olarak yakın verilerin yakalanması.
- **Kritik Gelişmeler:**
    - Vektör tabanlı benzerlik araması (pgvector).
    - Reranking mekanizması (Graph vs Vector sonuçları).

## 🛡️ RC-4: Privacy & Compliance
- **Hedef:** Çoklu kullanıcı ortamında veri gizliliğinin en üst düzeye çıkarılması.
- **Kritik Gelişmeler:**
    - PII (Kişisel Veri) Maskeleme (Hafızaya yazılmadan önce).
    - Kullanıcı bazlı "Unut Beni" (Purge) komutu.

## 🎯 RC-5: Final Stability & Roadmap FAZ 8-15
- **Hedef:** Genel kullanıma hazır, %99.9 çalışma süresi hedefli kararlı sürüm.
- **Kritik Gelişmeler:**
    - Kapsamlı Stress Testleri.
    - FAZ 8-15 için altyapı hazırlığı.

---

## 🔍 Neo4j Doğrulama Sorguları

### Bildirim Sayaçlarını Kontrol Et
```cypher
MATCH (t:Task) 
WHERE t.notified_count > 0 
RETURN t.id, t.raw_text, t.notified_count, t.last_notified_at
```

### Liderlik Kilidini Kontrol Et
```cypher
MATCH (l:SchedulerLock) 
RETURN l.name, l.holder, l.expires_at
```

## 🛠️ Test Komutları
- `python -m unittest Atlas.memory.test_rc1_hardening`
- `python -m unittest Atlas.test_rc1_scheduler_refresh`
- `python -m unittest Atlas.memory.test_rc1_due_scanner`
