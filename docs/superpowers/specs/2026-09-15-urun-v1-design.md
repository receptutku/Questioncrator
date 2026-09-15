# Questioncrator Ürün v1 — Tasarım (Spec)

Tarih: 2026-09-15 · Durum: onaylı (kullanıcı otonomi verdi) · Önceki: `docs/tasarim-v0.5.md`

Amaç: Faz 1 çekirdeğini (5/11 görev bitmiş) dershanelere ve özel ders hocalarına
satılabilir, barındırılan bir web ürününe dönüştürmek. v0.5'in ürün fikri aynen
geçerlidir (havuz → otomatik şablon → doğrulanmış soru → çift puanlı kart akışı →
öğrenme döngüsü → sınav/çalışma kağıdı); bu belge v0.5'i **teknik yığın, dağıtım,
kapsam ve güvenlik** açısından günceller. Çelişki olursa bu belge kazanır.

---

## 1. Kararlar ve gerekçeleri

| # | Karar | Gerekçe | Yanlışsa maliyeti |
|---|---|---|---|
| K1 | Streamlit bırakılır; **FastAPI (Python) API + React/TypeScript SPA** | Satılabilir ürün: marka, hızlı kart akışı (klavye), yazdırma düzeni, çok kullanıcı. Streamlit her etkileşimde sayfayı yeniden çalıştırır, kart başına ≤30 sn hedefini ve özgün tasarımı zorlar. | Streamlit'e göre daha fazla kod; çekirdek kütüphane aynı kaldığı için geri dönüş ucuz. |
| K2 | **Barındırılan (SaaS) çalışma + tek komutla kendi sunucusuna kurulum** (Docker) | Türkiye'de özel ders hocasına masaüstü kurulumu satmak zor; dershane birden fazla hocayla ortak havuz ister. v0.5'teki "çok kullanıcılı web servisi kapsam dışı" maddesi kaldırılır. | Kimlik doğrulama ve izolasyon kodu; aşağıdaki K3 ile küçük tutulur. |
| K3 | **Çalışma alanı (dershane) başına ayrı SQLite dosyası** + merkezi `accounts.db` | Kiracı izolasyonu fiziksel: sorgularda `workspace_id` filtresi unutma hatası imkânsız. Yedekleme/silme (KVKK) = dosya işlemi. Mevcut `db.py` fonksiyonları `conn` alarak aynen çalışır. | Çok büyük ölçekte (binlerce kiracı) Postgres'e göç gerekir; bu v1'in ölçeği değil. |
| K4 | **Reçete değerlendirmesi sertleştirilir + izole alt süreçte çalışır** | Doğrulandı: `sympify("_"+"_imp"+"ort_"+"_('os').getcwd()")` mevcut `mathenv.parse` üzerinden **kod çalıştırıyor**. Barındırılan üründe bu RCE'dir. Ayrıca zaman aşımına uğrayan iş parçacıkları sunucuda sonsuza dek CPU yer. | Değerlendirme gecikmesi (ms düzeyi); güvenlik açığına göre ihmal edilebilir. |
| K5 | **5 şıklı çoktan seçmeli** birinci sınıf; çeldiriciler **deterministik ve jenerik** üretilir (LLM'siz) | YKS/LGS formatı. Çeldirici = aynı reçetenin komşu bağlamalarla değerlendirilmesi (biçimi korunmuş yanlış cevap) + cevap düzeyi dönüşümler; hepsi SymPy ile doğrulanır. Konu adı gerektirmez. | Bazı şablonlar 4 ayrı çeldirici üretemez → soru yalnız "klasik" biçimde kullanılır. |
| K6 | **LLM sağlayıcıdan bağımsız katman, anahtar yoksa ürün LLM'siz tam çalışır** | Kullanıcı API'yi sonra bağlayacak. Somut istemci: Anthropic Messages API (httpx ile, SDK bağımlılığı yok), `ANTHROPIC_API_KEY` ile açılır. Testler betikli (scripted) istemciyle; LLM çıktıları elle yazılmış fikstürlerdir. | Sağlayıcı değişirse tek dosya. |
| K7 | **LLM her zaman doğrulayıcının arkasında** | LLM metin/reçete önerir; cevap her zaman SymPy'den gelir; giydirilmiş metin bağlama sayılarını içermezse atılır. | Bazı LLM önerileri boşa gider; yanlış cevaplı soru hocaya asla gitmez. |
| K8 | **PDF sunucuda üretilmez; tarayıcıda yazdırma görünümü** (A4 baskı CSS + KaTeX) + **Word (.docx, gerçek denklem nesneleriyle)** + **LaTeX (.tex)** | pdflatex/Chromium sunucu bağımlılığı yok; KaTeX baskı kalitesi yüksek; hocalar Word'de düzenlemek ister. | Tarayıcı "PDF olarak kaydet" adımı hocaya bir tık fazla. |
| K9 | Ödeme/abonelik altyapısı **v1 dışı** | Erken satış elle faturalanır; kayıt açık/kapalı + davet kodu yeterli. | Satış büyürse iyzico entegrasyonu ayrı iş. |
| K10 | Konu bağımsızlığı kuralı korunur, `questioncrator/` altındaki tüm `.py` dosyalarını (API dahil) bağlar | v0.5 §10. Demo havuzu `.md` dosyasıdır, kuralın dışında. | — |

---

## 2. Sistem mimarisi

```
tarayıcı (React SPA, Türkçe)
   │  /api/* (JSON, HttpOnly oturum çerezi)
   ▼
questioncrator/api     FastAPI: auth, çalışma alanı çözümü, yönlendiriciler (ince)
   │
   ▼
questioncrator/services  HTTP'den bağımsız uygulama mantığı (pytest ile test edilir)
   │
   ├── accounts.py (accounts.db)       kullanıcı, çalışma alanı, üyelik, davet, oturum
   ├── db.py (workspaces/<id>.db)      havuz, şablon, soru, değerlendirme, öğrenci, sınav
   ├── sandbox.py                      izole değerlendirme süreci (zaman aşımı + öldürme)
   └── çekirdek (konu bağımsız)
         mathenv · ingest · templating · generation (sampler, engine, distractors,
         difficulty) · verification · scoring (store, weights, calibration, examples)
         · export (latex, docx, booklet) · llm (client, anthropic, tasks)
```

İstek başına: çerezden oturum → kullanıcı → üyelik → çalışma alanı SQLite bağlantısı
(WAL, `busy_timeout=5000`, `foreign_keys=ON`) açılır, istek bitince kapanır.

Veri dizini (`QC_DATA_DIR`, varsayılan `./data`):
```
data/accounts.db
data/workspaces/<workspace_id>.db
```

---

## 3. Güvenlik (K4 ayrıntısı)

### 3.1 Reçete dili sertleştirme (`mathenv`)
Ayrıştırmadan önce `tokenize` ile jeton düzeyinde denetim; herhangi biri ihlal
edilirse `UnsafeExpression`:
- `STRING` jetonu (f-string dahil) yasak — reçete dizge gerektirmez.
- `_` ile başlayan her ad yasak.
- Ad alanından çıkarılan ve jeton olarak da yasaklanan tehlikeli adlar
  (`mathenv.DENIED_NAMES`, testle korunur): `sympify`, `S`, `parse_expr`, `lambdify`,
  `preview`, `plot` ile başlayan adlar, `init_printing`, `init_session`, `var`,
  `pprint`, `pretty_print`, `print_` ile başlayan adlar, `interactive_traversal`,
  `exec`/`eval`/`open`/`compile`/`getattr`/`globals`/`locals`/`vars`. Yan etkisiz
  diğer tüm sympy adları serbesttir. İlke: dizge yasağı + alt çizgi yasağı birincil
  koruma, ad listesi ikincil.
- Uzunluk üst sınırı: 2000 karakter. Büyük tamsayı literali üst sınırı: 6 hane.
- `__builtins__` boş ad alanı korunur.

### 3.2 İzole değerlendirme (`sandbox.py`)
- Çekirdek işler (şablon çıkarımı, üretim partisi, reçete önizleme) API sürecinde
  değil, **forkserver** bağlamlı kalıcı işçi süreçlerde çalışır (sympy ön yüklü).
- Her işin toplam süresi sınırlıdır (önizleme 10 sn, parti 90 sn). Aşılırsa işçi
  `kill` edilir, yenisi başlatılır, API `422/504` benzeri Türkçe hata döner.
- Linux'ta işçi başına bellek sınırı (`RLIMIT_AS`, 1 GB).
- Testlerde `QC_SANDBOX=inline` ile süreç içi çalıştırma mümkündür.

### 3.3 Hesap güvenliği
- Parola: `hashlib.scrypt` (n=2^14, r=8, p=1, 16 bayt tuz), en az 8 karakter.
- Oturum: 32 bayt rastgele belirteç, veritabanında SHA-256 özeti; çerez `HttpOnly`,
  `SameSite=Lax`, `Secure` (`QC_COOKIE_SECURE=1`), 30 gün kayan süre.
- Durum değiştiren her istek JSON veya multipart; CORS yok (aynı köken).
- Giriş denemesi sınırlaması: e-posta+IP başına 10 dk'da 10 deneme (bellekte).
- Rol: `owner` (üye yönetimi, çalışma alanı silme) / `teacher`.
- Yüklenen dosya boyutu ≤ 15 MB; türler: `.md .txt .docx .pdf .png .jpg .jpeg`.

---

## 4. Veri modeli (çalışma alanı veritabanı)

Şema `PRAGMA user_version` ile sürümlenir; `db.migrate(conn)` sıralı göçleri uygular.
Kimlikler önekli rastgele: `s_…`, `t_…`, `q_…`, `st_…`, `ex_…` (12 onaltılık hane).
Kimlik üretimi dışarıdan verilir (`id_factory`), testlerde deterministik.

- `source_questions`: id, text, recipe?, answer_text? (hocanın insan dilinde cevabı),
  objective?, needs_review, origin (`markdown|manual|file|llm`), review_note?, created_at
- `templates`: v0.5 alanları + `difficulty_estimate` (1-10 gerçel)
- `generated_questions`: v0.5 alanları + `choices` (JSON, LaTeX dizeleri, boş = klasik),
  `correct_index`?, `difficulty_estimate`, `student_id`?, `created_by`?, `archived`
- `reviews`: v0.5 alanları + `reviewer_id`?
- `students`: id, alias, weak_objectives (JSON), level (1-10)?, created_at, archived
- `student_questions`: student_id, question_id, assigned_at (verilen = çalışma kağıdına girmiş)
- `exams`: id, title, kind (`exam|worksheet`), student_id?, question_ids (JSON),
  settings (JSON: format `mc|open`, booklets `["A"]|["A","B"]`, seed), created_by?, created_at

Öğrenci verisi yalnız rumuz + zayıf kazanımlar + seviye (v0.5 gizlilik kararı).

Hesap veritabanı: `users(id, email UNIQUE, name, password_hash, created_at)`,
`workspaces(id, name, created_at)`, `memberships(user_id, workspace_id, role)`,
`invites(code, workspace_id, role, created_by, expires_at, used_at?)`,
`sessions(token_hash, user_id, workspace_id, expires_at)`.
v1'de kullanıcı tek çalışma alanına üyedir (dershane ya da tek başına hoca).

---

## 5. Çekirdek boru hattı değişiklikleri

### 5.1 Metin render düzeltmeleri (mevcut hatalar, doğrulandı)
- `render_text` `str.format` kullanıyor: LaTeX'li metinde (`\frac{...}{x}`) `KeyError`.
  → Yalnız `{p\d+}` yer tutucuları regex ile değiştirilir.
- Negatif değerler: `3x^2 + -4x - -4` → işaret sadeleştirme: `+ -a`→`- a`,
  `- -a`→`+ a`; baştaki `+` atılır.
- Katsayı 1: yer tutucu hemen bir harf/`\`/`(` önündeyse `1`→ boş, `-1` → `-`.
- Metin ve reçete aynı bağlamayı kullanır; reçete tarafı değişmez (parantezli).

### 5.2 Doğrulayıcı (`verification/checks.py`)
Faz 1 planındaki 6 kontrol + iki ek jenerik kontrol:
- **Değerlendirilmemiş işlem:** `answer.doit() != answer` → ret ("kapalı biçim yok").
- **Görsel estetik:** `len(latex(answer)) > 160` → ret.

### 5.3 Üretim motoru (`generation/engine.py`)
Faz 1 planı + :
- **Ağırlıklı şablon seçimi** (öğrenme döngüsü §2.2): ağırlık =
  `(approved+1)/(reviewed+2) × (avg_quality_smoothed/10)`, deneme şablonuna
  parti başına `TRIAL_BATCH_CAP=2`, `disabled` hiç.
- **Hedef zorluk** verilirse: kalibre zorluğu hedefe `|fark| ≤ 2` olan şablonlar
  tercih; yoksa en yakınlar.
- **Hariç tutma:** `seen_answer_keys` (genel kopya) + öğrenci bağlamında
  `avoid_templates` (öğrenciye verilmiş şablonlar; ancak kota dolmazsa kullanılır ve
  kart `similar_given=True` işaretlenir).
- Her soru için çeldirici denemesi (§5.4) ve zorluk tahmini (§5.5).

### 5.4 Çeldiriciler (`generation/distractors.py`)
Aday kaynakları, sırayla:
1. Bağlama komşuları: tek parametre `±1`, işaret çevirme (reçete aynı, cevap farklı).
2. Cevap dönüşümleri: `-answer`; cevaptaki her tamsayı atomu için `±1`.
Süzgeç: doğrulayıcıdan geçer, `simplify(aday - doğru) != 0`, LaTeX'leri birbirinden
ve doğrudan farklı. 4 çeldirici bulunursa şıklar `rng` ile karıştırılıp
`choices` + `correct_index` yazılır; bulunamazsa `choices=[]`.

### 5.5 Zorluk tahmini ve kalibrasyon
- Tahmin (1-10, jenerik): cevap `count_ops`, reçete `count_ops`, parametre sayısı ve
  en büyük mutlak sayının logaritmasının ağırlıklı toplamı, 1-10'a kırpılır.
- Kalibrasyon: şablon ≥3 puan aldıysa kalibre zorluk = hocanın ortalama zorluk puanı;
  aksi halde tahmin + çalışma alanı genel sapması (hoca puanı − tahmin ortalaması).
- Panel metriği: ilk 100 karttan sonra ortalama |sapma|.

### 5.6 Öğrenme döngüsü metrikleri (`scoring/`)
`store.template_scores`, `apply_status_transitions` (Faz 1 planı Task 8), `weights`,
`calibration`, `examples.few_shot_examples(conn, objective, k=3)` (onaylı ve
kurgu ≥ 8), `stats.learning_stats(conn)`: toplam kart, onay oranı, ort. kurgu, ilk 50 vs
son 50 karşılaştırması, zorluk sapması, şablon durum sayıları.

---

## 6. Alım (A1)

| Girdi | LLM yokken | LLM varken |
|---|---|---|
| `.md` yapılandırılmış | `ingest/markdown.py` (mevcut) — `### Soru/Cevap/Kazanım`, ek olarak `### Çözüm` (insan dilinde cevap) | aynı; reçetesiz sorulara reçete önerisi |
| `.txt .docx .pdf` | metin çıkarılır (`python-docx`, `pypdf`), numaralı soru bölücü (`1.`, `1)`, `Soru 1`) ile ayrılır; hepsi `needs_review` | LLM metni soru/cevap/reçete/kazanım yapısına çevirir; reçete doğrulanamazsa `needs_review` |
| `.png .jpg` | reddedilir ("görsel okuma için LLM gerekli") | LLM görsel girdi ile aynı yapı |

"Elle kontrol" kuyruğu ekranı: hoca metni, cevabı, kazanımı düzeltir; reçeteyi yazar ya
da "Reçete öner" (LLM) der; **Önizle** reçeteyi değerlendirip cevabı, bulunan
parametreleri ve 3 örnek varyantı gösterir. Kaydedince şablon çıkarımı çalışır.

---

## 7. LLM katmanı (`llm/`)

- `client.py`: `LLMClient` protokolü — `complete(prompt, *, system, max_tokens, images=()) -> str`;
  `NullLLMClient`, `ScriptedLLMClient(responses)`; `get_client()` ortamdan seçer.
- `anthropic.py`: Messages API, `httpx`, zaman aşımı, 429/5xx yeniden deneme (3, üstel).
  Model `QC_LLM_MODEL` (varsayılan güncel Claude modeli).
- `tasks.py` (her biri JSON çıktı ister, `json` ayrıştırılamazsa bir kez yeniden sorar,
  sonra `LLMTaskFailed`):
  - `structure_questions(text | images) -> list[DraftQuestion]`
  - `suggest_recipe(question_text, answer_text?) -> str`
  - `dress_question(question, bindings, examples) -> str` — sonuç metni her bağlama
    değerini içermiyorsa reddedilir; hoca kartında "giydirilmiş" rozeti.
- Giydirme v1'de kart başına isteğe bağlı ("Metni güzelleştir" düğmesi), otomatik değil
  (maliyet kontrolü).

---

## 8. API yüzeyi (`/api`)

- `auth`: `POST register {name,email,password,workspace_name,load_demo}`, `POST login`,
  `POST logout`, `GET me`, `POST join {code,name,email,password}`
- `workspace`: `GET`, `PATCH {name}`, `GET members`, `POST invites`, `DELETE members/{id}`,
  `GET backup` (owner: çalışma alanı .db indir), `DELETE` (owner, onay metniyle)
- `pool`: `GET summary`, `GET sources?filter=`, `POST upload` (multipart), `POST sources`,
  `PATCH sources/{id}`, `DELETE sources/{id}`, `POST preview-recipe`,
  `POST sources/{id}/suggest-recipe`, `GET objectives`
- `cards`: `POST generate {count, objectives?, target_difficulty?}`, `GET pending`,
  `POST {id}/review {approved,difficulty,quality}`, `DELETE {id}/review` (geri al),
  `POST {id}/dress`
- `questions`: `GET ?status=approved&objective=&difficulty_min=&difficulty_max=`, `PATCH {id} {archived}`
- `exams`: `POST {title, kind, question_ids? | auto{count, objectives{obj:weight}, difficulty?}, format, booklets}`,
  `GET`, `GET {id}` (kitapçıklara göre sıralı sorular + cevap anahtarı), `GET {id}/docx?booklet=&answers=`,
  `GET {id}/tex?booklet=&answers=`, `DELETE {id}`
- `students`: CRUD, `POST {id}/generate {count}`, `GET {id}/history`, `POST {id}/worksheet {question_ids}`
- `stats`: `GET` (panel)
- `system`: `GET health`, `GET config` (llm açık mı, kayıt açık mı, sürüm)

Hata biçimi: `{"detail": "<Türkçe mesaj>"}`; doğrulama hataları 422.

---

## 9. Arayüz (web/)

Vite + React + TypeScript, Tailwind CSS, React Router, TanStack Query, KaTeX.
Metin içindeki `$...$` / `$$...$$` KaTeX ile, cevaplar LaTeX olarak çizilir.

Ekranlar:
1. **Giriş / Kayıt / Davetle katıl** — kayıtta "örnek havuzla başla" (varsayılan açık).
2. **Panel** — onay oranı, ort. kurgu, bekleyen kart, onaylı soru, öğrenme eğrisi
   (ilk 50 vs son 50), zorluk sapması; "sonraki adım" yönlendirmesi.
3. **Havuz** — sürükle-bırak yükleme, özet (toplam/hazır/elle kontrol/kazanım dağılımı),
   kaynak listesi, elle kontrol düzenleyicisi (§6), elle soru ekleme.
4. **Öneriler (kart akışı)** — üret (adet, kazanım, hedef zorluk); tek kart: metin,
   şıklar (doğru işaretli), cevap; iki kaydırıcı (başlangıçta boş — puanlamadan
   onay/red düğmesi pasif); klavye: `A` onayla, `R` reddet, `Z` geri al,
   `←/→` zorluk, `↑/↓` kurgu; ilerleme sayacı.
5. **Soru bankası** — onaylı sorular, filtre (kazanım, zorluk), seçip sınava ekleme.
6. **Sınavlar** — oluşturucu (elle seçim ya da otomatik dağılım, klasik/test, A/B
   kitapçık), liste; **yazdırma görünümü** (A4, başlık alanı: ad-soyad/sınıf/tarih,
   test ise iki sütun, cevap anahtarı sayfası, optik tipi cevap tablosu), Word/TeX indir.
7. **Öğrenciler** — liste, öğrenci sayfası: rumuz, zayıf kazanımlar (havuz kazanımlarından
   seçim), seviye, "Bu öğrenci için soru üret" (aynı kart akışı, öğrenci bağlamında),
   geçmiş, çalışma kağıdı oluştur.
8. **Ayarlar** — dershane adı, üyeler + davet kodu, LLM durumu, yedek indir, hesabı sil.

Erişilebilirlik: klavye ile tam kullanım, odak halkaları, kontrast AA. Mobil: kart
akışı ve listeler tek sütuna iner (hoca telefondan kart puanlayabilir).

---

## 10. Çıktılar (A8)

- `export/booklet.py`: sınav → kitapçık başına soru sırası ve şık sırası (tohumdan
  deterministik), cevap anahtarı (`1-C` biçimi) — yazdırma, docx, tex hepsi bunu kullanır.
- `export/latex.py`: metinde `$...$` dışındaki LaTeX özel karakterleri kaçışlanır.
- `export/docx.py`: `python-docx`; `$...$` ve cevaplar `latex2mathml` → `mathml2omml`
  ile Word denklemi; dönüşüm başarısızsa düz metin.
- Yazdırma görünümü frontend'dedir (K8).

---

## 11. Demo içeriği

`questioncrator/demo/havuz.md`: TYT/AYT düzeyinde, reçeteli, `$...$` biçimli en az 30 soru,
en az 8 kazanım (çok konu). Kayıtta "örnek havuz" seçilirse yüklenir ve 10 kart
üretilmiş olarak gelir. Konu adları yalnız bu `.md` içinde geçer (K10).

---

## 12. Dağıtım ve işletim

- `Dockerfile` (çok aşamalı: node derleme → python çalışma), `docker-compose.yml`
  (tek servis, `./data` birimi), `.env.example`.
- FastAPI derlenmiş SPA'yı `/` altında sunar (SPA geri dönüşü), `/api` API.
- Ortam: `QC_DATA_DIR`, `QC_COOKIE_SECURE`, `QC_ALLOW_REGISTRATION`, `ANTHROPIC_API_KEY`,
  `QC_LLM_MODEL`, `QC_SANDBOX`.
- CLI: `questioncrator serve`, `questioncrator create-user`, `questioncrator backup`.
- README (Türkçe): kurulum, geliştirme, dağıtım, yedekleme; `docs/kullanim-kilavuzu.md`
  (hoca için), `docs/havuz-formati.md`.

---

## 13. Test ve kalite kapıları

- Backend: `pytest -q` (çekirdek, servisler, API — FastAPI `TestClient`), `ruff check .`.
- Konu bağımsızlığı bekçi testi tüm `questioncrator/**/*.py`'yi tarar.
- Güvenlik testleri: §3.1 kaçış denemeleri (dizge, alt çizgi, yasak adlar), çalışma
  alanları arası erişim (A'nın oturumuyla B'nin sorusu 404), oturum/rol kontrolleri.
- LLM görevleri betikli istemciyle; fikstür yanıtları elle yazılır.
- Frontend: `tsc --noEmit`, `vitest` (render/biçim yardımcıları), `vite build`.
- Uçtan uca: Playwright ile kayıt → demo havuz → kart puanla → sınav oluştur → yazdır
  görünümü akışı (yerelde çalıştırılır).
- Her büyük adım sonunda bağımsız kod incelemesi; bulgular ikinci bir geçişle
  doğrulanır, sonra düzeltilir.

## 14. Kapsam dışı (v1)

Ödeme/abonelik, öğrenci girişi, otomatik performans takibi, şekil/grafikli sorular,
ispat soruları, sözel dersler, çoklu çalışma alanına üyelik, e-posta gönderimi
(parola sıfırlama owner tarafından CLI ile), vektör tabanlı yakın kopya kontrolü.
