Aşağıdaki metin “Atlas Hafıza Anayasası (Memory Constitution)” olarak kullanılmak üzere yazıldı. Amacı: ekipte herkesin aynı tanım, aynı hedef, aynı kalite kapıları ile ilerlemesi; tartışmaları azaltıp kararları hızlandırması; ama “basite kaçmadan” riskleri kapsaması.

Atlas Hafıza Anayasası v1.0
1) Amaç ve kapsam
1.1 Amaç

Atlas’ın hafızasını; sohbet geçmişi + kısa/uzun vadeli bellek + görev/hatırlatıcı + proaktif bildirim dahil olmak üzere tek bir tutarlı sistem olarak, yüksek doğruluk ve düşük yanlış hatırlama hedefiyle tasarlamak ve hayata geçirmek.

1.2 Kapsam

Çok katmanlı bellek: Transcript/Log, Working, Episodic, Semantic, Prospective

Yazma hattı: Claim üretimi, Memory Write Gate (MWG), kimlik/alias çözümleme, çelişki-zaman yaşam döngüsü

Okuma hattı: Orchestrated retrieval + context paketleme

Proaktif motor: görev/taahhüt/hatırlatıcı + bildirim adayları

Ölçüm/test: altın set + metrikler + kalite kapıları

Kullanıcı kontrol/şeffaflık: “bende ne var?”, “unut” gibi temel kontrol yüzeyi

Not: Projenizde ayrı bir güvenlik katmanı olduğunu söylediniz; burada güvenlik detayı tartışmıyoruz.

2) Temel ilkeler (değişmez maddeler)

Log ≠ Memory: Ham transcript bir “kayıt”tır; otomatik olarak “hafıza” sayılmaz.

Claim ≠ Fact: LLM çıkarımı “iddia”dır (Claim). “Gerçek” (Fact) ancak politika/guardian ile terfi eder.

Yazmadan önce karar: MWG onayı olmadan hiçbir şey uzun vadeye ve indekslere girmez.

Belirsizde konservatiflik: Emin değilsek yazma veya UNCERTAIN/VERIFY tut.

Tek aktif gerçek kuralı (Exclusive): Exclusive predicate’lerde aynı anda tek ACTIVE vardır.

Katmanlar arası sorumluluk ayrımı:

Working: tutarlılık

Episodic: “ne oldu?”

Semantic: “kullanıcı kim ve neye inanıyoruz?”

Prospective: “ne zaman ne yapacağız?”

Açıklanabilirlik: Hafızaya yazılan her Fact, kaynağa (provenance) bağlanır.

Ölçmeden iyileştirme yok: Her faz bir test seti ve metriklerle kapanır.

3) Sözlük ve ortak tanımlar
3.1 Katmanlar

Transcript/Log: Ham konuşma satırları.

Working Memory (WM): Oturum içi kısa pencere + entity state. TTL’li.

Episodic Memory (EM): Oturum/olay özetleri + zaman + embedding.

Semantic Memory (SM): Kürate, zamanlı ve statülü kullanıcı gerçekleri/tercihleri/ilişkiler.

Prospective Memory (PM): Görevler, taahhütler, hatırlatıcılar, takip soruları.

3.2 Varlıklar ve kayıt türleri

Mention: Metindeki yüzey form (örn. “ben”, “hocam”, “Mami”).

Entity (Canonical): Tekil gerçek dünya varlığı (User, Person, Org…).

Alias: Bir entity’nin alternatif adı/lakabı.

Claim: Extractor çıktısı; doğrulanmamış iddia.

Fact: Kürate edilmiş gerçek; SM’de “ACTIVE/HISTORICAL/UNCERTAIN” statülü.

Task/Trigger: PM’de zaman/durum bağlamlı eylem.

3.3 Zorunlu metadata (Claim/Fact)

source_turn_id, recorded_at, confidence

durability: EPHEMERAL / SITUATIONAL / PERSISTENT / PERMANENT

polarity: POS / NEG

modality: CERTAIN / UNCERTAIN / HABITUAL / OCCASIONAL / PAST / HYPOTHETICAL

attribution: SELF / OTHER

inferred_tier: 0 explicit / 1 safe inference / 2 speculative

4) Sistem bileşenleri (modüler mimari)

Orchestrator: Her turda “hangi katmandan ne alınır?” kararını verir; context paketler.

Identity Resolver: Speaker-aware anchoring + alias çözümleme + belirsizlik yönetimi.

Extractor: Claim üretir (+ metadata).

MWG (Write Gate / Sieve): Claim → (DISCARD / SESSION / EPHEMERAL(TTL) / LONG_TERM_CANDIDATE / VERIFY / TASK).

Conflict & Lifecycle Engine: Exclusive/Additive kurallarına göre ACTIVE/SUPERSEDED/HISTORICAL yönetir.

