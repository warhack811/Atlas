# Release Notes - RC-10 (Semantic Similarity Retrieval)

Atlas bellek sistemi, konulu ve anlamsal olarak benzer geçmiş bölümleri (episodes) artık daha hassas bir şekilde yakalayabiliyor. RC-10 ile birlikte "Keyword Overlap" yöntemine ek olarak "Embedding-based Similarity" desteği eklenmiştir.

## Öne Çıkan Özellikler

### 1. Hybrid Scoring Modeli
Episodik hafıza seçiminde artık üçlü bir ağırlıklandırma kullanılmaktadır:
- **%45 Keyword Overlap:** Terim eşleşmesi.
- **%35 Semantic Similarity:** Anlamsal yakınlık (Vektör benzerliği).
- **%20 Recency:** Güncellik bonusu.

### 2. Deterministik HashEmbedder
Test ortamlarında ve offline çalışmalarda deterministik sonuçlar üreten, harici kütüphane bağımlılığı olmayan (numpy hariç) `HashEmbedder` geliştirildi. Bu sayede testler ağ çağrısı yapmadan tutarlı çalışır.

### 3. Sentence-Transformers Desteği
Üretim (prod) ortamı için `EMBEDDER_PROVIDER="sentence-transformers"` seçeneği eklendi. Uygun kütüphane yüklüyse otomatik olarak yüksek kaliteli embedding üretimine geçer.

### 4. Gelişmiş Trace (RC-9 Entegrasyonu)
API yanıtındaki `debug_trace` artık seçilen her episod için şu detayları içerir:
- `overlap` skoru
- `semantic_sim` skoru
- `recency` bonusu
- `total` skor

## Kurulum ve Yapılandırma

### Ortam Değişkenleri
- `EMBEDDER_PROVIDER`: `hash` (varsayılan) veya `sentence-transformers`.

### Neo4j Doğrulama
Yeni episodların embedding ile kaydedildiğini şu sorguyla kontrol edebilirsiniz:
```cypher
MATCH (e:Episode) WHERE e.embedding IS NOT_NULL RETURN e.summary, size(e.embedding)
```

Vektör indeksi oluşturmak için (Neo4j sürümünüz destekliyorsa):
```python
from Atlas.memory.neo4j_manager import neo4j_manager
await neo4j_manager.create_vector_index(dimension=384)
```

## Performans Notu
Embedding üretimi sadece `Episode` READY durumuna geçtiğinde (arka plan worker'da) ve retrieval sırasında (sorgu bazlı) yapılır. Bu durum API gecikmesini minimumda tutar.
