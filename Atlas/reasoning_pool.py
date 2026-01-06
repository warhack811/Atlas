import random

SYNTHESIS_THOUGHTS = [
    "Veriler toplandı, stratejik harekat planı tamamlanıyor ve yanıtınız oluşturuluyor...",
    "Tüm kaynaklar tarandı, elde edilen bilgiler sentezleniyor...",
    "Analiz tamamlandı, bulgular kullanıcı dostu bir formata dönüştürülüyor...",
    "Bilgi parçacıkları birleştiriliyor, en yüksek kalitede yanıt yapılandırılıyor...",
    "Uzman raporları harmanlanıyor, size özel bir özet hazırlanıyor...",
    "Veri madenciliği bitti, çıkarımlar ana hatlarıyla netleştiriliyor...",
    "Sistematik inceleme sona erdi, nihai yanıtın üslup ayarları yapılıyor...",
    "Toplanan kanıtlar ışığında kapsamlı bir değerlendirme sunuluyor...",
    "Kaynaklar arası tutarlılık kontrol ediliyor, sonuçlar netleştiriliyor...",
    "Stratejik sentez katmanında bilgiler son kez filtreleniyor...",
    "Veri akışı durduruldu, anlamlandırma süreci başarıyla tamamlanıyor...",
    "Bilgi ağacı dallandırıldı, şimdi sizin için sadeleştiriliyor...",
    "Tüm sistemler yanıt üzerinde mutabık kaldı, metin son halini alıyor...",
    "Analiz derinleştirildi, en önemli noktalar ön plana çıkarılıyor...",
    "Çoklu veri kaynakları senkronize edildi, final raporu dökülüyor...",
    "Bağlamsal bütünlük sağlandı, yanıt estetiği üzerine odaklanılıyor...",
    "Bilgi girdileri kalite süzgecinden geçirildi, sentez aşamasına geçildi...",
    "Karar destek mekanizması sonuçları üretti, metin akışına aktarılıyor...",
    "Karmaşık veriler sadeleştirildi, anlaşılır bir yanıt hedefleniyor...",
    "Planlanan tüm adımlar kat edildi, son aşamadasınız..."
]

SEARCH_THOUGHTS = [
    "'{query}' konusu hakkında internet üzerinde kapsamlı bir araştırma yapıyorum.",
    "Dijital kütüphanelerde '{query}' izlerini sürüyorum...",
    "Küresel bilgi ağında '{query}' için en güncel verileri sorguluyorum...",
    "Web ekosistemindeki '{query}' ile ilgili güvenilir kaynakları analiz ediyorum...",
    "Bilgi okyanusunda '{query}' üzerine odaklanmış bir keşfe çıktım...",
    "En popüler dijital arşivlerde '{query}' taraması gerçekleştiriyorum...",
    "'{query}' hakkındaki en taze gelişmeleri yakalamak için ağ geçitlerini kullanıyorum...",
    "Çok boyutlu arama algoritmalarımı '{query}' için optimize ediyorum...",
    "'{query}' temalı açık kaynak verileri sınıflandırarak topluyorum...",
    "Global indekslerde '{query}' başlığı altındaki en kritik noktaları tarıyorum...",
    "Bilgi madenciliği araçlarım '{query}' için derinlemesine bir taramaya başladı...",
    "Çevrimiçi kaynakları '{query}' özelinde filtreleyerek en doğru sonuçlara ulaşıyorum...",
    "'{query}' sorgusu için akademik ve genel ağları eşzamanlı tarıyorum...",
    "Dijital ayak izlerini takip ederek '{query}' konusundaki gerçeği arıyorum...",
    "'{query}' verisini doğrulamak için çok katmanlı bir web taraması yürütüyorum...",
    "Bilgi otoyolunda '{query}' için en hızlı ve güvenilir şeritleri kullanıyorum...",
    "'{query}' hakkında veri tutarsızlıklarını gidermek için geniş bir tarama yapıyorum...",
    "Web dünyasındaki uzman görüşlerini '{query}' özelinde bir araya getiriyorum...",
    "'{query}' araması için global sunucular üzerinden veri toplama işlemini başlattım...",
    "Bilgi talebiniz için '{query}' anahtar kelimesiyle en güncel süzgeci uyguluyorum..."
]

