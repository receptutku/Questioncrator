# Plan D — Dağıtım, Belgeler, Tanıtım ve Kabul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ürünü bir dershaneye kurulabilir ve satılabilir hale getirmek: tek komutla ayağa kalkan Docker paketi, hoca ve yönetici belgeleri, tanıtım sayfası, güvenlik/dayanıklılık geçişi ve tek komutlu kabul betiği.

**Architecture:** Çok aşamalı Docker imajı (node ile `web/dist` derlenir, python çalışma katmanında uvicorn ile sunulur); veri tek bir bağlı birimde (`/veri`). Ters vekil (Caddy/nginx) TLS'i üstlenir. Belgeler `docs/` altında Türkçe. Kabul betiği tüm kapıları tek komutta koşturur.

**Tech Stack:** Docker (python:3.12-slim + node:22-alpine), uvicorn, Caddy örnek yapılandırması, bash.

**Spec:** `docs/superpowers/specs/2026-09-15-urun-v1-design.md` (§12) · Önkoşul: Plan A, B, C tamam.

## Global Constraints

- Kullanıcıya ve müşteriye görünen tüm metinler Türkçe; kod/dosya adları İngilizce.
- Depoya **sır girmez**: `.env` git'e eklenmez, `.env.example` yalnız boş anahtarlar içerir.
- Docker imajı **root olmayan** kullanıcıyla çalışır; veri birimi dışında yazma yapmaz.
- Commit mesajları Türkçe conventional; **Co-Authored-By ya da benzeri iz satırı yok** (`CLAUDE.md`).
- Belgelerde yanlış vaat yok: ölçülmemiş başarı oranı, "yapay zekâ her soruyu okur" gibi iddialar yazılmaz; sınırlar açıkça yazılır.
- Hiçbir task ağ erişimi gerektiren bir adımı zorunlu kılmaz; gerekiyorsa (imaj çekme) adım "ağ yoksa BLOCKED raporla" notuyla yazılır.

---

### Task 1: Docker paketi ve çalıştırma

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example`, `docs/kurulum.md`
- Modify: `README.md` (Docker bölümü)

**Sözleşme.**
- `Dockerfile`, iki aşama:
  1. `node:22-alpine` — `web/package*.json` kopyalanır, `npm ci`, kaynak kopyalanır, `npm run build` → `/web/dist`.
  2. `python:3.12-slim` — `pyproject.toml` + `questioncrator/` kopyalanır, `pip install --no-cache-dir .`, birinci aşamadan `web/dist` → `/uygulama/web/dist`. `useradd` ile `questioncrator` kullanıcısı, `/veri` dizini ona ait. `ENV QC_DATA_DIR=/veri QC_WEB_DIST=/uygulama/web/dist QC_COOKIE_SECURE=1 QC_SANDBOX=process`. `EXPOSE 8000`. `HEALTHCHECK` → `python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/system/health')"`. `CMD ["uvicorn", "questioncrator.api.app:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]`.
