# Havuz Tabanlı Otomatik Soru Üretim Sistemi
## Teknik Tasarım Dokümanı — v0.5

**Değişiklik özeti:** Hocaya görünen yüzey üç ekrana indirildi: havuz yükleme, soru onaylama, öğrenci sayfaları. v0.4'teki şablon atölyesi hocanın önünden kaldırıldı ve arka plana gömüldü — şablonlar otomatik çıkarılır, kalite kapısı soru seviyesindeki onay + puanlamadır. Yeni: her onay/redde eşlik eden çift puan (zorluk /10, kurgu /10) sistemin öğrenme sinyalidir. Yeni: öğrenci başına özel sayfa — hocanın belirlediği zayıf kazanımlara odaklı üretim.

---

## 1. Hocanın Gördüğü Sistem

Üç sekme. Başka hiçbir şey yok.

### Sekme 1 — Havuz

Hoca dosyalarını sürükler bırakır. Format serbest: Word, PDF, LaTeX, fotoğraf, tarama. Sistem arka planda ayrıştırır; okuyamadığı soruları "elle kontrol gerekli" listesinde gösterir, hoca isterse düzeltir isterse atlar.

Havuz ekranında hoca şunu görür: kaç soru yüklendi, konulara dağılımı, kaçı işlenmeye hazır. O kadar.

### Sekme 2 — Soru Önerileri

Sistemin ürettiği sorular tek tek kart olarak gelir. Her kartta:

- Soru metni + çözümü (çoktan seçmeliyse şıklar ve doğru cevap işaretli)
- **Zorluk puanı:** 1-10 kaydırıcı
- **Kurgu puanı:** 1-10 kaydırıcı (soru iyi kurulmuş mu, gerçekçi mi, kazanımı gerçekten ölçüyor mu — hocanın öznel kalite yargısı)
- **Onayla / Reddet** düğmesi

Kural: puanlamadan onay/red verilemez. İki kaydırıcı + bir düğme, kart başına 20-30 saniye.

Hoca yeterince soru onayladığında **"Dosya oluştur"** der: onaylı sorulardan sınav kağıdı + cevap anahtarı (PDF/Word) iner. İsterse dağılım belirtir ("20 soru, ağırlık türev, orta zorluk"), istemezse sistem dengeli dağıtır.

### Sekme 3 — Öğrenciler

Hoca öğrenci ekler (sadece bir isim/rumuz). Her öğrencinin kendi sayfası açılır. Sayfada:

- Hocanın işaretlediği **zayıf konular/kazanımlar** listesi (elle seçer: "Ali türev uygulamalarında ve limitte zayıf")
- **"Bu öğrenci için soru üret"** düğmesi: üretim o kazanımlara odaklanır, zorluk hocanın seçtiği seviyeden başlar
- Aynı kart akışı: puanla, onayla, öğrenciye özel çalışma kağıdı indir

Öğrenci sayfaları geneldeki onay/puan verisinden beslenir ama kendi geçmişini de tutar: Ali'ye daha önce verilen sorular tekrar üretilmez.

**Gizlilik notu:** sistemde öğrenciye dair tek veri, hocanın girdiği isim/rumuz ve işaretlediği zayıf konulardır. Not, sınav sonucu, kişisel veri toplanmaz; hoca rumuz kullanmaya teşvik edilir. Veri hocanın makinesinde durur.

---

## 2. Öğrenme Döngüsü: Puanlar Nasıl Kalite Üretir

Hocanın verdiği her puan çifti + onay/red kararı kaydedilir. Bu veri üç yerde kullanılır:

1. **Örnek seçimi.** LLM'li üretimde isteme eklenen few-shot örnekler, artık havuzdan rastgele değil, **hocanın yüksek kurgu puanı verdiği onaylı sorulardan** seçilir. Model her üretimde "bu hocanın iyi dediği" soruları örnek alır.
2. **Şablon ağırlıklama.** Her arka plan şablonunun bir skoru oluşur: ondan üretilen soruların ortalama kurgu puanı ve onay oranı. Düşük skorlu şablonlardan üretim azaltılır, sürekli reddedilenler devre dışı kalır. Hoca şablon diye bir şey görmez ama fiilen şablon eliyor.
3. **Zorluk kalibrasyonu.** Sistemin ürettiği zorluk hedefi ile hocanın verdiği zorluk puanı karşılaştırılır. Sapma sistematikse (sistem "orta" dediğine hoca hep 8 veriyorsa) şablonun zorluk eşlemesi otomatik kayar. Zorluk, spekülasyon olmaktan çıkıp hocanın kendi ölçeğine oturur.

