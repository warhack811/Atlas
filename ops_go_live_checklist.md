# Ops Go-Live Checklist: RC-8 Pilot

## 1. Hazırlık (Preparation)
- [ ] **Backup:** Neo4j veri tabanının tam (full) yedeği alındı mı?
- [ ] **Environment:** `Atlas/config.py` içerisindeki `CONTEXT_BUDGET_PROFILES` değerleri prod ortamına uygun mu?
- [ ] **Dependency:** `standalone_router` bağımlılıkları güncel mi?

## 2. İzleme (Monitoring)
- [ ] **Niyet Takibi:** `stats["intent"]` değerlerinin dağılımı (Grafana/Kibana) izleniyor mu?
- [ ] **Hassas Filtreleme:** `stats["semantic_filtered_out_count"]` ve `stats["episode_filtered_out_count"]` metrikleri takip ediliyor mu?
- [ ] **Latency:** `build_chat_context_v1` çalışma süresi (ms) baseline ile karşılaştırıldı mı?

## 3. Acil Durum (Kill-Switch & Rollback)
- [ ] **Kill-Switch (Memory Injection):** `BYPASS_MEMORY_INJECTION=true` bayrağı ile semantik/episodik besleme anında durdurulabilir.
- [ ] **Kill-Switch (Adaptive Budget):** `BYPASS_ADAPTIVE_BUDGET=true` bayrağı ile niyet profilleri devre dışı bırakılıp `STANDARD` bütçeye dönülebilir.
- [ ] **Rollback:** Sorun anında `rc-memory-7` branch'ine geri dönme prosedürü hazır mı?
- [ ] **Data Cleanup:** Pilot sonrası test verilerini temizlemek için `POST /api/admin/purge_test_data` endpoint'i kullanılabilir.

## 4. Rollout Planı
- [ ] **Internal Pilot:** Geliştirici ekibi (Day 1-2).
- [ ] **Limited Beta:** %5 kullanıcı (Day 3-5).
- [ ] **Full Release:** Day 7+.
