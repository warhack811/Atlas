# Atlas Memory RC-2 Release Notes

## 🚀 Yeni Özellikler

### 1. Kimlik ve Oturum Ayrımı (user_id != session_id)
- `/api/chat` ve `/api/chat/stream` artık opsiyonel `user_id` parametresini destekliyor.
- Eğer `user_id` verilmezse, sistem `session_id`'ye güvenli bir şekilde fallback yapar.
- Neo4j üzerinde `(:User)-[:HAS_SESSION]->(:Session)` graf yapısı kuruldu.

### 2. Kalıcı Kullanıcı Politikaları
- Kullanıcıların bellek ve bildirim tercihleri artık doğrudan Neo4j'de `(:User)` node'u üzerinde saklanıyor.
- Bellek Modları:
    - **OFF:** Kişisel hafıza erişimi tamamen kapanır.
    - **STANDARD:** Varsayılan bellek kullanımı.
    - **FULL:** Gelişmiş bağlam birleştirme.

### 3. Kullanıcı Kontrol Endpoint'leri
- **GET `/api/memory`**: Kullanıcının hafıza özeti, açık görevleri ve bekleyen bildirimlerini tek bir raporda sunar.
- **POST `/api/memory/forget`**: Kullanıcıya özel bilgilerin silinmesini sağlar. Düğümleri (Entity) silmez, sadece kullanıcıyla olan ilişkileri koparır.
- **POST `/api/policy`**: Bellek modunu ve bildirim ayarlarını dinamik olarak günceller.

## 🛠 Teknik İyileştirmeler
- **Context V3 Integration:** Tüm retrieval süreçleri yeni v3 paketleyicisine geçirildi.
- **Ensure Session Helper:** Her chat isteğinde kullanıcı ve oturum varlığı kontrol edilerek bağ kurulur.
- **JSON Serialization Fix:** Neo4j `datetime` objelerinin API tarafında patlaması engellendi.

## 🧪 Doğrulama Kanıtları
- `Atlas.test_rc2_identity`: OK (2 test)
- `Atlas.test_rc2_policy`: OK (2 test)
- `Atlas.test_rc2_forget`: OK (1 test)
- `Atlas.test_rc2_api_contract`: OK (2 test)
- `RC-1 Regressions`: OK (Scheduler sync & Due scanner)

## 💻 Örnek Kullanım (curl)

**Politika Güncelleme:**
```bash
curl -X POST http://localhost:8000/api/policy \
     -H "Content-Type: application/json" \
     -d '{"session_id": "s1", "user_id": "u1", "memory_mode": "OFF"}'
```

**Bilgi Unutma:**
```bash
curl -X POST http://localhost:8000/api/memory/forget \
     -H "Content-Type: application/json" \
     -d '{"session_id": "s1", "scope": "all"}'
```