Stores: Log store, WM store, EM store (summary+embedding), SM store (graph), PM store (tasks).

Retrieval Engine: Hybrid arama + kontrollü graf genişletme + re-rank opsiyonu.

Proactive Engine: PM üzerinden aday bildirim üretir, skorlar, kullanıcı tercihleri/yoğunluk limitleri ile karar verir.

Consolidation/Decay: EM → SM yoğunlaştırma, TTL/eskime, pekiştirme.

5) Politikalar (yazma/okuma/proaktif)
5.1 MWG kararı (kanonik karar seti)

Her Claim için tek karar:

DISCARD: Kaydetme

SESSION: WM’ye

EPHEMERAL(TTL): EM’ye (kısa ömür)

LONG_TERM_CANDIDATE: SM’ye aday

VERIFY: Doğrulama kuyruğu (soru sorulacak)

TASK: PM’ye (hatırlatıcı/taahhüt)

MWG değerlendirme boyutları (zorunlu):

stability, utility, recurrence, confidence, user-intent

modality/attribution/polarity

“state→trait risk” (yanlış genelleme riski)

5.2 Inference boundary (çıkarım anayasası)

Tier 0 (explicit): yazılabilir

Tier 1 (safe inference): inferred=true + düşük/orta güven ile yazılabilir veya VERIFY

Tier 2 (speculative): SM’ye yazılmaz (en fazla VERIFY adayına dönüşür)

5.3 Predicate tipleri

Exclusive: tek ACTIVE (örn. medeni durum)

Additive: birikimli (hobi/ilgi alanı) → “pekiştirme/weight”

Set-like: üyelik listesi (diller, cihazlar…) → ekle/çıkar semantiği

Temporal: “geçmişte” gibi modality=PAST ile doğrudan historical

5.4 Retrieval paketleme standardı

Model context’i 3 bölmeli verilir:

Hard Facts: ACTIVE + yüksek güven

Soft Signals: aday tercih/alşkanlık, düşük risk

Open Questions: belirsiz/çelişkili; sorulacak netleştirmeler

5.5 Proaktif motor standardı

Proaktif motor PM merkezlidir (SM’den “ödev” üretmez; ancak “aday” üretip PM’ye teklif eder).

Her bildirim adayı skorlanır:

relevance, urgency, fatigue, preference-fit, context-fit

Bildirim türleri:

passive (inbox), contextual (sohbet içinde), active (push)

6) Risk kayıt defteri (non-security)

Bu anayasa, şu riskleri “tasarım gereği” ele almak zorundadır:

Coref/kimlik hatası (Türkçe ve isim çakışmaları)

Önlem: speaker anchoring + AMBIGUOUS_REF + doğrulama kuyruğu

İroni/hipotetik yanlış kaydı

Önlem: modality=HYPOTHETICAL varsayılan DISCARD/SESSION

State→trait yanlış genelleme

Önlem: inference tier + VERIFY

Hibrit aramada gürültü

Önlem: threshold + controlled traversal + re-rank opsiyonu

MWG yanlış kalibrasyon (over/under collection)

Önlem: terfi mekanizması (ephemeral→long term), quota/decay, ölçüm döngüsü

Zaman/çelişki yönetiminde yanlış supersede

Önlem: predicate tip kataloğu + exclusive kuralı + test seti

7) Fazlar ve adımlar (adım adım, kapılı ilerleme)

Aşağıdaki fazlar sırayla ve her biri “Exit Criteria” ile kapanır. Bu, “hızlanmak için” değil, yanlış temeli erken kilitlememek için.

FAZ 0.1 — Çoklu Kullanıcı İzolasyonu + Silme Güvenliği (Zorunlu)
Amaç: “Log ≠ Memory” ve “curated memory”e geçmeden önce, grafın kime ait olduğunu deterministik yapmak.

Kapsam (anayasa maddesi olarak yazın):

FACT ilişkileri mutlaka user-scoped olmalı (write + read + observer).

Scheduler/Observer “test_user” gibi sabit kullanıcıyla çalışamaz; user listesi/registry üzerinden yürümeli.

“Forget/Delete” fonksiyonları shared Entity node silmemeli; sadece kullanıcıya ait ilişkileri/kenarları temizlemeli.

“user_id vs session_id” tanımı tekilleştirilmeli.

Exit Criteria:

Kullanıcı A’nın yazdığı hiçbir FACT, kullanıcı B’nin retrieval/observer bağlamına giremiyor.

“Unut” komutları diğer kullanıcıların grafına zarar vermiyor.

Geriye dönük veriler “güvenli varsayılan” ile ya migrate ediliyor ya da görünmez kalıyor (ama asla sızmıyor).

Faz 1 — Predicate Kataloğu + Veri Sözlüğü (Anayasa’nın iskeleti)

