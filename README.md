# ATLAS - Akıllı Yapay Zeka Asistanı

<div align="center">

**Proaktif, Öngörülü ve İnsansı AI Asistan Platformu**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.x-red.svg)](https://neo4j.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 🎯 Vizyon

Atlas, kullanıcıyı **gerçekten anlayan, hatırlayan ve öngören** bir AI asistan olmayı hedefler.

| Yetenek | Açıklama |
|---------|----------|
| 🧠 **Anlama** | Söyleneni değil, kastedileni anlama |
| 💾 **Hatırlama** | Graf tabanlı uzun vadeli hafıza |
| 🔮 **Öngörme** | Kullanıcı sormadan ihtiyacı tahmin etme |
| 🎭 **Adapte Olma** | Kullanıcının stiline ve duygusuna uyum |

---

## ✨ Özellikler

### Çekirdek Mimari
- **4-Tier Intent Classification** - Niyet sınıflandırma (GENERAL/PERSONAL/TASK/FOLLOWUP)
- **DAG Execution Engine** - Paralel görev yürütme
- **Dynamic Model Routing** - Gemini, Llama, Kimi modelleri arası akıllı yönlendirme
- **Resilience & Key Rotation** - Otomatik anahtar rotasyonu ve yedek model

### Hafıza Sistemi (RC-11)
- **Graf Tabanlı Bellek** - Neo4j ile ilişkisel hafıza
- **Memory Write Gate (MWG)** - Kalite kontrollü yazma
- **Hybrid Retrieval** - Keyword + Semantic + Recency skorlama
- **Conflict Resolution** - EXCLUSIVE/ADDITIVE kuralları
- **User Controls** - Silme, düzeltme, politika yönetimi

### Proaktif Özellikler
- **Observer** - Arka plan risk/fırsat tespiti
- **Task/Reminder** - Türkçe tarih parse desteği
- **Notification Gatekeeping** - Sessiz saatler, yorgunluk kontrolü

### Güvenlik
- **Safety Gate** - Prompt injection koruması
- **PII Detection** - Kişisel veri maskeleme
- **OFF Mode** - Tam hafıza izolasyonu
- **Quality Gates** - HARD %100 garanti

---

## 🏗️ Mimari

```
Atlas/
├── api.py                 # FastAPI giriş noktası (817 satır)
├── orchestrator.py        # Beyin - Planlama katmanı
├── dag_executor.py        # Paralel görev yürütücü
├── synthesizer.py         # Stil ve ton harmanlayıcı
├── generator.py           # LLM çağrı katmanı
│
├── memory/                # Hafıza Sistemi
│   ├── context.py         # Bağlam paketleme (V3)
│   ├── neo4j_manager.py   # Graf DB yönetimi
│   ├── mwg.py             # Memory Write Gate
│   ├── lifecycle_engine.py# Conflict resolution
│   ├── intent.py          # Niyet sınıflandırma
│   ├── embeddings.py      # Vektör embedding
│   ├── prospective_store.py # Task yönetimi
│   ├── due_scanner.py     # Hatırlatma tarayıcı
│   └── ...
│
├── tools/                 # Araç Sistemi
│   ├── registry.py        # Dinamik araç yükleyici
│   ├── handlers/          # search, flux, weather
│   └── definitions/       # JSON tanımları
│
├── observer.py            # Proaktif gözlemci
├── safety.py              # Güvenlik katmanı
├── quality.py             # Kalite kontrol
├── time_context.py        # Zaman farkındalığı
├── style_injector.py      # Persona yönetimi
│
└── ui/                    # Web Arayüzü
    ├── index.html
    ├── app.js
    └── ...
```

---

## 🚀 Kurulum

### Gereksinimler
- Python 3.11+
- Neo4j 5.x (AuraDB veya local)
- API Keys: Gemini, Groq

### Adımlar

1. **Depoyu klonlayın:**
```bash
git clone <repo-url>
cd standalone_router
```

2. **Sanal ortam oluşturun:**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

3. **Bağımlılıkları yükleyin:**
```bash
pip install -r requirements.txt
```

4. **Yapılandırma:**
```bash
cp env.example .env
# .env dosyasını düzenleyin
```

`.env` içeriği:
```env
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
```

5. **Başlatın:**
```bash
uvicorn Atlas.api:app --reload --port 8080
```

6. **Erişim:**
- Web UI: http://localhost:8080
- API Docs: http://localhost:8080/docs

---

## 📡 API Endpoint'leri

### Sohbet
| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/chat` | POST | Standart yanıt |
| `/api/chat/stream` | POST | SSE stream yanıt |

### Hafıza
| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/memory` | GET | Hafıza durumu |
| `/api/memory/forget` | POST | Bilgi silme |
| `/api/memory/correct` | POST | Bilgi düzeltme |
| `/api/policy` | POST | Politika güncelleme |

### Proaktif
| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/api/notifications` | GET | Bildirimler |
| `/api/tasks` | GET | Görevler |
| `/api/tasks/done` | POST | Görev tamamla |

---

## ⚙️ Yapılandırma

### Model Governance (`config.py`)
```python
MODEL_GOVERNANCE = {
    "orchestrator": ["gemini-2.0-flash", "llama-3.3-70b"],
    "synthesizer": ["kimi-k2-instruct", "llama-3.3-70b"],
    "coding": ["gpt-oss-120b", "llama-3.3-70b"],
    # ...
}
```

### Memory Settings
```python
RETENTION_SETTINGS = {
    "TURN_RETENTION_DAYS": 30,
    "MAX_TURNS_PER_SESSION": 400,
    "EPISODE_RETENTION_DAYS": 180
}
```

### Kill-Switches
```python
BYPASS_MEMORY_INJECTION = False  # Hafıza kapalı
BYPASS_ADAPTIVE_BUDGET = False   # Intent profilleri kapalı
```

---

## 🧪 Test

```bash
# Smoke Test
python -m pytest Atlas/memory/ -v -k "golden"

# Full Test
python -m pytest Atlas/ -v --tb=short
```

---

## 📚 Dokümantasyon

| Dosya | İçerik |
|-------|--------|
| [CHANGELOG.md](docs/CHANGELOG.md) | Sürüm geçmişi |
| [ROADMAP.md](docs/ROADMAP.md) | Gelecek planı |
| `docs/archive/` | Faz raporları |

---

## 🗺️ Yol Haritası

| Faz | Kapsam | Durum |
|-----|--------|-------|
| FAZ-0 | Repo Hygiene | 🟡 Devam |
| FAZ-1 | Production Safety | ⬜ Planlandı |
| FAZ-α | Dialogue Intelligence | ⬜ Planlandı |
| FAZ-β | Emotional Intelligence | ⬜ Planlandı |
| FAZ-γ | Relationship Model | ⬜ Planlandı |

Detaylar için: [ROADMAP.md](docs/ROADMAP.md)

---

## 📄 Lisans

MIT License - Detaylar için [LICENSE](LICENSE) dosyasına bakın.

---

<div align="center">

**Atlas** - *İnsansı AI Asistan*

</div>
