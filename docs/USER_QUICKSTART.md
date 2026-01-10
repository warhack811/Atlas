# 🚀 Atlas Kullanıcı Hızlı Başlangıç Rehberi

## Giriş

Atlas, Türkçe konuşan gelişmiş bir AI asistanıdır. Sohbet arayüzü üzerinden doğal dilde etkileşim kurabilirsiniz.

---

## 🔐 Nasıl Giriş Yapılır?

1. **Tarayıcıdan aç:** `https://<ATLAS_URL>/`
2. **Otomatik oturum:** Sistem size benzersiz bir `user_id` atar (tarayıcı localStorage'da saklanır)
3. **Yeni oturum:** Sayfa yenilendiğinde aynı kullanıcı olarak devam edersiniz

> **Not:** INTERNAL_ONLY modu aktifse, sadece yetkilendirilmiş kullanıcılar erişebilir.

---

## 💬 Nasıl Soru Sorulur?

1. Metin kutusuna sorunuzu yazın
2. **Enter** tuşuna basın veya **Gönder** butonuna tıklayın
3. Atlas düşünme sürecini ve yanıtını akış halinde gösterir

### Örnek Sorular
```
✅ "Bugün hava nasıl olacak?"
✅ "Python'da liste sıralama nasıl yapılır?"
✅ "Benim adım Ali, hatırla."
✅ "Dün ne konuşmuştuk?"
```

---

## ⚠️ Nelere Uygun Değil?

| Konu | Neden |
|------|-------|
| Gerçek zamanlı veri (borsa, canlı skor) | API entegrasyonu sınırlı |
| Yasal/tıbbi tavsiye | Profesyonel değil, sorumluluk alamaz |
| Çok uzun dökümanlar (>10K token) | Bağlam penceresi sınırı |
| Görsel oluşturma (şu an) | Worker node gerekli |
| Gizli/hassas bilgiler | PII maskelemesi var ama dikkatli olun |

---

## 🛠️ Hata Olursa Ne Yapmalı?

### 1. Sayfa Yanıt Vermiyorsa
```
→ Sayfayı yenileyin (F5)
→ Tarayıcı önbelleğini temizleyin
→ Birkaç dakika bekleyip tekrar deneyin
```

### 2. 403 Hatası Alıyorsanız
```
→ INTERNAL_ONLY modu aktif olabilir
→ Yöneticiyle iletişime geçin
```

### 3. 500 Hatası Alıyorsanız
```
→ Geçici sunucu hatası
→ Birkaç dakika sonra tekrar deneyin
→ Devam ederse yöneticiye bildirin
```

### 4. Yanıt Çok Yavaşsa
```
→ Karmaşık sorular daha uzun sürebilir
→ İnternet bağlantınızı kontrol edin
→ 60 saniyeden fazla sürüyorsa yenileyin
```

---

## 📞 Destek

Sorun devam ederse:
- Hata mesajının ekran görüntüsünü alın
- Tarayıcı konsolundaki hataları not edin (F12 → Console)
- Yöneticiye iletin

---

*Son güncelleme: 2026-01-10*
