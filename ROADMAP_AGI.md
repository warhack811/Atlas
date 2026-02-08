# ATLAS v2.0: "Agentic Evolution" - Mimari Geliştirme Raporu

Mevcut Atlas mimarisi, güçlü bir **RAG (Retrieval-Augmented Generation)** ve **DAG (Directed Acyclic Graph)** tabanlı iş akışı motorudur. Ancak modern "Büyük AI" sistemleri (örn: AutoGPT, BabyAGI, OpenAI Assistants) sadece planlayıp yürüten değil, **gözlemleyen, hatalarından dönen ve dinamik araç kullanan** (ReAct) yapılardır.

Projeyi "Büyük AI" seviyesine taşımak için önerilen stratejik yol haritası aşağıdadır.

---

## 1. Mimari Dönüşüm: "Statik Planlama"dan "Dinamik Döngü"ye

**Mevcut Durum:**
`Orchestrator` bir kez çalışır -> Bir plan (JSON) üretir -> `DAGExecutor` bunu körü körüne uygular.
*Sorun:* Eğer "Arama Aracı" beklenen sonucu vermezse sistem durur veya hatalı cevap verir. İkinci bir deneme şansı yoktur.

**Öneri: Agentic Loop (ReAct / OODA Loop)**
`Plan -> Execute` yapısını `Think -> Act -> Observe -> Reflect` döngüsüne çevirmeliyiz.

*   **Döngüsel Yürütücü (Cyclic Executor):** `DAGExecutor` yerine bir `AgentRunner` gelmeli. Bu yapı, her adımın sonucunu tekrar LLM'e beslemeli.
    *   *Adım 1:* LLM: "Hava durumuna bakmam lazım." -> Tool: (Hava 25 derece)
    *   *Adım 2:* LLM: (Gözlem: Hava güzelmiş) -> "Şimdi piknik yerlerini arayayım."
    *   *Adım 3:* LLM: (Gözlem: Yerler bulundu) -> "Kullanıcıya öneri sunuyorum."

---

## 2. Araç Entegrasyonu: "Metin Bazlı"dan "Native Function Calling"e

**Mevcut Durum:**
Araçlar `ORCHESTRATOR_PROMPT` içinde metin olarak (`1. search_tool: ...`) anlatılıyor. LLM'in çıktı formatına (JSON) uyması bekleniyor.
*Sorun:* Karmaşık senaryolarda LLM JSON formatını bozabilir veya parametreleri (örn: tarih formatı) yanlış üretebilir.

**Öneri: Native Tool Use**
Gemini ve Llama-3 gibi modellerin **Native Function Calling** özelliklerini kullanmalıyız.
*   `Atlas/tools/registry.py` zaten `to_openai_function()` metoduna sahip. Bunu `orchestrator.py` içindeki API çağrısına `tools=[...]` parametresi olarak doğrudan bağlamalıyız.
*   Böylece model "metin" değil, doğrudan "çalıştırılabilir aksiyon nesnesi" üretecektir. Hata oranı %0'a yakınsar.

---

## 3. Hafıza Sistemi: "Pasif Bağlam"dan "Aktif Araştırmacı"ya

**Mevcut Durum:**
Kullanıcı mesajı gelir gelmez sistem *tahmini* olarak hafızadan veri çeker (`context.py`).
*Sorun:* Kullanıcı "Geçen ayki toplantıdaki kararları hatırlıyor musun?" dediğinde, sistem sadece "toplantı" kelimesine odaklanıp yanlış veriyi çekebilir.

**Öneri: Hafızayı Bir Araç Olarak Tanımlamak**
Hafızayı (`Neo4jManager`) sadece bağlam (context) olarak değil, bir **Araç (Tool)** olarak tanımlamalıyız: `retrieve_memory(query="...")`.
*   Agent, önce "Geçen ayki toplantı" diye arama yapar.
*   Gelen sonuç yetersizse, "2023 Ekim ayı toplantı notları" diye *kendiliğinden* ikinci bir arama yapar.
*   Bu, "Multi-Hop Reasoning" (Çok adımlı mantık yürütme) yeteneği kazandırır.

---

## 4. Kullanıcı Deneyimi: "Bekle-Gör"den "Canlı Akış"a (Streaming UI)

**Mevcut Durum:**
Kullanıcı mesajı yazar, Atlas 5-10 saniye düşünür, sonra cevabı blok halinde basar.
*Sorun:* "Büyük AI" hissini yok eden en büyük faktör gecikmedir (latency).

**Öneri: Server-Sent Events (SSE) & UI Update**
*   Backend (`DAGExecutor`), her adımı (örn: "İnternette aranıyor...", "Hafıza taranıyor...") canlı olarak frontend'e yayınlamalı.
*   Kullanıcı, Atlas'ın o an ne düşündüğünü (Thought Process) şeffaf bir şekilde görmeli.

---

## 🚀 Özet Yol Haritası (Faz 2.0)

| Adım | İşlem | Hedef |
| :--- | :--- | :--- |
| **1** | **Native Tooling** | `Orchestrator`'ı prompt-based yapıdan `API tools` parametresine geçirmek. |
| **2** | **ReAct Loop** | `DAGExecutor`'ı yinelemeli (iterative) çalışacak şekilde yeniden yazmak. |
| **3** | **Active Memory** | `Neo4j` sorgularını `retrieve_memory` aracı olarak Agent'a sunmak. |
| **4** | **Streaming UI** | `api.py` üzerinden düşünce adımlarını (thought chains) frontend'e akıtmak. |

Bu mimari, Atlas'ı basit bir "Chatbot"tan, otonom kararlar alabilen gerçek bir "AI Agent"a dönüştürecektir.