Mekanizma hakkında açık olalım: model ağırlıkları değişmez, "LLM'in kendisi öğrenmez." Öğrenen şey sistemdir — puan verisi örnek seçimini, şablon ağırlıklarını ve zorluk eşlemesini sürekli günceller. Hoca açısından sonuç aynıdır: puanladıkça öneriler onun zevkine yaklaşır. İlk 50-100 puanlamadan sonra fark edilir hale gelmesi beklenir; bu eşik ölçüm planına dahildir.

---

## 3. Arka Plan Mimarisi

Hocaya görünmeyen kısım. v0.4'ün boru hattı korunur, iki değişiklikle: şablon onayı içselleşti, puan deposu ve öğrenci kaydı eklendi.

```
[Yükleme]
    |
    v
 A1  ALIM               her format -> soru nesnesi; düşük güvenliler
    |                   "elle kontrol" kuyruğuna
    v
 A2  GRUPLAMA           kazanım/tip etiketi; etiket yoksa embedding kümeleme
    |
    v
 A3  ŞABLON ÇIKARIMI    otomatik: varyant keşfi + iskelet + doğrulama planı
    |                   (hoca onayı YOK; kalite kapısı aşağıda, soru seviyesinde)
    v
 A4  ÜRETİM MOTORU      varyant seç -> parametre örnekle -> SymPy kısıt süz
    |
    +--> A5  LLM KATMANI    giydirme + çeldirici; few-shot = yüksek puanlı onaylılar
    |
    v
 A6  DOĞRULAYICI        SymPy: çözülebilirlik, teklik, cevap, çeldirici
    |
    v
 A7  KART AKIŞI         onay + zorluk/kurgu puanı (hocanın Sekme 2'si)
    |
    +--> PUAN DEPOSU ----geri----> A3 şablon ağırlıkları, A5 örnek seçimi,
    |                              zorluk kalibrasyonu
    v
 A8  ÇIKTI              PDF/Word sınav + cevap anahtarı; öğrenci kağıtları
```

### Şablon onayının kaldırılmasının bedeli ve telafisi

v0.4'te hatalı şablon, hoca onayında yakalanıyordu. Şimdi hatalı şablon üretime girer ve kötü sorular üretir. Telafi üç katmanlı:

1. SymPy doğrulayıcı matematiksel hataları zaten süzer (bu değişmedi).
2. Kurgusal hatalar (anlamsız, kötü kurulmuş soru) hocanın red + düşük kurgu puanıyla yakalanır ve şablon ağırlığını düşürür — hatalı şablon birkaç red içinde kendini devre dışı bırakır.
3. Yeni bir şablon ilk kez üretime girdiğinde "deneme modu"ndadır: ondan aynı anda en fazla 2 soru öneriye çıkar. İlk onayları alana kadar hacim verilmez. Böylece hatalı şablon en kötü ihtimalle 2 kötü kartla sınırlı kalır, 20 kartlık bir çöp dalgası yaratamaz.

### Öğrenci sayfalarının arka planı

- Öğrenci kaydı: `{rumuz, zayif_kazanimlar[], verilen_soru_idleri[], sayfa_puan_gecmisi}`
- Üretim isteği öğrenci bağlamında gelirse: kazanım filtresi = zayıf kazanımlar, tekrar filtresi = verilen sorular + onların kaynak şablonundaki yakın komşuları (aynı sorunun sayısı değişmiş halini "yeni soru" diye vermemek için yapısal benzerlik eşiği uygulanır).
- Öğrenciye özel zorluk: sayfa geçmişindeki puanlardan başlangıç seviyesi; hoca elle ezebilir.

---

## 4. LLM Kullanım Haritası

| # | Yer | İş | Sıklık |
|---|---|---|---|
| 1 | A1 | Ayrıştırma yardımı: serbest formatlı metinden soru/çözüm/şık ayırma | Yüklemede, soru başına 1 (yalnız belirsiz formatlarda) |
| 2 | A3 | Varyant keşfi + iskelet çıkarımı | Şablon başına 1, kalıcı |
| 3 | A5 | Giydirme + çeldirici (birleşik istem, few-shot puan verisiyle) | LLM'li üretimde soru başına 1 |

"Her format serbest" kararının maliyeti 1. satırdadır: taranmış/fotoğraf girdilerde matematiksel OCR (Mathpix vb.) devreye girer ve havuz yüklemesi projenin en pahalı tek seferlik işlemi olur. Bu bedel yükleme anında bir kez ödenir, üretimde tekrarlanmaz.

