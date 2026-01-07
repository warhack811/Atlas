# Release Notes - RC-6 (Forgetfulness)

Bu sürümle birlikte ATLAS, uzun vadeli bellek yönetimi (Retention) ve bilgi yoğunlaştırma (Consolidation) özelliklerine kavuşmuştur.

## 🚀 Yeni Özellikler

### 1. Otomatik Veri İmhası (Retention)
- **Turn Retention:** 30 günden eski veya oturum başına 400 mesajı aşan konuşmalar otomatik olarak silinir.
- **Notification Retention:** Okunmuş ve 30 günden eski bildirimler temizlenir.
- **Task Retention:** Tamamlanmış (DONE/CLOSED) ve 30 günden eski görevler silinir.
- **Episode Retention:** 180 günden eski episod özetleri silinir.

### 2. Episodic Consolidation (Bilgi Yoğunlaştırma)
- 10 adet `READY` durumunda episod biriktiğinde, bunlar tek bir "Consolidated Summary" (Üst Özet) haline getirilir.
- **Avantaj:** Retrieval sırasında 10 ayrı episod yerine 1 ana özet okunarak LLM maliyeti düşürülür ve bağlam kalitesi artırılır.
- **Retrieval Hiyerarşisi:** 2 Yeni Regular Episode + 1 Consolidated Episode (Daha eski tarihli).

### 3. Maintenance Jobs (Bakım Görevleri)
- Lider Scheduler üzerinden her gün **03:30**'da (24 saatte bir) `maintenance_worker` çalışarak temizlik yapar.
- `consolidation_worker` her 60 dakikada bir bekleyen konsolidasyonları işler.

## 🛡️ Güvenlik ve Uyumluluk
- **Safe Pruning:** `DETACH DELETE Entity` kuralına uyulmuştur. Paylaşılan varlıklar asla silinmez, sadece kullanıcı özgü veriler temizlenir.
- **Dedupe Integration:** Konsolidasyon özetleri mevcut dedupe sistemiyle tam uyumludur.

## ⚙️ Yapılandırma
`Atlas/config.py` altındaki `RETENTION_SETTINGS` ve `CONSOLIDATION_SETTINGS` alanlarından süreler ve limitler değiştirilebilir.

## 🧪 Doğrulama
- `test_rc6_pruning`: TTL ve limit Cypher sorguları doğrulanmıştır.
- `test_rc6_consolidation`: PENDING oluşturma ve worker akışı doğrulanmıştır.
- `test_rc6_no_entity_delete`: Statik analiz ile Entity güvenliği doğrulanmıştır.
- Tüm RC-1/RC-5 testleri pasiftir (Regresyon OK).
