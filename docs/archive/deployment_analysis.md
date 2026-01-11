# Oracle Cloud Deployment Analysis - Sandbox Router

Bu rapor, ATLAS Sandbox Router projesinin Oracle Cloud **VM.Standard.E2.1.Micro** (1 OCPU, 1 GB RAM) üzerinde stabil çalışması için gereken yapılandırmaları ve risk analizini içerir.

## 1. Donanım Kısıtları ve Mevcut Durum

| Özellik | Değer | Etkisi |
| :--- | :--- | :--- |
| **İşlemci (OCPU)** | 1 (AMD EPYC) | Paralel görev işlemede (DAG) dar boğaz yaratabilir. |
| **Bellek (RAM)** | 1 GB | En kritik kısıt. Python çalışma zamanı ve kütüphaneler (özellikle Google Cloud SDK) bu sınırı zorlayacaktır. |
| **Ağ (Network)** | 480 Mbps | API istekleri ve streaming için yeterli. |

## 2. Gerekli Değişiklikler ve Optimizasyonlar

### A. Swap Alanı Oluşturma (KRİTİK)
1GB RAM üzerinde sistemin aniden durmaması (OOM - Out of Memory) için en az **2GB Swap** alanı oluşturulmalıdır.
- **Neden:** İşletim sistemi ve arka plan servisleri bellek bittiğinde bu alanı kullanarak sistemin çökmesini engeller.

### B. Uygulama Katmanı Optimizasyonları
1.  **Gunicorn/Uvicorn Ayarları:**
    - Worker sayısı 1 veya en fazla 2 olarak sınırlandırılmalıdır (`--workers 1`). Fazla worker her biri için ek bellek tüketimi demektir.
2.  **Kütüphane Temizliği:**
    - `google-cloud-aiplatform` kütüphanesi oldukça ağırdır. Sadece Gemini API kullanılıyorsa, hafif olan `google-genai` yeterli olabilir.
3.  **Logging:**
    - `DEBUG=True` modundan çıkılmalı, günlükleme (logging) seviyesi `WARNING` veya `ERROR` yapılarak yüksek disk I/O ve bellek kullanımı önlenmelidir.

### C. Docker ve Deployment Stratejisi
- **Base Image:** `python:3.11-slim` veya `alpine` tabanlı imajlar tercih edilmelidir. `debian` tabanlı ağır imajlardan kaçınılmalıdır.
- **Build Süreci:** Docker imajını sunucuda build etmek yerine (1GB RAM build sırasında yetmeyebilir), GitHub Actions üzerinden build edip Oracle'a "pull" etmek çok daha güvenlidir.

## 3. Mimari Öneriler

### Veritabanı (Neo4j)
-   **Bağlantı Şekli:** Mevcut yapılandırmanızda olduğu gibi `neo4j+s://` protokolü üzerinden AuraDB (bulut) kullanımı Oracle Server için en doğru yöntemdir. Bu sayede hem bellek korunur hem de trafik şifrelenir.
-   **VCN / Firewall:** Oracle Cloud Panelinde, giden trafik (egress) kurallarında **7687** (Bolt) ve **443** (HTTPS) portlarının açık olduğundan emin olunmalıdır. (Varsayılan olarak açıktır).
-   **Öneri:** Bağlantı stabilitesi için `memory/neo4j_manager.py` içindeki retry (yeniden deneme) mekanizmalarının aktif olduğundan emin olunmalıdır (ki kodda bu mevcuttur).

### Önbellek (Caching)
- Memorize (bellek içi cache) yerine, disk bazlı hafif **SQLite** kullanımı tercih edilebilir. Bu, bellek üzerindeki yükü hafifletir.

## 4. Uygulama Adımları (Checklist)

1. [ ] Sunucuda 2GB Swap alanını aktive et.
2. [ ] `api.py` içerisindeki worker ve concurrency ayarlarını düşük tutacak bir `start.sh` oluştur.
3. [ ] `google-cloud-aiplatform` bağımlılığını kaldır (Vertex AI kullanılmıyor, `google-genai` yeterli).
4. [ ] Nginx reverse proxy ayarlarını yaparak 80/443 portlarını 8080'e yönlendir.

---

> [!IMPORTANT]
> 1GB RAM üzerinde çalışırken "Cold Start" (ilk açılış) süresi normalden uzun olabilir. Ancak sistem bir kez ayağa kalktıktan sonra, bulut tabanlı veritabanı ve API'lar sayesinde stabil bir şekilde hizmet verebilir.
