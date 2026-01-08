# FAZ 4: Memory Write Gate - Completion Report

**Status:** ✅ TAMAMLANDI  
**Last Commit:** da4e6c0  
**Repository:** warhack811/Atlas (main)

---

## Özet
Merkezi hafıza yazma kararı motoru (MWG) ve kullanıcı bazlı politika sistemi eklendi. Artık her triplet için "nereye yazılacak?" kurallarla belirleniyor.

## Değişen Dosyalar

| Dosya | Değişiklik | Açıklama |
|:------|:-----------|:---------|
| `Atlas/memory/memory_policy.py` | +150 satır (YENİ) | MemoryPolicy dataclass + OFF/STANDARD/FULL |
| `Atlas/memory/mwg.py` | +250 satır (YENİ) | Decision engine + scoring |
| `Atlas/memory/prospective_store.py` | +100 satır (YENİ) | Task node yönetimi |
| `Atlas/memory/neo4j_manager.py` | +70 satır | get_user_memory_mode, fact_exists |
| `Atlas/memory/extractor.py` | +25 satır | MWG entegrasyonu |

**Toplam:** 5 dosya, ~600 satır

---

## Policy Modları

### OFF Mode
- `write_enabled = False`
- Hiçbir fact Neo4j'ye yazılmaz
- **Exception:** Prospective intent varsa reminder oluşturulur

### STANDARD Mode (Varsayılan)
- `write_enabled = True`
- Eşikler: utility=0.6, stability=0.6, confidence=0.6
- **Yazılır:** İSİM, YAŞI, MESLEĞİ, SEVER, ARKADAŞI (catalog LONG_TERM + eşik üstü)
- **Yazılmaz:** NEREDE, HİSSEDİYOR (catalog EPHEMERAL)

### FULL Mode
- `write_enabled = True`
- Düşük eşikler: utility=0.4, stability=0.4, confidence=0.5
- Daha geniş kapsam BUT EPHEMERAL predicate'ler yine LTM'ye akmaz

---

## MWG Karar Akışı

```
Triplet → MWG.decide()
  ├─ Policy.write_enabled=False? → DISCARD
  ├─ Catalog durability=EPHEMERAL? → EPHEMERAL (TTL 24h)
  ├─ Catalog durability=SESSION? → SESSION (TTL 2h)
  ├─ Catalog durability=PROSPECTIVE? → PROSPECTIVE
  ├─ Scoring (utility+stability+confidence) ≥ thresholds? → LONG_TERM
  ├─ Recurrence pekiştirmesi? → LONG_TERM
  └─ Default → EPHEMERAL
```

**Skorlama:**
- **Utility:** Identity/preferences yüksek (0.8-0.9), state düşük (0.3)
- **Stability:** STATIC=1.0, LONG_TERM=0.8, EPHEMERAL=0.2
- **Confidence:** Triplet'ten veya 0.7 default
- **Recurrence:** fact_exists() ile kontrol (0 veya 1)

---

## Manuel Doğrulama

### 1️⃣ OFF Mode Test
```bash
# PowerShell
$env:ATLAS_DEFAULT_MEMORY_MODE="OFF"

curl -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id": "faz4_off_test", "message": "Benim adım Ali."}'
```

**Neo4j Kontrolü:**
```cypher
MATCH ()-[r:FACT {user_id: "faz4_off_test"}]->()
RETURN count(r)
// Beklenen: 0 (write_enabled=False)
```

---

### 2️⃣ STANDARD Mode Test  
```bash
$env:ATLAS_DEFAULT_MEMORY_MODE="STANDARD"

curl -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id": "faz4_std_test", "message": "Benim adım Ahmet, 30 yaşındayım."}'
```

**Neo4j Kontrolü:**
```cypher
MATCH (s:Entity)-[r:FACT {user_id: "faz4_std_test"}]->(o:Entity)
WHERE s.name CONTAINS '__USER__'
RETURN r.predicate, o.name
// Beklenen: İSİM→Ahmet, YAŞI→30
```

---

### 3️⃣ EPHEMERAL Predicate Test
```bash
curl -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id": "faz4_eph_test", "message": "Evdeyim."}'
```

**Neo4j Kontrolü:**
```cypher
MATCH ()-[r:FACT {user_id: "faz4_eph_test", predicate: "NEREDE"}]->()
RETURN count(r)
// Beklenen: 0 (NEREDE catalog'da EPHEMERAL olarak işaretli)
```

---

### 4️⃣ Prospective Task Test
```bash
curl -X POST http://localhost:8000/api/chat `
  -H "Content-Type: application/json" `
  -d '{"session_id": "faz4_task_test", "message": "Yarın saat 10da su iç hatırlat."}'
```

**Neo4j Kontrolü:**
```cypher
MATCH (t:Task {user_id: "faz4_task_test", status: "OPEN"})
RETURN t.raw_text, t.created_at
LIMIT 5
// Beklenen: Task node oluşturulmuş
```

---

## UI Bağlama Noktaları

### 1. User Memory Mode (Neo4j)
```cypher
// UI'den mod ayarla
MATCH (u:User {id: "user_123"})
SET u.memory_mode = 'FULL'
```

### 2. Task Listesi
```python
from Atlas.memory.prospective_store import list_open_tasks

tasks = await list_open_tasks("user_123")
for task in tasks:
    print(f"{task['id']}: {task['text']}")
```

### 3. Predicate Override (Gelecek)
```python
policy = MemoryPolicy(
    mode="STANDARD",
    predicate_overrides={
        "YAŞAR_YER": {"force_decision": "LONG_TERM"}  # Her zaman yaz
    }
)
```

---

## Geriye Dönük Uyumluluk

✅ **Mevcut sistem:** Faz 1/2/3 davranışları korundu  
✅ **Catalog enforcement:** sanitize_triplets çalışmaya devam ediyor  
✅ **Default mode:** STANDARD (env var yoksa)  
✅ **Status filter:** FAZ2'deki status=ACTIVE filtresi korundu  

---

**FAZ 4 DURUMU: ✅ TAMAMLANDI**
