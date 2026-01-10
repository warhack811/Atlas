# ✅ Atlas Delivery Checklist

Production deploy öncesi kontrol listesi.

---

## 1. Deploy Öncesi

- [ ] `DEBUG=false` ayarlandı (`config.py` veya `.env`)
- [ ] `INTERNAL_ONLY` doğru ayarlandı
  - `true` → sadece test/alpha kullanıcıları
  - `false` → herkese açık
- [ ] `INTERNAL_WHITELIST_USER_IDS` güncellendi (gerekiyorsa)
- [ ] Tüm testler geçiyor: `pytest Atlas/tests/ -v`
- [ ] Commit mesajı anlamlı ve conventional format

---

## 2. Deploy

- [ ] `git push origin main` yapıldı
- [ ] GitHub Actions workflow başladı
- [ ] CI Gate (RC-7) geçti ✅
- [ ] Deploy to Oracle VM başladı

---

## 3. Health Check

Deploy sonrası otomatik kontrol:

```bash
# Manuel kontrol (Oracle VM üzerinde)
curl -f http://127.0.0.1:8080/api/health

# Beklenen yanıt
{"status": "ok", ...}
```

- [ ] Health check başarılı (workflow yeşil)
- [ ] Rollback tetiklenmedi

---

## 4. Rollback Senaryosu

Health check başarısız olursa workflow otomatik yapar:

| Adım | Eylem |
|------|-------|
| 1 | `git reset --hard $PREV_SHA` |
| 2 | `pip install -r requirements.txt` |
| 3 | `systemctl restart atlas` |
| 4 | Health check retry |

**Exit kodları:**
- `0` = Deploy başarılı
- `1` = Deploy fail, rollback başarılı
- `2` = KRİTİK - manuel müdahale gerekli

---

## 5. Log Kontrolü

```bash
# Oracle VM üzerinde
sudo journalctl -u atlas -n 100 --no-pager

# Aranan loglar
grep "INTERNAL_ONLY" /var/log/atlas.log
grep "ERROR" /var/log/atlas.log
grep "Health check" /var/log/atlas.log
```

- [ ] Kritik hata yok
- [ ] Memory leak işareti yok
- [ ] INTERNAL_ONLY logları beklenen davranışta

---

## 6. INTERNAL_ONLY Kontrolü

### Aktifse (INTERNAL_ONLY=true)

```bash
# Whitelist dışı kullanıcı → 403
curl -X POST http://<URL>/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"test","session_id":"s1","user_id":"random_user"}'
# → 403 Forbidden

# Whitelist içi kullanıcı → 200
curl -X POST http://<URL>/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"test","session_id":"s1","user_id":"u_admin"}'
# → 200 OK
```

- [ ] Whitelist çalışıyor
- [ ] Non-whitelist 403 alıyor

### Kapalıysa (INTERNAL_ONLY=false)

- [ ] Herkes erişebiliyor

---

## 7. Post-Deploy

- [ ] UI'dan manuel test yapıldı
- [ ] Temel soru-cevap çalışıyor
- [ ] Hafıza sistemi çalışıyor ("Adımı hatırlıyor musun?")
- [ ] Bildirimler çalışıyor (varsa)

---

## Hızlı Komutlar

```bash
# Durum kontrolü
sudo systemctl status atlas

# Loglar
sudo journalctl -u atlas -f

# Restart
sudo systemctl restart atlas

# Health check
curl -f http://127.0.0.1:8080/api/health
```

---

*Son güncelleme: 2026-01-10*