---

## 5. Teknoloji Yığını

| Katman | Seçim |
|---|---|
| Uygulama | Tek Python paketi + Streamlit (3 sekme) |
| Veritabanı | SQLite (+ sqlite-vec gerekirse) |
| Sembolik | SymPy |
| OCR | Mathpix API (tarama/fotoğraf girdisi için) |
| Embedding | sentence-transformers, yerel |
| LLM | Tek sağlayıcı, ince istemci soyutlaması |
| Çıktı | Jinja2 -> LaTeX -> PDF; python-docx -> Word |

---

## 6. Başarı Ölçütleri

| Ölçüt | Hedef |
|---|---|
| Doğrulama geçme (parametrik) | %98+ |
| Doğrulama geçme (LLM'li) | %85 |
| Hoca onay oranı | %75 |
| Ortalama kurgu puanı | ≥ 7/10, zamanla yükselen eğim |
| Zorluk sapması (hedef vs hoca puanı) | ilk 100 karttan sonra ≤ 1.5 |
| Öğrenme kanıtı | ilk 50 kart ile son 50 kartın onay oranı ve kurgu ortalaması karşılaştırılır; anlamlı artış beklenir |
| Kart başına hoca süresi | ≤ 30 saniye medyan |

Kör test korunur: hocanın 10 sorusu + sistemin 10 sorusu karışık, ayırt etme + puanlama.

---

## 7. Yol Haritası

**Faz 0 — Havuz keşfi.** Envanter (boyut, format, şekilli oran, telif). Kod yok.

**Faz 1 — Çekirdek + kart akışı.** Pilot ünite, otomatik şablon çıkarımı, parametrik motor, doğrulayıcı, Sekme 2 (kart + çift puan + onay), PDF çıktı. Puan deposu ilk günden kayıt alır. Kör test faz sonunda.

**Faz 2 — Öğrenme döngüsü + LLM katmanı.** Few-shot puan seçimi, şablon ağırlıklama, zorluk kalibrasyonu devreye girer. Giydirme + çeldirici. Word çıktısı.

**Faz 3 — Serbest format alımı + öğrenci sayfaları.** OCR dahil tam format desteği (Sekme 1 nihai hali), Sekme 3 öğrenci sayfaları, tekrar filtresi.

**Faz 4 — Ölçek ve genelleme.** Tam havuz, gerekirse vektör kopya kontrolü, ikinci ders.

Sıralama gerekçesi: öğrenme döngüsü (Faz 2) öğrenci sayfalarından (Faz 3) önce gelir, çünkü öğrenci sayfası "iyi soru üretmeyi öğrenmiş" bir sistemin üstünde anlamlıdır.

---

## 8. Kapsam Dışı (ilk sürüm)

- Şekil/grafik gerektiren sorular (Faz 0'da oran ölçülür; TikZ parametrik şekil sonraki aday)
- İspat soruları
- Öğrencinin sisteme doğrudan erişimi (sistem yalnız hocanındır; öğrenci sadece kağıdı görür)
- Otomatik öğrenci performans takibi (zayıflıkları hoca işaretler, sistem ölçmez)
- Çok kullanıcılı web servisi
- Sözel dersler

---

## 9. Açık Sorular (Faz 0)

1. Havuz kaç soru, format dağılımı ne? (OCR bütçesinin ana girdisi)
2. Etiketleme var mı?
3. Soruların ne kadarı hocanın kendi yazımı / yayınevi kaynaklı?
4. Hedef çıktı yazılı mı, çoktan seçmeli mi?
5. Hoca haftada kaç kart puanlamaya razı? (Öğrenme döngüsünün hızını belirler)

---

## 10. Uygulama Kararları (v0.5 sonrası, plan yazımında alındı)

- **Konu bağımsızlığı zorunludur.** Pilot ünite diye ayrıcalıklı bir konu yoktur. Şablon çıkarımı, üretim motoru ve doğrulayıcı "reçete" (herhangi bir SymPy ifadesi) üzerinden çalışır; kodda türev/limit/integral/matris ayrımı geçmez. Yeni bir konu, kod değişikliği değil yeni bir kaynak sorusu gerektirir.
- **LLM sağlayıcısı Faz 1'de seçilmez.** Faz 1 yalnız soyut bir `LLMClient` protokolü ve `NullLLMClient` içerir; somut istemci Faz 2'de eklenir.
- **Faz 1 alım formatı yapılandırılmış Markdown'dır.** Serbest format (Word/PDF/OCR) Faz 3'e aittir.
