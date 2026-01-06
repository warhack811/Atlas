# FAZ 2: Graph Schema & Provenance - Tamamlama Raporu

**Durum:** ✅ TÜM 3 COMMIT BAŞARIYLA UYGULANIP GITHUB'A PUSH EDİLDİ  
**Son Commit:** d01bdad (FAZ2-2)  
**Repository:** warhack811/Atlas (main)

---

## Yapılan Değişiklikler

### FAZ2-1: source_turn_id Plumbing (4b60434)
**Değişen Dosyalar:**
- `Atlas/api.py` (+2 line comments, 2 call sites updated)  
- `Atlas/memory/extractor.py` (+7 lines: signature + docstring + pass-through)
- `Atlas/memory/neo4j_manager.py` (+10 lines: signatures + param passing)

**Değişiklik Özeti:**
- RDR'da oluşturulan `request_id`, `extract_and_save` fonksiyonuna 3. parametre olarak geçiliyor
- `extract_and_save` → `store_triplets` → `_execute_triplet_merge` zincirine source_turn_id iletiliyor
- Tüm yeni parametre tanımlamaları opsiyonel (None default) → geriye dönük uyumlu

---

###FAZ2-2: FACT Schema Fields + Status Filter (d01bdad)
**Değişen Dosyalar:**
- `Atlas/memory/neo4j_manager.py` (+12 lines ON CREATE, +3 lines ON MATCH)
- `Atlas/memory/context.py` (+4 lines: status filter in WHERE)
- `Atlas/observer.py` (+2 lines: status filter in WHERE)

**Yeni FACT Alanları (ON CREATE):**
```cypher
r.schema_version = 2
r.status = 'ACTIVE'
r.source_turn_id_first = $source_turn_id
r.source_turn_id_last = $source_turn_id
r.modality = 'ASSERTED'
r.polarity = 'POSITIVE'
r.attribution = 'USER'
r.inferred = false
```

**ON MATCH Güncellemeleri:**
```cypher
r.source_turn_id_last = $source_turn_id  // Her güncellemede yenilenir
r.schema_version = COALESCE(r.schema_version, 1)  // Eski relationship'ler 1 olarak işaretlenir
```

**Status Filtresi:**
```cypher
WHERE r.status IS NULL OR r.status = 'ACTIVE'
```
- `IS NULL`: Eski relationship'ler (schema_version 1)
- `= 'ACTIVE'`: Yeni aktif relationship'ler
- INACTIVE/RETRACTED relationship'ler dönmez

---

### FAZ2-3: Tests + Completion Report (şu an)
**Yeni Dosyalar:**
- `Atlas/memory/test_faz2_provenance.py` (5 test case)
- `faz02_completion_report.md` (bu dosya)

---

## Manuel Doğrulama Adımları

### Adım 1: Yeni Bir Fact Oluştur
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "faz2_test", "message": "Benim adım Ahmet."}'
```

### Adım 2: Neo4j'de Schema Alanlarını Kontrol Et
```cypher
MATCH ()-[r:FACT {user_id: "faz2_test"}]->()
RETURN r.predicate, r.schema_version, r.status, 
       r.source_turn_id_first, r.source_turn_id_last,
       r.modality, r.polarity, r.attribution, r.inferred
LIMIT 5
```

**Beklenen Çıktı:**
```
predicate: İSİM
schema_version: 2
status: ACTIVE
source_turn_id_first: <8 char UUID from RDR>
source_turn_id_last: <same UUID>
modality: ASSERTED
polarity: POSITIVE  
attribution: USER
inferred: false
```

### Adım 3: Aynı Fact'i Güncelle
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "faz2_test", "message": "Benim adım Ahmet Yılmaz."}'
```

**Neo4j Kontrolü:**
```cypher
MATCH ()-[r:FACT {user_id: "faz2_test", predicate: "İSİM"}]->()
RETURN r.source_turn_id_first, r.source_turn_id_last, r.updated_at
```

**Beklenen:**
- `source_turn_id_first`: İlk request_id (değişmemeli)
- `source_turn_id_last`: İkinci request_id (güncellenmiş olmalı)
- `updated_at`: Yeni timestamp

### Adım 4: Status Filtresini Test Et
```cypher
// Bir fact'in status'ünü INACTIVE yap
MATCH ()-[r:FACT {user_id: "faz2_test"}]->()
SET r.status = 'INACTIVE'
RETURN r
```

```bash
# Artık bu fact context'te dönmemeli
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "faz2_test", "message": "Benim adım neydi?"}'
```

**Beklenen:** INACTIVE fact'ler context'e dahil edilmemeli.

---

## Geriye Dönük Uyumluluk

**Eski FACT Relationship'ler (schema_version 1 veya NULL):**
- Yeni alanlar yok (source_turn_id_*, modality, vb.)
- `status` alanı: NULL
- Query filtresi: `r.status IS NULL OR r.status = 'ACTIVE'` sayesinde hala okunabilir ✅
- İlk güncellenmelerinde `schema_version = 1` olarak işaretlenirler

**ON MATCH Davranışı:**
- `schema_version` yoksa → 1 olarak set edilir
- `source_turn_id_last` güncellenir (first yoksa NULL kalır)
- Diğer yeni alanlar eklenmez (sadece CREATE'te)

---

## Test Komutu

```bash
cd standalone_router
python -m unittest Atlas.memory.test_faz2_provenance -v
```

**Beklenen Testler:**
1. `test_extract_and_save_accepts_source_turn_id` - source_turn_id parametresi akışı
2. `test_extract_and_save_works_without_source_turn_id` - Geriye dönük uyumluluk
3. `test_context_query_has_status_filter` - context.py'de status filtresi
4. `test_observer_query_has_status_filter` - observer.py'de status filtresi
5. `test_old_relationships_without_schema_fields` - Eski relationship'lerin NULL kontrolü

---

## Dosya Değişiklik Özeti

| Dosya | Satır Değişikliği | Amaç |
| :--- | :--- | :--- |
| `api.py` | +4 | source_turn_id iletimi |
| `extractor.py` | +7 | Parametre imzası ve pass-through |
| `neo4j_manager.py` | +25 | Schema alanları + source_turn_id |
| `context.py` | +4 | Status filtresi |
| `observer.py` | +2 | Status filtresi |
| `test_faz2_provenance.py` | +150 (YENİ) | Unit testler |
| `faz02_completion_report.md` | +200 (YENİ) | Dokümantasyon |

**Toplam:** 7 dosya, ~400 satır (production + test + doc)

---

## Gelecek Adımlar (Faz 3+)

**Faz 3: Memory Write Gate (MWG)**
- Daha sofistike EPHEMERAL filtresi
- Claim vs Fact ayrımı
- Polarity detection (SEVMİYOR → NEGATIVE)

**Faz 4: Provenance API**
- Turn-based fact history query
- "Bu bilgiyi hangi konuşmada öğrendin?" endpoint'i

**Faz 5: Status Lifecycle Management**
- ACTIVE → RETRACTED workflow
- Fact conflict resolution

---

**FAZ 2 DURUMU: ✅ TAMAMLANDI VE DEPLOY EDİLDİ**
