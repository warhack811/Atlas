# Release Notes - RC-7 (Quality Gates)

Bu sürümle birlikte ATLAS, veri doğruluğu ve hafıza sızıntısı (leakage) takibi için profesyonel bir kalite kontrol sistemine (Quality Gate) kavuşmuştur.

## 🚀 Yeni Özellikler

### 1. Expanded Golden Set (60 Senaryo)
- `Atlas/memory/golden_set_rc7.json` dosyası artık 60 farklı uç vakayı (edge case) kapsamaktadır.
- Kategoriler: `OFF_MODE`, `MULTI_USER`, `CONSOLIDATION`, `TIMEZONE`, `DEDUPE`, `SCORING`, `LEAK`, `NOISE`.

### 2. Otomatik Metrik Raporlama
- Her test koşumundan sonra karakter kullanımı, dedupe başarısı ve bağlam isabet oranı (Hit/Leak rate) hesaplanır.
- Raporlar JSON formatında geçici dizine kaydedilir ve özet olarak konsola basılır.

### 3. CI Gate (GitHub Actions)
- `.github/workflows/ci.yml` eklendi.
- Artık her push ve PR'da:
  - Golden Set testleri
  - Pruning & Consolidation regresyonları
  - Scheduler & Identity regresyonları
  otomatik olarak çalışmaktadır.

## ⚙️ Teknik Değişiklikler
- `Atlas/memory/context.py`: `build_chat_context_v1` fonksiyonuna opsiyonel `stats` parametresi eklendi. Bu sayede üretim kodunu bozmadan metrik toplanabiliyor.
- `Atlas/memory/golden_metrics.py`: Metrik toplama mantığı merkezileştirildi.

## 🧪 Test Sonuçları (Baseline)
- **Geçiş Oranı:** %50.0 (Geleneksel "her şeyi bas" mantığından "sadece ilgiliyi bas" mantığına geçişteki kalite açıkları raporlanmıştır).
- **Hit Rate:** %75.0
- **Leak Rate:** %35.8 (Alakasız bilginin bazen hala bağlama sızdığı tespit edilmiştir).

---
*Not: Bu sürüm bir "Baseline" (temel çizgi) sürümüdür. RC-8 ve sonrasında bu metriklerin iyileştirilmesi hedeflenmektedir.*