FLUX_THOUGHTS = [
    "Hayal ettiğiniz görseli en ince ayrıntılarıyla kurguluyorum ve fırça darbelerimi vurmaya başlıyorum.",
    "Zihnimdeki fırçayı elime alarak '{prompt}' vizyonunuzu dijital tuvale aktarıyorum...",
    "Işık, gölge ve kompozisyon dengelerini '{prompt}' için optimize ederek görseli oluşturuyorum...",
    "Kreatif algoritmalarım '{prompt}' komutunuzu görsel bir şablona dönüştürüyor...",
    "Estetik bir perspektif ile '{prompt}' dünyasını piksel piksel inşa ediyorum...",
    "'{prompt}' için en uygun doku ve renk paletini seçerek üretime geçtim...",
    "Hayal gücümü '{prompt}' özelinde derinleştirip eşsiz bir tasarım hazırlıyorum...",
    "Görsel motorum '{prompt}' için gerekli tüm sanatsal detayları işliyor...",
    "'{prompt}' vizyonunuza sadık kalarak modern bir kompozisyon yapılandırıyorum...",
    "Sanatsal zekam '{prompt}' için en vurucu görselliği ortaya çıkarıyor...",
    "'{prompt}' için ışık ve derinlik katmanlarını üst üste bindirerek görseli netleştiriyorum...",
    "Dijital sanat atölyemde '{prompt}' için özel bir çalışma başlattım...",
    "'{prompt}' fikrinizi görsel bir hikayeye dönüştürmek için render işlemini başlattım...",
    "Estetik kurallar çerçevesinde '{prompt}' görselinizi en etkileyici haliyle hazırlıyorum...",
    "'{prompt}' için gerçeküstü bir derinlik ve kalite düzeyi hedefliyorum...",
    "Görsel veri bankamı '{prompt}' için en iyi sonuçları verecek şekilde tarıyorum...",
    "'{prompt}' komutunuzu sanatsal bir şahesere dönüştürmek üzereyim...",
    "Piksel yoğunluğu ve renk doygunluğunu '{prompt}' için hassas bir şekilde ayarlıyorum...",
    "'{prompt}' dünyasına bir pencere açmak için görsel üretim motorunu tetikledim...",
    "İstediğiniz '{prompt}' konseptini en kaliteli şekilde dijital ortama yansıtıyorum..."
]

WEATHER_THOUGHTS = [
    "'{city}' şehri için yerel meteoroloji istasyonlarından güncel verileri çekiyorum.",
    "'{city}' üzerindeki atmosferik basınç ve nem oranlarını analiz ediyorum...",
    "'{city}' için uydu verileri ve radar görüntülerini senkronize ediyorum...",
    "'{city}' bölgesindeki hava akımlarını ve sıcaklık dengelerini kontrol ediyorum...",
    "Bilgi bankamdaki '{city}' geçmiş hava verileriyle güncel durumu kıyaslıyorum...",
    "'{city}' için yağış olasılığı ve rüzgar hızı parametrelerini sorguluyorum...",
    "Küresel tahmin modellerini '{city}' özelinde daraltarak sonuç üretiyorum...",
    "'{city}' semalarındaki bulut yoğunluğu ve görüş mesafesini kontrol ediyorum...",
    "'{city}' sakinleri için en doğru hava tahminini simüle ediyorum...",
    "Meteorolojik sensörlerden '{city}' için anlık ısı değişimlerini okuyorum...",
    "'{city}' için gün doğumu ve gün batımı arasındaki termal döngüyü analiz ediyorum...",
    "'{city}' üzerindeki alçak ve yüksek basınç merkezlerinin konumunu doğruluyorum...",
    "'{city}' hava kalitesi ve UV indeksi verilerini taramaya başladım...",
    "'{city}' için önümüzdeki saatlere ait mikroklima tahminlerini çıkarıyorum...",
    "Bölgesel hava istasyonlarının '{city}' için paylaştığı son notları inceliyorum...",
    "'{city}' için fırtına veya ekstrem hava olayı risklerini değerlendiriyorum...",
    "'{city}' özelinde deniz seviyesi ve rakım etkili sıcaklık hesaplaması yapıyorum...",
    "'{city}' için nem kaynaklı hissedilen sıcaklık farklarını hesaplıyorum...",
    "'{city}' gökyüzündeki değişimleri anlık olarak veritabanıma aktarıyorum...",
    "'{city}' için en güncel meteoroloji bülteninden özet çıkarıyorum..."
]

def get_random_synthesis_thought() -> str:
    return random.choice(SYNTHESIS_THOUGHTS)

def get_random_search_thought(query: str) -> str:
    template = random.choice(SEARCH_THOUGHTS)
    return template.format(query=query)

def get_random_flux_thought(prompt: str) -> str:
    template = random.choice(FLUX_THOUGHTS)
    return template.format(prompt=prompt)

def get_random_weather_thought(city: str) -> str:
    template = random.choice(WEATHER_THOUGHTS)
    return template.format(city=city)
