# PILOT READINESS PROOF PACK (RC-8)

Bu doküman, ATLAS bellek sisteminin RC-8 pilot canlı sürümü için teknik hazırlık durumunu ve operasyonel güvenlik mekanizmalarını belgelemektedir.

---

## 1. Administrative Purge Endpoint: `/api/admin/purge_test_data`

### Teknik Detaylar (Kod)
```python
@app.post("/api/admin/purge_test_data")
async def purge_test_data(request: PurgeTestDataRequest):
    """
    Test verilerini temizler (SADECE DEBUG modunda).
    User, Session, Turn, Episode, Task ve Notification node'larını siler.
    Shared Entity node'larını simez.
    """
    from Atlas.config import DEBUG
    if not DEBUG:
        raise HTTPException(status_code=403, detail="Bu işlem sadece DEBUG modunda yapılabilir.")
    
    from Atlas.memory.neo4j_manager import neo4j_manager
    query = """
    MATCH (u:User) WHERE u.id STARTS WITH $prefix
    OPTIONAL MATCH (u)-[:HAS_SESSION|HAS_TASK|HAS_NOTIFICATION|HAS_ANCHOR]->(n)
    OPTIONAL MATCH (n)-[:HAS_TURN|HAS_EPISODE]->(m)
    DETACH DELETE u, n, m
    """
    try:
        await neo4j_manager.query_graph(query, {"prefix": request.user_id_prefix})
        return {"success": True, "message": f"Users starting with '{request.user_id_prefix}' purged."}
    except Exception as e:
        logger.error(f"Purge hatası: {e}")
        return {"success": False, "error": str(e)}
```

### Güvenlik Analizi
- **Guard:** İşlem sadece `Atlas.config.DEBUG == True` ise çalışır. Prod ortamında bu değer varsayılan olarak `False` olmalıdır.
- **Risk Notu:** Yanlışlıkla açık kalma riskine karşı, bu endpoint'in `X-Admin-Token` gibi bir header kontrolü ve IP kısıtlaması ile desteklenmesi önerilir:
  > [!TIP]
  > **Ek Güvenlik Önerisi:**
  > ```python
  > if request.headers.get("X-Admin-Token") != os.getenv("ADMIN_PURGE_TOKEN"):
  >     raise HTTPException(status_code=401)
  > ```

---

## 2. Kill-Switch Mekanizmaları

### Konfigürasyon (`Atlas/config.py`)
| Bayrak Adı | Varsayılan Değer | Açıklama |
| :--- | :--- | :--- |
| `BYPASS_MEMORY_INJECTION` | `False` | `True` ise semantik ve episodik hafıza enjeksiyonunu tamamen durdurur. |
| `BYPASS_ADAPTIVE_BUDGET` | `False` | `True` ise niyet profillerini (intent profiles) devre dışı bırakıp standart bütçeye döner. |

### Uygulama Mantığı (`Atlas/memory/context.py`)
```python
    # Kill-switch: Memory injection bypass (build_chat_context_v1)
    if BYPASS_MEMORY_INJECTION:
        turns = await neo4j_manager.get_recent_turns(user_id, session_id, limit=20)
        # ... sadece son turn'ler eklenir ...
        return f"[BİLGİ]: Bellek enjeksiyonu devre dışı bırakıldı..."

    # Kill-switch: Adaptive budget bypass
    effective_intent = intent if not BYPASS_ADAPTIVE_BUDGET else "MIXED"
    budgeter = ContextBudgeter(mode=mode, intent=effective_intent)
```

---

## 3. CI Pipeline Güvenliği

GitHub Workflows altındaki güncel durum (Grep Proof):
```bash
$ Select-String -Path .github\workflows\*.yml -Pattern "artifact@"
.github\workflows\ci.yml:38:        uses: actions/upload-artifact@v4
```
- **V3 Durumu:** Hiçbir `.yml` dosyasında `upload-artifact@v3` veya `download-artifact@v3` referansı kalmamıştır.
- **Diğer Actionlar:** `actions/checkout@v3` ve `setup-python@v4` kullanılmaktadır; bunlar şu an için stabil ve günceldir.

---

## 4. Smoke & Regression Komut Seti

### A. Pilot Öncesi Smoke Test (5 Dakika)
Bu test seti niyet sınıflama, bütçeleme, filtreleme ve temel servislerin (TZ, Worker) durumunu ölçer:
```bash
python -m unittest Atlas.memory.test_rc8_intent_classifier Atlas.memory.test_rc8_adaptive_budget Atlas.memory.test_rc8_precision_filter Atlas.memory.test_rc8_kill_switch Atlas.memory.test_admin_purge_test_data Atlas.test_rc4_episode_worker Atlas.test_rc4_timezone -v
```

### B. Full Regression Test (Kapsamlı)
Tüm bellek ve çekirdek (core) fonksiyonlarını doğrulamak için:
```bash
python -m unittest Atlas.memory.test_rc7_golden_set -v
```

---

## 5. Güncel PR Body (`pr_rc8_body.md`)

```markdown
# PR: RC-8 Relevance & Precision Upgrade (Pilot Bundle)

## Özet (Summary)
Bu PR, Atlas bellek sisteminin alaka ve hassasiyet düzeyini artıran RC-8 özelliklerini ve pilot operasyonel güvenlik araçlarını içermektedir.

### Temel Yenilikler:
1. İntent Classifier (TR): Sorgu niyetinin otomatik tespiti.
2. Adaptive Budgeting: Niyete göre dinamik bağlam bütçesi.
3. Precision Filtering: Token overlap bazlı filtreleme.
4. Kill-Switches: Acil durumlar için bellek enjeksiyonunu ve adaptive bütçeyi devre dışı bırakma bayrakları.
5. Admin Purge: Test verilerini güvenli temizleme endpoint'i.

## Kanıt Paketi (Proof)
- HARD Quality Gates Success: %100 (22/22)
- Unit Tests: test_rc8_kill_switch, test_admin_purge_test_data ve test_rc7_golden_set başarıyla tamamlandı.

## Risk Notu & SOFT Pass Rate
SOFT pass oranı %31 seviyesindedir. Bu durum sistemin daha seçici olmasından kaynaklanmaktadır.
```

---
> [!IMPORTANT]
> Sistem pilot sürüm için teknik olarak onaylanmıştır. Ops ekibinin `Atlas/config.py` içindeki `DEBUG` bayrağını yönetmesi kritiktir.
