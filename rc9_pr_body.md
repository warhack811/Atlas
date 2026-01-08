# Pull Request: RC-9 - Observability & Context Trace

## Özet
Bu PR, Atlas bellek sisteminin bağlam (context) üretim sürecini şeffaf ve ölçülebilir hale getiren **Context Trace** altyapısını içerir. Bağlamın neden ve nasıl oluştuğu artık hem geliştirme aşamasında (API) hem de performans metriklerinde izlenebilir.

## Değişiklikler
- **ContextTrace Dataclass:** `Atlas/memory/trace.py` içinde tanımlandı. ID'ler, bütçeler, kullanım miktarları ve karar gerekçelerini tutar.
- **Hybrid Context Integration:** `build_chat_context_v1` ve `build_memory_context_v3` fonksiyonları trace desteğiyle güncellendi.
- **High-Precision Timing:** `time.perf_counter` kullanılarak milisaniye hassasiyetinde adım bazlı ölçüm eklendi.
- **Conditional API Exposure:** `debug_trace` alanı, sadece `DEBUG=True` ve istekte açıkça talep edildiğinde yanıta eklenir.
- **JSON Safety:** Neo4j ve datetime tiplerine karşı `serialize_neo4j_value` koruması eklendi.

## Risk & Güvenlik
- **PII Redaction:** Trace içeriği ham kullanıcı mesajı veya hafıza cümleleri içermez; sadece metadata ve ID'ler mevcuttur.
- **Performance:** Ölçümler ek DB sorgusu oluşturmaz, sadece mevcut işlemlerin sürelerini yakalar.

## Rollout & Geriye Uyumluluk
- Varsayılan yapılandırmada API şeması üzerinde herhangi bir değişiklik yoktur (opsiyonel alan).
- Metrik sistemine yeni `avg_context_build_ms` verisi eklenmiştir.

## Doğrulama
- `Atlas.memory.test_rc9_trace`: **PASS**
- `Atlas.test_rc9_api_debug_trace`: **PASS**
- `Atlas.memory.test_rc7_golden_set`: **PASS** (Regresyon kontrolü - %100 HARD PASS)
