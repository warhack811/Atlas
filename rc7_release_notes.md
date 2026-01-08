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

## 🧪 Test Sonuçları (RC-7.1 Baseline)
- **HARD Gate Başarısı:** %100 (22/22) - `OFF_MODE`, `MULTI_USER`, `LEAK` kategorilerinde sıfır sızıntı garantilendi.
- **SOFT Metrikleri:** %50.0 Pass Rate. (RC-8'de iyileştirilecek).
- **Genel Başarı:** %68.3 (41/60).

## 🛠️ RC-6 Operasyon Notları (Retention)
Hafıza temizlik parametreleri `Atlas/config.py` altındaki `RETENTION_SETTINGS` sözlüğünden ayarlanabilir. İlk haftalar için şu konservatif değerler önerilir:
- **TURN_RETENTION_DAYS:** 60 (Daha uzun geçmiş için)
- **MAX_TURNS_PER_SESSION:** 800 (Oturum şişmesini engellemek için)

> [!TIP]
> Eğer kullanıcılardan "eskiyi hatırlamıyor" şikayeti gelirse, ilk kontrol edilecek yer bu retention süreleri ve konsolidasyon eşikleridir.

---
*Not: Bu sürüm bir "Baseline" (temel çizgi) sürümüdür. RC-8 ve sonrasında SOFT metriklerin iyileştirilmesi hedeflenmektedir.*