- `docker-compose.yml`: tek servis `uygulama`, `./veri:/veri` birimi, `env_file: .env`, `restart: unless-stopped`, `ports: "127.0.0.1:8000:8000"` (TLS'i ters vekil üstlenir).
- `.env.example`: `ANTHROPIC_API_KEY=`, `QC_LLM_MODEL=claude-opus-5`, `QC_ALLOW_REGISTRATION=0`, `QC_COOKIE_SECURE=1`, `QC_SANDBOX_WORKERS=2` ve her satırın üstünde tek cümlelik Türkçe açıklama.
- `docs/kurulum.md`: (1) tek makinede Docker ile kurulum adımları; (2) Caddy örnek yapılandırması (otomatik TLS, `reverse_proxy 127.0.0.1:8000`); (3) ilk yönetici hesabını açma (`docker compose exec uygulama questioncrator create-user ...`); (4) kayıt kapalıyken davet kodlarıyla hoca ekleme; (5) yedekleme (günlük `questioncrator backup` cron örneği + `./veri` klasörünün kopyası, geri yükleme adımı); (6) güncelleme (`docker compose pull/build && up -d`, şema göçleri otomatik); (7) sorun giderme (log okuma, sağlık ucu, disk dolması).
- `QC_SANDBOX=process` konteynerde çalışmalı: `forkserver` başlatma yöntemi Linux'ta desteklenir; imaj içinde `.venv` yok, sistem python'u kullanılır.

- [ ] **Adım 1: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.env.example` yaz.** `.dockerignore`: `.git`, `.venv`, `web/node_modules`, `web/dist`, `data`, `veri`, `.superpowers`, `docs`, `tests`, `*.db`.
- [ ] **Adım 2: İmajı derle ve çalıştır** — `docker build -t questioncrator .` (ağ yoksa BLOCKED raporla), `docker run --rm -p 8123:8000 -e QC_COOKIE_SECURE=0 -v $(pwd)/veri-deneme:/veri questioncrator`.
  Doğrula: `curl -s localhost:8123/api/system/health` → `{"status":"ok"}`; tarayıcıda arayüz açılıyor; kayıt ol → demo havuz geliyor → bir kart üret ve puanla (sandbox alt süreci konteynerde çalışıyor demektir); `docker exec ... questioncrator list-workspaces` çalışıyor; konteyner `whoami` → root değil.
- [ ] **Adım 3: `docs/kurulum.md` ve README Docker bölümünü yaz.**
- [ ] **Adım 4: Commit** — `git commit -m "feat(dagitim): Docker imajı, compose dosyası ve kurulum belgesi"`

---

### Task 2: Hoca kılavuzu, havuz biçimi ve gizlilik belgeleri

**Files:**
- Create: `docs/kullanim-kilavuzu.md`, `docs/havuz-formati.md`, `docs/gizlilik.md`, `docs/sss.md`
- Modify: `README.md` (belgelere bağlantılar)

**Sözleşme.**
- `kullanim-kilavuzu.md` — hocanın gerçek iş akışı sırasıyla: hesap açma → havuza soru ekleme (dosya yükleme ve elle ekleme, reçete nedir, önizleme) → öneri üretme → kart puanlama (iki puanın anlamı, klavye kısayolları tablosu) → soru bankası → sınav oluşturma (test/klasik, A-B kitapçık) → yazdırma/Word → öğrenci sayfaları → panelin okunması (öğrenme eğrisi, zorluk uyumu). Her bölüm "Ne yaparsınız / Ne olur / İpucu" kalıbında, en fazla bir ekran uzunluğunda. Ekran görüntüsü yer tutucuları: `![Havuz ekranı](gorseller/havuz.png)` — görseller sonraki elle çekimde eklenecek, dosya adları sabit.
- `havuz-formati.md` — yapılandırılmış Markdown biçimi: `### Soru`, `### Cevap`, `### Çözüm`, `### Kazanım`, `---` ayracı; reçete dili kuralları (izin verilen SymPy adları, dizge yasağı, `Rational`, metindeki sayıların reçetede birebir geçmesi gerektiği), 6 çalışan örnek (farklı konulardan), sık hatalar ve düzeltmeleri.
- `gizlilik.md` — sistemin sakladığı veriler (hoca hesabı, havuz içeriği, öğrenci rumuzu ve zayıf konu etiketleri), **saklanmayanlar** (öğrenci notu, kimlik, sınav sonucu), verinin nerede durduğu (müşterinin sunucusu / tek SQLite dosyası), yedekleme ve silme (çalışma alanı silme = dosyanın silinmesi), LLM kullanıldığında hangi verinin sağlayıcıya gittiği (yalnız yüklenen soru metni/görseli ve kart metni; öğrenci rumuzu gönderilmez). Belgenin başında uyarı: "Bu metin bilgilendirme amaçlıdır; KVKK aydınlatma metniniz için hukuk danışmanınıza gösterin."
- `sss.md` — satış görüşmelerinden çıkacak sorular: "Sorularım telif açısından ne olur?" (havuz müşterinin sunucusunda kalır), "Yapay zekâ olmadan çalışır mı?" (evet, parametrik üretim + doğrulama), "Ürettiği sorular doğru mu?" (SymPy doğrulaması + hoca onayı; doğrulanamayan soru hocaya gitmez), "Kaç soru üretir?" (havuzdaki şablon ve parametre aralığına bağlı; sınır cevabın tekrarlanmaması), "Şekilli sorular?" (v1 kapsamı dışı), "Birden fazla hoca?" (davet kodu), "Verilerim nasıl yedeklenir?".
- Tüm belgelerde ölçülmemiş sayı verilmez; "hedef" olan ölçütler "hedeflenen" diye yazılır.

- [ ] **Adım 1: Dört belgeyi yaz;** `havuz-formati.md`'deki 6 örneği `.venv/bin/python -c "from questioncrator.mathenv import parse; ..."` ile doğrula ve çıktıyı rapora ekle.
- [ ] **Adım 2: README'den bağlantıları ver.**
- [ ] **Adım 3: Commit** — `git commit -m "docs: hoca kılavuzu, havuz biçimi, gizlilik ve SSS belgeleri"`

---

### Task 3: Tanıtım sayfası (giriş ekranı üstünde)

Satış görüşmesine giren bir dershane müdürü ürünü ilk burada görür. Ayrı bir pazarlama sitesi kurulmaz — uygulamanın kendi kök sayfası tanıtımı yapar.

**Files:**
- Create: `web/src/pages/LandingPage.tsx`
- Modify: `web/src/App.tsx` (oturum yokken `/` → tanıtım; oturum varken `/panel`), `web/src/pages/LoginPage.tsx` (üstte tanıtıma dönüş bağlantısı)
- Test: `web/src/pages/LandingPage.test.tsx`

**Sözleşme.**
- Tek sayfa, dört bölüm: (1) **Başlık**: "Kendi soru havuzunuzdan, doğrulanmış yeni sorular." + alt başlık (dershaneler ve özel ders hocaları için) + iki düğme: "Örnek havuzla dene" (`/kayit?demo=1`) ve "Giriş yap". (2) **Nasıl çalışır** üç adım: havuzu yükleyin → sistem doğrulanmış varyantlar üretir → puanlayın, sistem sizin ölçünüze göre öğrenir. (3) **Ne kazandırır**: dört madde — her soru SymPy ile doğrulanır, A/B kitapçık ve Word/PDF çıktı, öğrenciye özel çalışma kağıdı, veriler sizin sunucunuzda kalır. (4) **Sınırlar** (dürüstlük bölümü): şekil/grafik gerektiren sorular ve ispatlar v1'de yok; sistem hocanın onayı olmadan soru yayınlamaz.
- Ekranın altında tek satır iletişim/talep notu (yapılandırılabilir e-posta adresi metin olarak; form yok).
- Tanıtım sayfasında API çağrısı yoktur (oturum gerektirmez, hızlı açılır). Mobil uyumlu, klavyeyle gezilebilir.

- [ ] **Adım 1: Başarısız testleri yaz** — (1) başlık ve iki ana düğme çizilir, "Örnek havuzla dene" `/kayit?demo=1`e gider; (2) dört bölümün başlıkları vardır; (3) sayfa hiç `fetch` çağırmaz (`vi.spyOn(globalThis,"fetch")` çağrılmamış olmalı); (4) oturum varken `/` `/panel`e yönlenir.
- [ ] **Adım 2–3:** başarısızlığı doğrula → yaz.
- [ ] **Adım 4:** `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula** — 360 px ve 1440 px genişlikte ekran görüntüsü al, rapora yolunu yaz.
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): tanıtım sayfası"`

---

### Task 4: Güvenlik ve dayanıklılık geçişi

**Files:**
- Create: `docs/guvenlik.md`, `tests/test_hardening.py`
- Modify: bulguların gerektirdiği kaynak dosyalar

**Sözleşme — denetim listesi (her madde ya kanıtla "geçti" ya da düzeltmeyle kapanır).**
1. **Reçete sanal alanı:** `tests/test_mathenv.py` ve `tests/test_sandbox.py` mevcut; ek olarak `test_hardening.py` şu uçtan uca kapıyı doğrular: kötü niyetli reçete API üzerinden (`POST /api/pool/preview-recipe`) 422 döner, dosya sistemine yazmaz ve sunucu ayakta kalır.
2. **Kaynak tüketimi:** sonsuz döngüye yakın bir reçete (`factorial(100000)` gibi) önizlemede zaman aşımına düşer (504) ve bir sonraki istek normal yanıt verir (işçi yenilenmiş olmalı).
3. **Yükleme:** 15 MB üstü dosya 413; zip bomba benzeri docx (çok büyük açılım) için `extract_text` bellek patlatmadan hata döndürür (test: 50 MB'a açılan küçük docx üretilemiyorsa gerekçesiyle atlanır).
4. **Kimlik:** parola özeti scrypt; oturum çerezi HttpOnly+SameSite; 401/403/404 ayrımı sızdırmıyor; giriş sınırı çalışıyor (mevcut testler) — `docs/guvenlik.md`'de özetlenir.
5. **Kiracı izolasyonu:** mevcut `tests/api/test_isolation.py` + yeni test: `workspace_path` yol kaçışına kapalı (Plan B Task 2 testi), API'den gelen çalışma alanı kimliği yalnız oturumdan türetiliyor (istek gövdesinden asla).
6. **Bağımlılık taraması:** `.venv/bin/pip list --outdated` ve `npm audit --omit=dev` çıktıları rapora eklenir; yüksek/kritik bulgu varsa sürüm yükseltilir, mümkün değilse `docs/guvenlik.md`'ye gerekçesiyle yazılır. (Ağ yoksa adım atlanır, ledger'a işlenir.)
7. **Günlükleme:** sunucu günlüklerine parola, oturum belirteci, e-posta ya da soru metni yazılmıyor (grep ile doğrula).
8. **Hata sızıntısı:** beklenmeyen istisnalar istemciye iz (traceback) döndürmüyor — genel 500 gövdesi `{"detail": "Sunucuda beklenmeyen bir hata oluştu."}`; iz yalnız sunucu günlüğüne. (Gerekliyse `app.py`'ye genel istisna işleyicisi eklenir.)
9. **Eşzamanlılık:** iki çalışma alanında eşzamanlı üretim (iki iş parçacığı, `TestClient` ile) veri karışmadan tamamlanır; SQLite `database is locked` hatası vermez.

- [ ] **Adım 1: `tests/test_hardening.py`'yi yaz** (1, 2, 5, 8, 9 maddeleri için çalıştırılabilir testler).
- [ ] **Adım 2: Testleri çalıştır, kırmızı olanları düzelt** (`.venv/bin/pytest -q`).
- [ ] **Adım 3: Kalan maddeleri elle denetle, çıktıları rapora yaz.**
- [ ] **Adım 4: `docs/guvenlik.md`'yi yaz** — tehdit modeli (kötü niyetli reçete, çok kiracılı veri sızıntısı, oturum çalma, kaynak tüketimi), alınan önlemler, sınırlar (tek süreçli istek sınırı bellekte; ters vekil önerisi), olay müdahale notu (yedekten dönüş, oturumları toplu düşürme).
- [ ] **Adım 5: Commit** — `git commit -m "test(guvenlik): sertleştirme testleri ve güvenlik belgesi"`

---

### Task 5: Performans ve gerçek veri provası

**Files:**
- Create: `scripts/olcum.py`, `docs/olcumler/faz1-performans.md`
- Modify: gerekiyorsa dizin/sorgu iyileştirmeleri

**Sözleşme.**
- `scripts/olcum.py` (geliştirici aracı, pakete girmez): geçici bir çalışma alanı açar, demo havuzunu yükler, şu ölçümleri alır ve Markdown tablo yazar: (1) demo havuzu alım süresi; (2) 20 kartlık üretim süresi ve kart başına ortalama; (3) çeldirici üretilebilen kart oranı; (4) doğrulamadan geçen deneme oranı; (5) 200 soruluk bankada soru bankası sorgu süresi; (6) sınav oluşturma + docx üretme süresi; (7) veritabanı dosya boyutu.
- Hedefler (aşılırsa ya iyileştir ya gerekçeyi belgeye yaz): havuz alımı ≤ 30 sn; kart üretimi ≤ 3 sn/kart; çeldirici oranı ≥ %50; banka sorgusu ≤ 200 ms; docx ≤ 2 sn.
- Ölçüm çıktısı `docs/olcumler/faz1-performans.md` olarak işlenir (tarih, makine, sürüm, tablo, yorum).
- Ayrıca **gerçek veri provası**: `tests/data/ornek_havuz.md` dışında, kılavuzdaki biçimde 10 soruluk ikinci bir örnek havuz (`docs/ornekler/ikinci-havuz.md`) yazılır ve aynı boru hattından geçirilir — konu bağımsızlığı iddiasının pratik sınaması (tasarım §7, Faz 4 sinyali).

- [ ] **Adım 1: `scripts/olcum.py`'yi yaz ve çalıştır.**
- [ ] **Adım 2: Hedefleri aşan maddeleri iyileştir** (ör. eksik indeks, gereksiz `load_questions` çağrıları) ve ölçümü yinele.
- [ ] **Adım 3: İkinci örnek havuzu yaz ve boru hattından geçir;** başarısız olan sorular varsa nedenini belgeye yaz.
- [ ] **Adım 4: Ölçüm belgesini yaz ve commit et** — `git commit -m "docs(olcum): performans ölçümleri ve ikinci havuz provası"`

---

### Task 6: Kabul betiği ve sürüm kontrol listesi

**Files:**
- Create: `scripts/kabul.sh`, `docs/surum-kontrol-listesi.md`
- Modify: `README.md` (kabul betiği bölümü)

**Sözleşme.**
- `scripts/kabul.sh` (bash, `set -euo pipefail`): sırayla `ruff check .` → `pytest -q` → `cd web && npm run typecheck && npm run lint && npm test && npm run build` → derlenmiş arayüzle sunucuyu geçici veri dizininde başlat → `/api/system/health` bekle → Playwright e2e (kuruluysa) → sunucuyu kapat → özet tablo (her adım süre + sonuç) ve dönüş kodu. Her adım başlığı Türkçe.
- `docs/surum-kontrol-listesi.md`: sürüm çıkmadan önce yapılacaklar — kabul betiği yeşil, göç testi (eski `data/` ile yeni imaj), yedek al, `docker compose up -d`, duman testi (kayıt→kart→sınav), geri alma planı (önceki imaj etiketine dönüş), müşteriye duyurulacak değişiklikler.
- Betik ağ gerektiren adımı (Playwright kurulumu) atlar ve uyarı yazar.

- [ ] **Adım 1: Betiği yaz ve çalıştır;** çıktısını rapora ekle.
- [ ] **Adım 2: Kontrol listesini yaz.**
- [ ] **Adım 3: Commit** — `git commit -m "chore: tek komutlu kabul betiği ve sürüm kontrol listesi"`

---

## Plan D Bitiş Kontrolü

- [ ] `scripts/kabul.sh` yeşil.
- [ ] `docker compose up -d` ile temiz bir makinede kayıt → kart → sınav → yazdırma akışı çalışıyor.
- [ ] Belgeler eksiksiz: kurulum, kullanım kılavuzu, havuz biçimi, gizlilik, SSS, güvenlik, sürüm kontrol listesi.
- [ ] Tanıtım sayfası yayında ve dürüstlük bölümü içeriyor.
- [ ] Performans ölçümleri belgelenmiş; hedefi aşan madde ya düzeltilmiş ya gerekçelendirilmiş.
- [ ] Bağımsız kod incelemesi + bulguların ikinci geçişte doğrulanması.
