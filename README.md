# Questioncrator

Havuz tabanlı otomatik soru üretim sistemi. Hocanın yüklediği kaynak sorulardan parametrik
şablonlar çıkarır, her şablondan matematiksel olarak doğrulanmış yeni varyantlar üretir ve
sınav kitapçığı olarak dışa aktarır. Dershaneler ve özel ders hocaları için tasarlanmıştır.

- Ürün tasarımı (bağlayıcı): `docs/superpowers/specs/2026-09-15-urun-v1-design.md`
- Uygulama planları: `docs/superpowers/plans/2026-09-15-plan-{a,b,c,d}-*.md`
- İlk tasarım notu: `docs/tasarim-v0.5.md`

## Durum

Şu an yalnızca **çekirdek motor** (Python kütüphanesi) var; çalıştırılabilir bir uygulama
(API + arayüz) henüz yok. İlerleme Plan A → B → C → D sırasıyla:

| Plan | Kapsam | Durum |
|------|--------|-------|
| A — çekirdek motor | güvenlik, şablon, doğrulama, üretim, çıktı | Task 1–4 tamam (4-ek review bekliyor), Task 5–9 bekliyor |
| B — API ve servisler | FastAPI, hesaplar, çalışma alanları, LLM katmanı | başlamadı |
| C — arayüz | React/TypeScript SPA | başlamadı |
| D — dağıtım | Docker, belgeler, kabul betiği | başlamadı |

## Pipeline

Bir kaynak sorunun sınav kağıdına giden yolu. ✅ = yazıldı ve test edildi, ⏳ = planlandı.

```
kaynak dosya (Markdown | txt/docx/pdf)
   │  1. Alım (A1)
   ▼
SourceQuestion: metin + SymPy reçetesi + kazanım + çözüm
   │  2. Şablon çıkarımı (A3)
   ▼
Template: metin ve reçetede {p0}, {p1}… parametreleri + kısıtlar
   │  3. Örnekleme (A4)  →  4. Render  →  5. Güvenli değerlendirme
   ▼
aday varyant: soru metni + çalıştırılabilir reçete + cevap
   │  6. Doğrulama (A6)  →  7. Zorluk + çeldiriciler
   ▼
doğrulanmış çoktan seçmeli soru (5 şık)
   │  8. Üretim motoru + öğrenme döngüsü (hoca puanları)
   ▼
soru bankası  →  9. Çıktı (A8): A/B kitapçık, cevap anahtarı, LaTeX, Word
```

1. **Alım (A1)** — `ingest/markdown.py` ✅: yapılandırılmış Markdown havuzunu `SourceQuestion`
   listesine çevirir (`### Çözüm` bölümü dahil). txt/docx/pdf alımı ⏳ (Plan B Task 9).
2. **Şablon çıkarımı (A3)** — `templating/extract.py` ✅: kaynak sorudaki sayıları parametreye
   çevirir. Temel kural: bir değer metindeki ve reçetedeki **tüm** geçişlerinde parametreleşir ya
   da hiçbirinde. `$…$` dışındaki bir sayı ancak nicelik olduğuna dair kanıt varsa
   parametreleşir (`3x`, `3 elma`, `5'e`, `%20`, seçenek satırı). Soru numaraları, sıra
   sayıları ve etiketler sabit kalır. Üs, alt simge, kök derecesi ve ondalık gibi güvensiz
   bağlamlar da donar.
3. **Örnekleme (A4)** — `generation/sampler.py` ✅: parametre değerlerini örnekler ve kısıtlardan
   süzer.
4. **Render** — `templating/render.py` ✅: şablon + bağlamadan soru metni ve reçete üretir; negatif
   sayı, işaret sadeleştirme, `1` katsayısı ve kuvvet önünde parantez kuralları metni reçeteyle
   tutarlı tutar.
5. **Güvenli değerlendirme** — `mathenv.py` ✅ reçeteyi kısıtlı ad alanında ve zaman aşımıyla
   çözer (bilinen iki RCE kapatıldı); `sandbox.py` ✅ ağır işleri ayrı süreçte, süre ve bellek
   sınırıyla koşar; `wire.py` ✅ işçi yanıtlarını tür etiketli JSON ile taşır (pickle yok).
6. **Doğrulama (A6)** — `verification/checks.py` ⏳ (Plan A Task 5): üretilen varyantı jenerik
   kontrollerden geçirir. Örneğin kapalı biçimde değerlendirilemeyen ya da görsel olarak aşırı
   uzun cevabı reddeder (tasarım §5.2).
7. **Zorluk + çeldiriciler** — `generation/difficulty.py`, `generation/distractors.py` ⏳ (Task 6).
8. **Üretim motoru + öğrenme döngüsü** — `generation/engine.py`, `scoring/` ⏳ (Task 7–8): hoca
   puanlarından şablon ağırlığı ve zorluk kalibrasyonu.
9. **Çıktı (A8)** — `export/` ⏳ (Task 9): A/B kitapçık, tarayıcıdan yazdırma, LaTeX, Word (OMML).

Kalıcılık: `db.py` ✅ — çalışma alanı başına ayrı SQLite (WAL, şema göçleri). Veri sınıfları
`models.py` ✅, kimlikler `ids.py` ✅.

Üstüne gelecek katmanlar: `questioncrator/api` (FastAPI) → `questioncrator/services` → React SPA,
Docker ile paketlenmiş SaaS (Plan B–D). Ayrıntı: tasarım belgesi §2.

## Kurulum

    python -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"

## Test

    .venv/bin/pytest -q
    .venv/bin/ruff check .

Kurallar: testlerde mock yok (`monkeypatch.setattr`/sahte nesne yasak, gerçek davranış sınanır;
eski testlerde kalan 3 `setattr` sıradaki "mock temizliği" görevinde kaldırılacak);
`questioncrator/**/*.py` konu bağımsızdır (`tests/test_topic_agnostic.py`). Linux'a özgü bellek
sınırı testleri macOS'ta atlanır.
