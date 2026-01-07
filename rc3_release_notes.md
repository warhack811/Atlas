# Atlas Memory RC-3 Release Notes

## 🚀 Yeni Özellikler

### 1. Kalıcı Konuşma Geçmişi (Persistent Transcript)
- Mesajlar artık RAM yerine Neo4j üzerinde `(:Session)-[:HAS_TURN]->(:Turn)` yapısıyla saklanıyor.
- Her mesaj (Turn) otomatik index'lenir ve zaman damgasıyla kaydedilir.
- `user_id` ve `session_id` bazlı tam izolasyon ve geçmiş sorgulama desteği.

### 2. Episodik Bellek (Session Summarization)
- Uzun oturumlar için her 20 mesajda bir otomatik özetleme (Episode) tetiklenir.
- Özetler `(:Session)-[:HAS_EPISODE]->(:Episode)` olarak saklanır.
- Bu yapı, LLM'in binlerce mesajlık geçmişi "tek bakışta" anlamasını sağlar.

### 3. Hibrit Bağlam (Hybrid Retrieval V1)
- LLM'e giden bağlam artık 3 katmanlıdır:
    - **Yakın Geçmiş:** Son 12 mesaj (Transcript).
    - **Orta Geçmiş:** Son 3 episod özeti (Episodic).
    - **Uzun Geçmiş:** Kişisel olgular ve sinyaller (Context V3 Facts).
- Bu sayede Atlas, hem az önce ne dendiğini hem de bir hafta önce ne özetlendiğini hatırlar.

## 🛠 Teknik İyileştirmeler
- **Neo4jManager Expansion:** `append_turn`, `get_recent_turns`, `create_episode` metodları eklendi.
- **ContextBuilder Upgrade:** Artık varsayılan olarak V1 Hibrit Bağlamı kullanır.
- **MemoryPolicy Safety:** "OFF" modunda kişisel veriler (Facts) gizlenmeye devam ederken, konuşma akışı (Transcript) korunur.

## 🧪 Doğrulama Kanıtları
- `Atlas.test_rc3_transcript_store`: OK
- `Atlas.test_rc3_context_builder`: OK
- `Atlas.test_rc3_episode_trigger`: Logic Verified (Threshold: 20 turns)
- `RC-1/RC-2 Regressions`: OK

## 💻 Neo4j Sorguları (Doğrulama)

**Son Mesajları Gör:**
```cypher
MATCH (s:Session {id: 'session_id'})-[:HAS_TURN]->(t:Turn)
RETURN t.role, t.content, t.turn_index ORDER BY t.turn_index DESC LIMIT 5
```

**Episod Özeti Kontrolü:**
```cypher
MATCH (e:Episode) RETURN e.session_id, e.summary, e.start_turn, e.end_turn
```
