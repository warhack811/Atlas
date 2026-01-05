# ATLAS Sandbox Router.

ATLAS Sandbox Router, 4 katmanlı niyet sınıflandırma, dinamik model yönlendirme ve paralel görev yürütme (DAG) yeteneklerine sahip modüler bir yapay zeka yönlendirme sistemidir.

## Özellikler

- **4-Tier Intent Classification:** Kullanıcı niyetini (kodlama, yaratıcı, genel, arama vb.) yüksek isabetle belirleme.
- **Dynamic Model Routing:** Görev tipine ve maliyetine göre en uygun modele (Gemini, Llama vb.) yönlendirme.
- **DAG Execution Engine:** Birbirine bağımlı veya bağımsız görevleri paralel olarak yürütebilen akıllı iş akışı motoru.
- **Resilience & Key Rotation:** API hatalarına ve hız sınırlarına karşı otomatik anahtar rotasyonu ve yedek model desteği.
- **Memory Layer:** Neo4j graf veritabanı ile uzun vadeli bağlam yönetimi.

## Kurulum

1. Depoyu kopyalayın:
   ```bash
   git clone <repo-url>
   cd standalone_router
   ```

2. Bağımlılıkları yükleyin:
   ```bash
   pip install -r requirements.txt
   ```

3. Yapılandırmayı ayarlayın:
   - `env.example` dosyasının adını `.env` olarak değiştirin.
   - API anahtarlarınızı ve veritabanı bilgilerinizi girin.

4. API'yi başlatın:
   ```bash
   python -m uvicorn api:app --reload --port 8080
   ```

## Yapı

- `orchestrator.py`: Sistemin beyni, planlama katmanı.
- `dag_executor.py`: Görevlerin paralel yürütülmesini yöneten motor.
- `synthesizer.py`: Uzman raporlarını harmanlayan stil katmanı.
- `key_manager.py`: API anahtarlarının rotasyonu ve sağlık takibi.
- `api.py`: FastAPI giriş noktası.

## Lisans
MIT
