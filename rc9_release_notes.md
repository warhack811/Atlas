# Release Notes - RC-9: Observability & Explainability

Atlas bellek sisteminin bağlam üretim sürecini şeffaf, ölçülebilir ve açıklanabilir hale getiren **RC-9** güncellemesi tamamlandı.

## Temel Özellikler
1. **Context Tracing:** Her bağlam üretimi için detaylı bir izleme (trace) kaydı oluşturulur.
2. **Explainability:** Bellek bütçesinin neden öyle dağıtıldığı, hangi öğelerin seçildiği ve hangilerinin neden elendiği (reasoning) kayıt altına alınır.
3. **Performance Monitoring:** Bağlam oluşturma adımlarının (Fetch Turns, Fetch Semantic, Build Total) süreleri milisaniye cinsinden ölçülür.
4. **Debug Trace API:** `Atlas.config.DEBUG=True` iken isteğe `debug_trace: true` eklenirse, tüm trace verisi yanıtla birlikte döner.

## Örnek Trace JSON
```json
"debug_trace": {
  "request_id": "trace_1704700000",
  "intent": "PERSONAL",
  "memory_mode": "MIXED",
  "budgets": {
    "transcript": 1800,
    "episodic": 1200,
    "semantic": 3000,
    "total": 6000
  },
  "usage": {
    "transcript_chars": 540,
    "episode_chars": 0,
    "semantic_chars": 120,
    "total_chars": 660
  },
  "reasons": [
    "BYPASS_ADAPTIVE_BUDGET=false",
    "threshold_filter > 0.15"
  ],
  "timings_ms": {
    "build_total_ms": 12.5,
    "fetch_semantic_ms": 8.2
  }
}
```

## Metrikler & Golden Set
- **Avg Context Build Latency:** ~10-15ms (local baseline).
- **Intent Distribution:** Golden Set senaryoları üzerinden niyet dağılımı raporlanabilir.
- **HARD Pass Rate:** **%100** (Regresyon korunmuştur).

## Nasıl Kullanılır?
1. `Atlas/config.py` içinde `DEBUG = True` yapın.
2. API isteğine `{ "message": "...", "session_id": "...", "debug_trace": true }` ekleyin.