Amaç: LLM’in keyfine göre predicate üretmesini engellemek; lifecycle/mantık kurallarının “zeminini” oluşturmak.

PredicateCatalog:

canonical_name

type: EXCLUSIVE (tek güncel gerçek) vs ADDITIVE (çoklu birikir)

default_durability, default_modality, default_polarity

allowed_subject/object types (User/Person/Thing/Place)

“Mapping layer”: LLM’den gelen predicate → katalog canonical’ına map.

✅ Kabul kriteri: Neo4j’ye yazılan predicate’lerin %95+’i katalogdan geliyor; kalan %5 “UNKNOWN_PREDICATE” olarak işaretlenip MWG’den geçmeden yazılmıyor.

Faz 2 — Claim modeli + Provenance + Metadata şeması

Amaç: “Claim ≠ Fact” ayrımı; denetlenebilirlik; conflict çözümü için temel veri.

Minimum metadata (anayasa uyumlu):

source_turn_id (hangi mesajdan çıktı)

created_at, updated_at

confidence

durability (EPHEMERAL/SITUATIONAL/PERSISTENT/LONG_TERM)

modality (CERTAIN/OCCASIONAL/PAST/HYPOTHETICAL vs.)

polarity (POS/NEG)

attribution (SELF/OTHER)

inferred flag (çıkarım sınırı için)

✅ Kabul kriteri: Yeni yazılan her kayıt bu alanları taşıyor (boş/None değil).

Faz 3 — Identity Resolver (Ben/Sen + alias + ambiguous ref)

Amaç: “Ben/Sen/Hoca/O” kirlenmesini bitirmek; alias/same_as yapısını kurmak.

Preprocess: “Ben → CURRENT_USER”, “Sen → ASSISTANT” deterministik

Entity resolution: alias graph (lakap/resmi ad/yanlış yazım)

Ambiguous ref: düşük confidence ile “AMBIGUOUS_REF” bırakıp MWG/Guardian’a paslamak

✅ Kabul kriteri: Yeni gelen mesajlarda “Ben” gibi surface-form’lar Entity node olarak çoğalmıyor.

Faz 4 — MWG (Write Gate) + TTL/Decay

Amaç: Hafızayı “log” olmaktan çıkarıp “curated memory” yapmak.

Çıkış: DISCARD / SESSION / EPHEMERAL(TTL) / LONG_TERM

Skorlar: stability, utility, recurrence, confidence, intent, sensitivity (siz güvenliği ayrı katmanda çözdüğünüz için burada sadece hafıza kalitesi açısından kullanın)

TTL/decay: EPHEMERAL otomatik düşer, tekrar ederse terfi eder.

✅ Kabul kriteri: Uçucu mesajların (açım/evdeyim) %90+’ı grafa yazılmıyor.

Faz 5 — Lifecycle & Conflict Engine

Amaç: Bekarım→Evlendim gibi “exclusive” predicate’lerde tek güncel gerçek + tarihsel kayıt.

Exclusive predicate’lerde: ACTIVE / SUPERSEDED

Additive predicate’lerde: weight/recency güçlendirme

“Negation-first”: sevmiyorum geldiğinde seviyorum’u zayıflat vs.

✅ Kabul kriteri: Exclusive predicate’te aynı anda 2 ACTIVE yok.

Faz 6 — Retrieval Orchestrator (Hard/Soft/Open paketleme + hibrit arama)

Amaç: Context’i “ne varsa bas” değil, kontrollü paketlemek.

Hard facts (yüksek confidence + active)

Soft signals (alışkanlık / düşük confidence)

Open questions (doğrulanması gerekenler)

Hibrit: keyword + semantic (sonra)

✅ Kabul kriteri: Yanıt token’ının %X’i “alakalı hafıza” (ölçümle).

Faz 7 — Prospective (Görev/hatırlatıcı) + proaktif motoru kalıcılaştırma

Amaç: Observer’ın RAM kuyruğu yerine kalıcı PM; kullanıcı yorgunluğu kontrolü.

“test_user” sabitinden çıkmak (şu an sabit 

scheduler

)

Bildirimlerin DB’de tutulması

Fatigue + izin + gerekçe alanları

✅ Kabul kriteri: Restart sonrası bildirim/task kaybolmuyor; kullanıcı bazlı çalışıyor.

8) Değişiklik yönetimi (Anayasa nasıl güncellenir?)

Her kural değişikliği ADR (Architecture Decision Record) ile yapılır:

Problem

Alternatifler

Karar

Etkiler (hangi testler güncellenecek)

Anayasa versiyonlanır: v1.0, v1.1…

9) Bu anayasa ile günlük çalışma rutini

Her yeni özellik önce katalog + test setine girer, sonra koda.

Her PR:

ilgili “faz” exit kriterine hizmet etmeli

altın setin ilgili bölümünü geçmeli

reason-code/trace üretmeli