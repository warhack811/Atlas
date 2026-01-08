# PR: RC-8 Relevance & Precision Upgrade (Pilot Bundle)

## Özet (Summary)
Bu PR, Atlas bellek sisteminin alaka ve hassasiyet düzeyini artıran **RC-8** özelliklerini ve pilot operasyonel güvenlik araçlarını içermektedir.

### Temel Yenilikler:
1. **İntent Classifier (TR):** Sorgu niyetinin otomatik tespiti.
2. **Adaptive Budgeting:** Niyete göre dinamik bağlam bütçesi.
3. **Precision Filtering:** Token overlap bazlı filtreleme.
4. **Kill-Switches:** Acil durumlar için bellek enjeksiyonunu ve adaptive bütçeyi devre dışı bırakma bayrakları.
5. **Admin Purge:** Test verilerini güvenli temizleme endpoint'i.

## Kanıt Paketi (Proof)
- **HARD Quality Gates Success:** **%100 (22/22)**
- **Unit Tests:** `test_rc8_kill_switch`, `test_admin_purge_test_data` ve `test_rc7_golden_set` başarıyla tamamlandı.

## Risk Notu & SOFT Pass Rate
SOFT pass oranı **%31** seviyesindedir. Bu durum sistemin daha seçici olmasından kaynaklanmaktadır ve pilot aşamasında yakından izlenecektir.

## Rollout & Safety
- Acil durumlar için `BYPASS_*` flagleri hazır.
- Neo4j yedekleme ve rollback planı mevcut.
