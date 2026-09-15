# Plan C — Web Arayüzü (React + TypeScript) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hocanın gördüğü ürünü yazmak: giriş/kayıt, panel, havuz, kart akışı, soru bankası, sınavlar (yazdırma görünümü dahil), öğrenciler ve ayarlar — Türkçe, klavyeyle tam kullanılabilir, telefonda da çalışan bir tek sayfa uygulaması.

**Architecture:** `web/` altında Vite + React 19 + TypeScript + Tailwind CSS 4 + React Router 7 + TanStack Query 5. Tüm sunucu iletişimi tek bir tipli API istemcisinden (`src/api/client.ts`) geçer; oturum HttpOnly çerezle taşınır (token JavaScript'te tutulmaz). Matematik KaTeX ile çizilir. Üretim derlemesi `web/dist`'e çıkar ve FastAPI tarafından sunulur (Plan B Task 8).

**Tech Stack:** Node 20+, Vite 6, React 19, TypeScript 5 (strict), Tailwind CSS 4, React Router 7, TanStack Query 5, KaTeX, Vitest + Testing Library, Playwright (yalnız Task 9).

**Spec:** `docs/superpowers/specs/2026-09-15-urun-v1-design.md` (§9 Arayüz) · Önkoşul: Plan B (API) tamam.

## Global Constraints

- **Dil:** Kullanıcıya görünen her dize Türkçe. Kod tanımlayıcıları (değişken, bileşen, dosya adı) İngilizce. Kullanıcı metinleri bileşenlerin içinde düz yazılır (i18n katmanı yok — YAGNI).
- **TypeScript strict:** `strict: true`, `noUncheckedIndexedAccess: true`; `any` yok (`unknown` + daraltma). `tsc --noEmit` temiz olmalı.
- **API tipleri tek yerde:** `src/api/types.ts`; her uç nokta için tip, elle Plan B şemalarına göre yazılır ve `src/api/client.ts` dışında `fetch` çağrısı bulunmaz.
- **Oturum:** `credentials: "same-origin"`; 401 alındığında istemci oturumu düşürür ve `/giris`e yönlendirir. Belirteç `localStorage`'a **yazılmaz**.
- **Erişilebilirlik:** Her etkileşimli öğe klavyeyle erişilebilir; `aria-label` Türkçe; odak halkası görünür (`focus-visible`); renk kontrastı WCAG AA; form hataları `aria-describedby` ile bağlı; modal odak tuzağı ve `Esc`.
- **Mobil:** 360 px genişlikte yatay kaydırma yok; kart akışı ve listeler tek sütuna iner.
- **Yol adları Türkçe:** `/giris`, `/kayit`, `/katil`, `/panel`, `/havuz`, `/oneriler`, `/sorular`, `/sinavlar`, `/sinavlar/:id`, `/sinavlar/:id/yazdir`, `/ogrenciler`, `/ogrenciler/:id`, `/ayarlar`.
- **Durum yönetimi:** Sunucu durumu yalnız TanStack Query (`queryKey` sabitleri `src/api/keys.ts`); global istemci durumu yalnız oturum bağlamı. Redux/zustand yok.
- **Test:** `npm run typecheck` (tsc), `npm run lint` (eslint), `npm test` (vitest, `--run`), `npm run build`. Her task bunlar yeşilken biter.
- **Commit:** Türkçe conventional mesaj; **Co-Authored-By ya da başka iz satırı yok** (bkz. depo kökündeki `CLAUDE.md`).
- **Bağımlılık disiplini:** Yukarıdaki yığın dışında paket eklenmez (ikon için `lucide-react` serbest). UI kit (MUI, shadcn CLI, antd) kullanılmaz — bileşenler `src/ui/` altında elle yazılır.

---

## Dosya Yapısı

```
web/
  package.json, vite.config.ts, tsconfig.json, eslint.config.js, index.html
  src/
    main.tsx, App.tsx, index.css
    api/
      client.ts        fetchJson, ApiError, uç nokta fonksiyonları
      types.ts         sunucu şemalarının TypeScript karşılıkları
      keys.ts          TanStack Query anahtarları
    auth/
      AuthProvider.tsx useAuth(), oturum yükleme/çıkış, 401 yönlendirmesi
      RequireAuth.tsx  korumalı yol sarmalayıcısı
    ui/                Button, Card, Field, Input, Textarea, Select, Slider,
                       Modal, Toast(+Provider), Badge, Spinner, EmptyState,
                       ConfirmDialog, Tabs, Table
    math/
      Math.tsx         $...$ / $$...$$ parçalayıp KaTeX ile çizer
      splitMath.ts     saf yardımcı (test edilir)
    layout/
      AppShell.tsx     yan menü + üst bar + içerik
      PublicShell.tsx  giriş/kayıt sayfaları için sade kabuk
    pages/
      LoginPage.tsx, RegisterPage.tsx, JoinPage.tsx
      DashboardPage.tsx
      PoolPage.tsx, PoolSourceEditor.tsx, PoolUpload.tsx
      CardsPage.tsx, CardView.tsx, ScorePad.tsx
      QuestionsPage.tsx
      ExamsPage.tsx, ExamBuilder.tsx, ExamDetailPage.tsx, ExamPrintPage.tsx
      StudentsPage.tsx, StudentDetailPage.tsx
      SettingsPage.tsx
    print.css
  tests/ (vitest; *.test.ts / *.test.tsx dosyaları kaynakla aynı klasörde de olabilir)
  e2e/ (Playwright, Task 9)
```

---

## Tasarım dili (tüm task'ları bağlar)

- **Renk (Tailwind teması, `index.css` içinde `@theme`):** arka plan `#f8fafc`, yüzey `#ffffff`, kenarlık `#e2e8f0`, metin `#0f172a`, ikincil metin `#475569`, birincil `#1d4ed8` (hover `#1e40af`), olumlu `#15803d`, uyarı `#b45309`, olumsuz `#b91c1c`. Koyu tema **yok** (v1 kapsamı dışı).
- **Tipografi:** sistem yazı tipi yığını; başlık 24/20/16 px yarı kalın, gövde 15 px, ikincil 13 px.
- **Yerleşim:** içerik en fazla 1100 px genişlikte ortalanır; kartlar 12 px yuvarlak köşe, `border` + `shadow-sm`; boşluk ölçeği 4/8/12/16/24/32.
- **Ton:** kısa, doğrudan, "siz" hitabı. Hata metinleri suçlayıcı değil, çözüm önerir ("Reçete hesaplanamadı — sayıları ve parantezleri kontrol edin.").
- **Boş durumlar:** her liste için tek cümlelik açıklama + birincil eylem düğmesi.
- **Yüklenme:** liste iskeleti (skeleton) ya da `Spinner`; düğmeler işlem sırasında `disabled` + "…" metni.

Görev sırası: 1 iskele+API+oturum · 2 UI kiti+matematik · 3 havuz · 4 kart akışı · 5 soru bankası+sınav oluşturucu · 6 yazdırma görünümü · 7 öğrenciler · 8 panel+ayarlar · 9 derleme bütünleşmesi+e2e.

---
### Task 1: Proje iskeleti, API istemcisi, oturum bağlamı ve yönlendirme

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/eslint.config.js`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/index.css`, `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/keys.ts`, `web/src/auth/AuthProvider.tsx`, `web/src/auth/RequireAuth.tsx`, `web/src/layout/PublicShell.tsx`, `web/src/layout/AppShell.tsx`, `web/src/pages/LoginPage.tsx`, `web/src/pages/RegisterPage.tsx`, `web/src/pages/JoinPage.tsx`, `web/vitest.setup.ts`
- Create (yer tutucu sayfalar, sonraki task'larda doldurulur): `web/src/pages/DashboardPage.tsx`, `PoolPage.tsx`, `CardsPage.tsx`, `QuestionsPage.tsx`, `ExamsPage.tsx`, `StudentsPage.tsx`, `SettingsPage.tsx` — her biri başlık + "Bu ekran hazırlanıyor." metni
- Test: `web/src/api/client.test.ts`, `web/src/auth/AuthProvider.test.tsx`
- Modify: depo kökü `.gitignore` (`web/node_modules/`, `web/dist/`)

**Interfaces:**
- `api/client.ts`:
  - `class ApiError extends Error { status: number; detail: string }`
  - `setUnauthorizedHandler(fn: () => void): void` — 401'de çağrılır (yalnız bir kez kayıtlı)
  - `api.auth`: `me()`, `login(body)`, `register(body)`, `join(body)`, `logout()`
  - `api.workspace`: `get()`, `rename(name)`, `members()`, `createInvite(role?)`, `removeMember(id)`, `backupUrl()`, `remove(confirmName)`
  - `api.pool`: `summary()`, `sources(status?)`, `source(id)`, `createSource(body)`, `updateSource(id, body)`, `deleteSource(id)`, `upload(file)`, `previewRecipe(body)`, `objectives()`, `suggestRecipe(id)`
  - `api.cards`: `generate(body)`, `pending(studentId?)`, `get(id)`, `review(id, body)`, `undoReview(id)`, `dress(id)`
  - `api.questions`: `list(params)`, `setArchived(id, archived)`
  - `api.exams`: `create(body)`, `list(studentId?)`, `get(id)`, `remove(id)`, `docxUrl(id, booklet, answers)`, `texUrl(id, booklet, answers)`
  - `api.students`: `list()`, `create(body)`, `get(id)`, `update(id, body)`, `archive(id)`, `generate(id, count)`, `history(id)`, `worksheet(id, body)`
  - `api.stats.get()`, `api.system.config()`
  - Tümü `fetchJson` üzerinden; hata gövdesi `{detail}` → `ApiError.detail`, gövde okunamazsa `"Beklenmeyen bir hata oluştu."`; 204 → `undefined`
- `auth/AuthProvider.tsx`: `useAuth(): { session: Session | null; loading: boolean; login(...); register(...); join(...); logout(); }` — `Session = { user: {id,email,name}; workspace: {id,name}; role: "owner" | "teacher" }`
- `auth/RequireAuth.tsx`: oturum yoksa `/giris`e `replace` yönlendirir, yüklenirken tam sayfa `Spinner`

**Kurallar.**
- `package.json` betikleri: `dev` (vite), `build` (`tsc -b && vite build`), `preview`, `typecheck` (`tsc --noEmit`), `lint` (`eslint .`), `test` (`vitest run`), `test:watch`.
- `vite.config.ts`: `@tailwindcss/vite` eklentisi, `server.proxy["/api"] = "http://127.0.0.1:8000"`, `build.outDir = "dist"`, `resolve.alias["@"] = "/src"`, vitest ayarı (`environment: "jsdom"`, `setupFiles: ["./vitest.setup.ts"]`, `globals: true`).
- `vitest.setup.ts`: `@testing-library/jest-dom` import + her testten sonra `cleanup()`.
- `index.css`: Tailwind import + `@theme` içinde tasarım dili renkleri (`--color-brand`, `--color-surface`, ...) + KaTeX CSS importu + odak halkası varsayılanı.
- Yönlendirme (`App.tsx`): `QueryClientProvider` → `AuthProvider` → `BrowserRouter`; `PublicShell` altında `/giris`, `/kayit`, `/katil`; `RequireAuth` + `AppShell` altında diğerleri; `*` → `/panel`e yönlendirme. `QueryClient` varsayılanları: `retry: 1`, `staleTime: 30_000`, `refetchOnWindowFocus: false`.
- `AppShell`: solda menü (Panel, Havuz, Öneriler, Soru Bankası, Sınavlar, Öğrenciler, Ayarlar), üstte çalışma alanı adı + kullanıcı adı + "Çıkış". Mobilde menü üstte yatay kaydırılabilir şerit olur.
- Giriş/kayıt formları: alan doğrulaması istemcide (boş alan, parola ≥ 8), sunucu hatası `ApiError.detail` olarak formun üstünde gösterilir. Kayıt formunda "Örnek soru havuzuyla başla" onay kutusu (varsayılan işaretli) → `load_demo`.

- [ ] **Adım 1: Projeyi kur**

```bash
cd web 2>/dev/null || mkdir -p web && cd web
npm create vite@latest . -- --template react-ts
npm install react-router-dom @tanstack/react-query katex lucide-react
npm install -D tailwindcss @tailwindcss/vite @types/katex vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event eslint @eslint/js typescript-eslint eslint-plugin-react-hooks
```
Kurulum çıktısında zafiyet uyarısı varsa rapora yaz, `npm audit fix --force` **çalıştırma**.

- [ ] **Adım 2: Başarısız testleri yaz**

`web/src/api/client.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, setUnauthorizedHandler } from "./client";

function yanit(body: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("api istemcisi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setUnauthorizedHandler(() => {});
  });

  it("GET isteğini gönderir ve gövdeyi çözer", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(yanit({ total: 3 }));
    await expect(api.pool.summary()).resolves.toEqual({ total: 3 });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/pool/summary");
    expect(init?.credentials).toBe("same-origin");
  });

  it("gövdeli isteklerde JSON başlığı ve metot kullanır", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(yanit({ id: "s_1" }));
    await api.pool.createSource({ text: "Soru", recipe: "2*x" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/pool/sources");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ text: "Soru", recipe: "2*x" });
  });

  it("hata gövdesindeki detail alanını taşır", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(yanit({ detail: "Soru bulunamadı." }, 404));
    await expect(api.cards.get("q_1")).rejects.toMatchObject({ status: 404, detail: "Soru bulunamadı." });
    await expect(api.cards.get("q_1")).rejects.toBeInstanceOf(ApiError);
  });

  it("okunamayan hata gövdesinde genel mesaj verir", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>", { status: 500 }));
    await expect(api.stats.get()).rejects.toMatchObject({ detail: "Beklenmeyen bir hata oluştu." });
  });

  it("401'de oturum düşürme geri çağrısını tetikler", async () => {
    const dusur = vi.fn();
    setUnauthorizedHandler(dusur);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(yanit({ detail: "Oturum açmanız gerekiyor." }, 401));
    await expect(api.auth.me()).rejects.toBeInstanceOf(ApiError);
    expect(dusur).toHaveBeenCalledOnce();
  });

  it("204 yanıtında undefined döner", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.pool.deleteSource("s_1")).resolves.toBeUndefined();
  });

  it("dosya yüklemede FormData kullanır ve JSON başlığı koymaz", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(yanit({ added: 1 }));
    await api.pool.upload(new File(["x"], "havuz.md", { type: "text/markdown" }));
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init?.body).toBeInstanceOf(FormData);
    expect(new Headers(init?.headers).get("content-type")).toBeNull();
  });
});
```

`web/src/auth/AuthProvider.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthProvider";

const oturum = {
  user: { id: "u_1", email: "h@ornek.com", name: "Ayşe Hoca" },
  workspace: { id: "w_1", name: "Işık Dershanesi", created_at: "" },
  role: "owner",
};

function Deneme() {
  const { session, loading, logout } = useAuth();
  if (loading) return <p>yükleniyor</p>;
  return (
    <div>
      <span>{session ? session.workspace.name : "oturum yok"}</span>
      <button onClick={() => void logout()}>Çıkış</button>
    </div>
  );
}

function ciz() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Deneme />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.restoreAllMocks());

it("açılışta oturumu yükler", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(oturum), { headers: { "content-type": "application/json" } }),
  );
  ciz();
  expect(screen.getByText("yükleniyor")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByText("Işık Dershanesi")).toBeInTheDocument());
});

it("401'de oturumsuz duruma düşer", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ detail: "Oturum açmanız gerekiyor." }), {
      status: 401,
      headers: { "content-type": "application/json" },
    }),
  );
  ciz();
  await waitFor(() => expect(screen.getByText("oturum yok")).toBeInTheDocument());
});

it("çıkışta oturumu temizler", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(oturum), { headers: { "content-type": "application/json" } }),
  );
  fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
  ciz();
  await waitFor(() => expect(screen.getByText("Işık Dershanesi")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Çıkış" }));
  await waitFor(() => expect(screen.getByText("oturum yok")).toBeInTheDocument());
});
```

- [ ] **Adım 3: Testin başarısız olduğunu doğrula** — `cd web && npm test` → FAIL (modüller yok).

- [ ] **Adım 4: `api/types.ts` ve `api/client.ts`'i yaz.** `fetchJson` iskeleti:

```ts
export class ApiError extends Error {
  constructor(readonly status: number, readonly detail: string) {
    super(detail);
    this.name = "ApiError";
  }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

async function fetchJson<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const headers = new Headers(rest.headers);
  let body = rest.body;
  if (json !== undefined) {
    headers.set("content-type", "application/json");
    body = JSON.stringify(json);
  }
  const response = await fetch(path, { ...rest, body, headers, credentials: "same-origin" });
  if (response.status === 401) onUnauthorized();
  if (!response.ok) {
    let detail = "Beklenmeyen bir hata oluştu.";
    try {
      const gövde = (await response.json()) as { detail?: unknown };
      if (typeof gövde.detail === "string") detail = gövde.detail;
    } catch {
      /* gövde JSON değil: genel mesaj kalır */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
```

(Uygulayıcı: yukarıdaki iskelette Türkçe yerel ad `gövde` kullanılmıştır — `web/` altında tanımlayıcılar İngilizce olmalı, `body`/`payload` gibi bir ad kullan.)

- [ ] **Adım 5: `AuthProvider`, `RequireAuth`, kabuklar, giriş/kayıt/katıl sayfaları ve yer tutucu sayfaları yaz; `App.tsx` yönlendirmesini kur.** `AuthProvider` içinde `useEffect` ile `setUnauthorizedHandler(() => queryClient.setQueryData(keys.session, null))`.

- [ ] **Adım 6: Testleri ve derlemeyi çalıştır** — `npm test && npm run typecheck && npm run lint && npm run build`.

- [ ] **Adım 7: Elle doğrula** — bir terminalde `QC_DATA_DIR=/tmp/qc-web .venv/bin/questioncrator serve`, diğerinde `cd web && npm run dev`; tarayıcıda kayıt ol → `/panel`e düşüyor, sayfa yenilenince oturum korunuyor, "Çıkış" `/giris`e atıyor. Sonucu rapora yaz.

- [ ] **Adım 8: Commit**

```bash
git add .gitignore web
git commit -m "feat(web): Vite/React iskeleti, tipli API istemcisi, oturum bağlamı ve yönlendirme"
```

---

### Task 2: UI kiti, matematik çizimi ve bildirimler

**Files:**
- Create: `web/src/ui/{Button,Card,Field,Input,Textarea,Select,Slider,Modal,ConfirmDialog,Toast,Badge,Spinner,EmptyState,Tabs,Table}.tsx`, `web/src/ui/index.ts`, `web/src/math/splitMath.ts`, `web/src/math/Math.tsx`
- Test: `web/src/math/splitMath.test.ts`, `web/src/math/Math.test.tsx`, `web/src/ui/Modal.test.tsx`, `web/src/ui/Slider.test.tsx`, `web/src/ui/Toast.test.tsx`

**Interfaces:**
- `splitMath(text: string): Array<{ kind: "text" | "inline" | "block"; value: string }>` — `$$...$$` blok, `$...$` satır içi; kaçışlı `\$` düz metindir; kapanmayan `$` düz metin sayılır (metin asla kaybolmaz).
- `<Math value={string} />` — parçaları çizer; matematik parçaları `katex.renderToString(value, { throwOnError: false, displayMode })` ile; hatalı LaTeX kırmızı `<code>` olarak ham gösterilir (uygulama çökmez).
- `<Slider label value onChange min={1} max={10} />` — `input[type=range]` + görünür değer; `value === null` iken "—" gösterir ve `aria-valuetext="puanlanmadı"`.
- `<Modal open title onClose>` — `role="dialog"`, `aria-modal`, `Esc` kapatır, odak modala taşınır, kapanınca tetikleyen öğeye döner, arka plan kaydırması kilitlenir.
- `<ConfirmDialog open title description confirmLabel onConfirm onCancel danger?>`
- `ToastProvider` + `useToast(): { success(msg): void; error(msg): void }` — en fazla 3 bildirim, 5 sn sonra kendiliğinden kapanır, `role="status"`.
- `<EmptyState title description action?>`, `<Badge tone="neutral"|"success"|"warning"|"danger">`, `<Table>` (başlık + satır alt bileşenleri), `<Tabs>` (klavye ok tuşlarıyla).

- [ ] **Adım 1: Başarısız testleri yaz**

`web/src/math/splitMath.test.ts`:
```ts
import { expect, it } from "vitest";
import { splitMath } from "./splitMath";

it("satır içi ve blok matematiği ayırır", () => {
  expect(splitMath("a $x^2$ b $$\\frac{1}{2}$$ c")).toEqual([
    { kind: "text", value: "a " },
    { kind: "inline", value: "x^2" },
    { kind: "text", value: " b " },
    { kind: "block", value: "\\frac{1}{2}" },
    { kind: "text", value: " c" },
  ]);
});

it("kaçışlı dolar ve kapanmayan dolar düz metindir", () => {
  expect(splitMath("5 \\$ tutar")).toEqual([{ kind: "text", value: "5 \\$ tutar" }]);
  expect(splitMath("yarım $x kaldı")).toEqual([{ kind: "text", value: "yarım $x kaldı" }]);
});

it("boş metin boş dizi verir", () => {
  expect(splitMath("")).toEqual([]);
});
```

`web/src/math/Math.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Math } from "./Math";

it("matematiği KaTeX ile çizer, metni olduğu gibi bırakır", () => {
  const { container } = render(<Math value={"Türev: $x^2$"} />);
  expect(screen.getByText(/Türev:/)).toBeInTheDocument();
  expect(container.querySelector(".katex")).not.toBeNull();
});

it("bozuk LaTeX'te çökmez", () => {
  const { container } = render(<Math value={"$\\frac{$"} />);
  expect(container.textContent).toContain("\\frac{");
});
```

`web/src/ui/Modal.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Modal } from "./Modal";

it("Esc ile kapanır ve başlığı erişilebilir", async () => {
  const kapat = vi.fn();
  render(
    <Modal open title="Soruyu sil" onClose={kapat}>
      <button>İçerik</button>
    </Modal>,
  );
  const pencere = screen.getByRole("dialog");
  expect(pencere).toHaveAccessibleName("Soruyu sil");
  await userEvent.keyboard("{Escape}");
  expect(kapat).toHaveBeenCalledOnce();
});

it("kapalıyken hiçbir şey çizmez", () => {
  render(<Modal open={false} title="X" onClose={() => {}} />);
  expect(screen.queryByRole("dialog")).toBeNull();
});
```

`web/src/ui/Slider.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Slider } from "./Slider";

it("puanlanmamış durumu bildirir ve değişimi iletir", async () => {
  const degis = vi.fn();
  render(<Slider label="Zorluk" value={null} onChange={degis} />);
  const kaydirici = screen.getByRole("slider", { name: "Zorluk" });
  expect(kaydirici).toHaveAttribute("aria-valuetext", "puanlanmadı");
  await userEvent.click(kaydirici);
  kaydirici.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(degis).toHaveBeenCalled();
});
```

`web/src/ui/Toast.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { ToastProvider, useToast } from "./Toast";

function Deneme() {
  const toast = useToast();
  return <button onClick={() => toast.success("Kaydedildi")}>Bildir</button>;
}

it("bildirim gösterir", async () => {
  render(
    <ToastProvider>
      <Deneme />
    </ToastProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Bildir" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Kaydedildi");
});
```

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `npm test` → FAIL.

- [ ] **Adım 3: `splitMath`, `Math` ve UI bileşenlerini yaz.** `App.tsx`'i `ToastProvider` ile sar. Bileşenler tasarım diline (renkler, boşluk, yuvarlaklık) uyar; her biri `className` birleştirmeye izin verir (`clsx` yerine küçük bir `cn()` yardımcı fonksiyonu `src/ui/cn.ts`).

- [ ] **Adım 4: Testleri ve derlemeyi çalıştır** — `npm test && npm run typecheck && npm run lint && npm run build`.

- [ ] **Adım 5: Commit**

```bash
git add web/src
git commit -m "feat(web): UI kiti, KaTeX matematik çizimi ve bildirim altyapısı"
```

---
### Task 3: Havuz ekranı (yükleme, liste, elle kontrol düzenleyicisi)

**Files:**
- Create: `web/src/pages/PoolPage.tsx`, `web/src/pages/PoolUpload.tsx`, `web/src/pages/PoolSourceEditor.tsx`, `web/src/pages/pool.hooks.ts`
- Test: `web/src/pages/PoolPage.test.tsx`, `web/src/pages/PoolSourceEditor.test.tsx`

**Ekran sözleşmesi.**
- Üstte dört sayaç kartı: **Toplam soru**, **Üretime hazır**, **Elle kontrol gerekli**, **Kazanım sayısı**. Kazanım dağılımı: en çok 8 kazanım için ad + adet çubuğu (fazlası "+N kazanım").
- **Yükleme alanı:** sürükle-bırak + "Dosya seç" düğmesi. Kabul: `.md .txt .docx .pdf .png .jpg .jpeg`. Yükleme sırasında `Spinner` ve alan pasif. Sonuç bildirimi: "X soru eklendi, Y şablon çıkarıldı." Sorunlu kaynaklar varsa altında liste: "Z soru elle kontrol gerektiriyor" + "Elle kontrol listesine git" bağlantısı. Hata (`ApiError.detail`) kırmızı bildirim.
- **Sekmeler:** "Elle kontrol (N)" (varsayılan sekme N>0 ise), "Üretime hazır", "Tümü". Her satır: soru metninin ilk satırı `<Math>` ile, kazanım rozeti, durum rozeti (`trial`/`active`/`disabled`/"şablon yok"), `review_note` varsa uyarı metni, "Düzenle" ve "Sil" (onay ister).
- **"Elle soru ekle"** düğmesi boş metinle düzenleyiciyi açar.
- **Düzenleyici** (`PoolSourceEditor`, modal): alanlar Soru metni (textarea, `$...$` ipucu), Cevap reçetesi (tek satır, monospace), Çözüm (isteğe bağlı), Kazanım (serbest metin + mevcut kazanımlardan `datalist`).
  - **Önizle** düğmesi → `api.pool.previewRecipe`: sonuç kutusunda cevabın LaTeX çizimi, "N parametre bulundu", tahmini zorluk ve 3 varyant (metin + cevap). Hata durumunda `error` metni kırmızı.
  - **Reçete öner** düğmesi yalnız `system.config.llm_enabled` ise görünür; dönen reçeteyi alana yazar ve otomatik önizleme yapar.
  - **Kaydet** → yeni kayıtta `createSource`, düzenlemede `updateSource`; başarı bildirimi + listeler `invalidateQueries`.
  - Kaydetmeden kapatmada değişiklik varsa `ConfirmDialog`.
- Yükleme/silme/kaydetme sonrası ilgili sorgular (`keys.pool.*`, `keys.objectives`) geçersizleştirilir.

- [ ] **Adım 1: Başarısız testleri yaz** (`vi.mock("@/api/client")` ile API taklit edilir; her testte `QueryClientProvider` + `ToastProvider` sarmalayıcısı `web/src/test/renderApp.tsx` yardımcısıyla — bu yardımcıyı da bu task'ta oluştur):

`web/src/pages/PoolPage.test.tsx` en az şu davranışları doğrular:
1. Sayaçlar API özetinden doğru yazılır ("Toplam soru 4", "Elle kontrol gerekli 1").
2. Elle kontrol sekmesi varsayılan açılır ve yalnız `needs_review` kaynakları listeler; her satırda `review_note` görünür.
3. Dosya seçildiğinde `api.pool.upload` çağrılır ve başarı bildirimi metni "4 soru eklendi, 3 şablon çıkarıldı." olur.
4. Yükleme hatasında `ApiError.detail` bildirimi görünür ve sayaçlar değişmez.
5. "Sil" düğmesi onay ister; onaylanınca `api.pool.deleteSource` çağrılır, iptal edilince çağrılmaz.
6. Liste boşken `EmptyState` başlığı "Havuzda henüz soru yok" ve "Dosya yükle" eylemi görünür.

`web/src/pages/PoolSourceEditor.test.tsx`:
1. "Önizle" `api.pool.previewRecipe`'i alanlarla çağırır; dönen varyantlar (3 adet) ve "2 parametre bulundu" ekranda görünür.
2. Önizleme hatasında (`ok:false, error`) hata metni görünür ve **Kaydet düğmesi yine etkindir** (hoca yine de kaydedip sonra düzeltebilir).
3. `llm_enabled=false` iken "Reçete öner" düğmesi yoktur; `true` iken çağrı sonucu reçete alanına yazılır.
4. Yeni kayıtta "Kaydet" `api.pool.createSource`'u `{text, recipe, answer_text, objective}` ile çağırır; boş metinle kaydet denemesi alan hatası gösterir ve çağrı yapılmaz.

- [ ] **Adım 2: Testlerin başarısız olduğunu doğrula** — `npm test` → FAIL.
- [ ] **Adım 3: `pool.hooks.ts` (sorgu/mutasyon kancaları), `PoolUpload`, `PoolSourceEditor`, `PoolPage`'i yaz.**
- [ ] **Adım 4:** `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula** — sunucu + `npm run dev` ile: demo hesapla havuz sayfası doluyor; `tests/data/ornek_havuz.md` yüklenince sayaçlar artıyor; elle kontrol kaydına reçete yazıp önizleme çalışıyor; kaydedince satır "Üretime hazır" sekmesine geçiyor.
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): havuz ekranı — yükleme, liste ve elle kontrol düzenleyicisi"`

---

### Task 4: Kart akışı ekranı

**Files:**
- Create: `web/src/pages/CardsPage.tsx`, `web/src/pages/CardView.tsx`, `web/src/pages/ScorePad.tsx`, `web/src/pages/cards.hooks.ts`, `web/src/pages/useCardShortcuts.ts`
- Test: `web/src/pages/CardsPage.test.tsx`, `web/src/pages/useCardShortcuts.test.ts`

**Ekran sözleşmesi.**
- **Üretim çubuğu:** adet (varsayılan 10, 1-50), kazanım seçimi (çoklu, boş = hepsi), hedef zorluk (isteğe bağlı 1-10 kaydırıcı + "Farketmez" seçeneği), "Yeni öneri üret" düğmesi. Üretim sırasında düğme pasif ve "Üretiliyor…" yazar; üretim bitince bildirim: "N yeni öneri hazır." Üretimden 0 sonuç dönerse: "Yeni soru üretilemedi — havuzdaki sorular tükenmiş olabilir. Havuza yeni soru ekleyin."
- **Kart:** sıradaki bekleyen kart tek başına ortada. İçerik: soru metni (`<Math>`, 18 px), varsa 5 şık `A) … E)` (doğru şık yeşil kenarlıkla ve "doğru cevap" etiketiyle), "Cevap: $…$", rozetler (`Deneme şablonu`, `Benzer soru daha önce verildi`, kazanım adı, tahmini zorluk). Sağ üstte "Kalan: N".
- **Puanlama (`ScorePad`):** iki kaydırıcı — **Zorluk (1-10)** ve **Kurgu (1-10)**; ikisi de puanlanmadan **Onayla** ve **Reddet** düğmeleri pasiftir ve altında "Puanlamadan onaylayamazsınız." açıklaması görünür (tasarım §1 kuralı).
- **Klavye:** `A` onayla, `R` reddet, `Z` son değerlendirmeyi geri al, `←/→` zorluk −/+, `↑/↓` kurgu +/−, `?` kısayol yardımını açar. Kısayollar yalnız odak bir form alanında değilken çalışır. Kısayol listesi kartın altında küçük puntoyla da yazılıdır.
- **Geri alma:** son değerlendirilen kart için "Son kararı geri al" düğmesi (`Z`); geri alınan kart sıranın başına döner, bildirim "Karar geri alındı."
- **Şablon geçişi:** `transitions` boş değilse bildirim: "Bu sorunun şablonu etkinleştirildi." / "…devre dışı bırakıldı."
- **Giydirme (LLM açıksa):** kartta "Metni güzelleştir" düğmesi; başarıda kart metni yenilenir, hata bildirimi `ApiError.detail`.
- Bekleyen kart yoksa `EmptyState`: "Bekleyen öneri yok." + "Yeni öneri üret" eylemi.

- [ ] **Adım 1: Başarısız testleri yaz**

`useCardShortcuts.test.ts` (saf kanca testi, `renderHook`): `A`/`R`/`Z` geri çağrıları tetikler; `←/→` zorluğu 1-10 aralığında değiştirir; `↑/↓` kurguyu değiştirir; `input`/`textarea` odaktayken hiçbir kısayol çalışmaz; puanlar eksikken `A`/`R` **çağırmaz**.

`CardsPage.test.tsx` en az:
1. Bekleyen kart metni, şıkları ve doğru şık işareti çizilir; `answer_key`/`bindings` ekranda görünmez.
2. Puanlar verilmeden "Onayla" pasiftir; iki kaydırıcı da ayarlanınca etkinleşir ve tıklanınca `api.cards.review` `{approved:true, difficulty, quality}` ile çağrılır.
3. Değerlendirme sonrası sıradaki kart görünür ve "Kalan" sayacı azalır.
4. `transitions` dolu dönerse şablon bildirimi görünür.
5. "Yeni öneri üret" `api.cards.generate` çağırır; boş liste dönerse tükenme mesajı görünür.
6. Geri al düğmesi `api.cards.undoReview` çağırır ve kart listeye döner.
7. `llm_enabled=false` iken "Metni güzelleştir" düğmesi yoktur.

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `npm test` → FAIL.
- [ ] **Adım 3: Kancayı, `ScorePad`, `CardView` ve `CardsPage`'i yaz.**
- [ ] **Adım 4:** `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula** — demo hesapla 10 kart üret, yalnız klavyeyle 5 kart puanla; kart başına süreyi ölç ve rapora yaz (hedef: medyan ≤ 30 sn, tasarım §6).
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): kart akışı — çift puanlama, klavye kısayolları, geri alma"`

---

### Task 5: Soru bankası ve sınav oluşturucu

**Files:**
- Create: `web/src/pages/QuestionsPage.tsx`, `web/src/pages/ExamsPage.tsx`, `web/src/pages/ExamBuilder.tsx`, `web/src/pages/ExamDetailPage.tsx`, `web/src/pages/exams.hooks.ts`
- Test: `web/src/pages/QuestionsPage.test.tsx`, `web/src/pages/ExamBuilder.test.tsx`, `web/src/pages/ExamDetailPage.test.tsx`

**Soru bankası sözleşmesi.**
- Filtreler: kazanım (seçim), zorluk aralığı (iki kaydırıcı ya da iki sayı alanı), arama kutusu (metin içinde, istemci tarafında).
- Liste: seçim kutusu, soru metni (`<Math>`, iki satır kırpma), kazanım rozeti, hocanın verdiği zorluk/kurgu puanları, "Arşivle" düğmesi.
- Seçim varken üstte çubuk: "N soru seçildi" + "Sınav oluştur" (seçimi `ExamBuilder`'a taşır) + "Seçimi temizle".
- Boş durumda: "Henüz onaylı soru yok. Önerileri puanlayarak başlayın." + "Önerilere git".

**Sınav oluşturucu sözleşmesi (`ExamBuilder`, modal).**
- Alanlar: Başlık, Tür (Sınav/Çalışma kağıdı — çalışma kağıdı yalnız öğrenci sayfasından), Biçim (Test/Klasik), Kitapçık (Tek A / A-B).
- Soru seçimi iki kip: **Elle** (bankadan taşınan seçim, listelenir, çıkarılabilir) veya **Otomatik** (soru sayısı, kazanım ağırlıkları — kazanım ekle/ağırlık ver, zorluk aralığı).
- "Oluştur" → `api.exams.create`; hata `ApiError.detail` (ör. "Yeterli onaylı soru yok: 20 istendi, 12 uygun soru var.") formun üstünde görünür.
- Başarıda sınav detay sayfasına yönlendirir.

**Sınav listesi ve detay sözleşmesi.**
- Liste: başlık, tür rozeti, soru sayısı, kitapçıklar, tarih; "Aç" ve "Sil" (onaylı).
- Detay: kitapçık sekmeleri (A/B); her kitapçıkta numaralı sorular (`<Math>`, şıklar) ve altta **Cevap anahtarı** tablosu (`1-C` biçimi, klasikte LaTeX cevap). Üstte eylem çubuğu: "Yazdır / PDF" (`/sinavlar/:id/yazdir?kitapcik=A` yeni sekmede), "Word indir" (`api.exams.docxUrl`), "Cevap anahtarı (Word)", "LaTeX indir". `missing_question_ids` doluysa uyarı: "N soru silinmiş; kağıtta yer almayacak."

- [ ] **Adım 1: Başarısız testleri yaz** — en az:
1. `QuestionsPage`: filtreler API'ye parametre olarak gider (`objective`, `difficulty_min`); arama istemcide süzer; "Arşivle" `api.questions.setArchived(id, true)` çağırır; seçim çubuğu seçilen sayıyı gösterir.
2. `ExamBuilder`: elle kipte seçili soru kimlikleriyle `api.exams.create` çağrılır (`question_ids`, `booklets: ["A","B"]`, `format`); otomatik kipte `auto` gövdesi doğru kurulur (`count`, `objective_weights`, `difficulty_min/max`); sunucu hatası formda görünür; başlık boşken çağrı yapılmaz.
3. `ExamDetailPage`: iki kitapçık sekmesi çizilir, B sekmesinde sıra A'dan farklı görünür (sahte veriyle), cevap anahtarı tablosu doğru harfleri gösterir, indirme bağlantılarının `href`'i doğru uç noktaya işaret eder, `missing_question_ids` uyarısı görünür.

- [ ] **Adım 2: Başarısız olduğunu doğrula** — `npm test` → FAIL.
- [ ] **Adım 3: Sayfaları ve kancaları yaz.**
- [ ] **Adım 4:** `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula** — demo veriyle 8 soru onayla, otomatik 5 soruluk A/B kitapçıklı test sınavı oluştur, Word dosyasını indir ve LibreOffice/Word'de aç (denklemler gerçek denklem nesnesi mi bak), sonucu rapora yaz.
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): soru bankası, sınav oluşturucu ve sınav detay ekranı"`

---
### Task 6: Yazdırma görünümü (A4 sınav kağıdı ve cevap anahtarı)

Spec K8: PDF sunucuda üretilmez; hoca tarayıcıdan "PDF olarak kaydet" der. Bu yüzden yazdırma düzeni ürünün asıl çıktı yüzeyidir ve baskı kalitesi satış argümanıdır.

**Files:**
- Create: `web/src/pages/ExamPrintPage.tsx`, `web/src/print.css`
- Test: `web/src/pages/ExamPrintPage.test.tsx`

**Sözleşme.**
- Yol: `/sinavlar/:id/yazdir?kitapcik=A&cevap=0`. Kabuk (`AppShell`) **yoktur**; sayfa yalnız kağıdı çizer. Üstte yalnız ekranda görünen (baskıda gizli) bir çubuk: kitapçık seçimi, "Cevap anahtarını göster" anahtarı, "Yazdır" düğmesi (`window.print()`), "Geri".
- **Kağıt düzeni:** `@page { size: A4; margin: 14mm 12mm; }`. Başlık bloğu: sınav adı (ortalı, 16 pt), altında kitapçık harfi; ikinci satır: `Ad Soyad: ______  Sınıf: ____  No: ____  Tarih: ____` (çizgili alanlar). Başlık bloğu yalnız ilk sayfada.
- **Sorular:** test biçiminde **iki sütun** (`column-count: 2; column-gap: 10mm`), klasik biçimde tek sütun ve her sorunun altında 3,5 cm boş çalışma alanı. Soru numarası kalın; şıklar `A) … E)` ve mümkünse iki şık yan yana. Soru bloğu sütun/sayfa arasında bölünmez (`break-inside: avoid`).
- **Cevap anahtarı:** `cevap=1` iken sorulardan sonra `break-before: page` ile ayrı sayfa; test biçiminde 10 sütunlu kompakt tablo (`1-C  2-A …`), klasik biçimde numara + LaTeX cevap listesi.
- **Altbilgi:** her sayfanın altında ekranda görünmeyen küçük metin: sınav adı + kitapçık + "Questioncrator" (baskıda görünür, `position: fixed; bottom: 0` + `@media print`).
- Yazı tipi baskıda 11 pt; KaTeX ölçeği baskıda 1.0 (ekranda 1.05).
- `?kitapcik=` geçersizse ilk kitapçığa düşer; sınav yoksa "Sınav bulunamadı." + sınavlar listesine dön bağlantısı.

- [ ] **Adım 1: Başarısız testleri yaz** — `ExamPrintPage.test.tsx`: (1) `?kitapcik=B` ile B kitapçığının sırası çizilir; (2) `cevap=1` cevap anahtarı bölümünü ekler, `cevap=0` eklemez; (3) ekran çubuğundaki "Yazdır" düğmesi `window.print`'i çağırır (`vi.spyOn(window, "print")`); (4) test biçiminde her soru için 5 şık etiketi (`A)`–`E)`) çizilir; (5) geçersiz kitapçık parametresi ilk kitapçığa düşer; (6) sınav 404 ise hata metni görünür.
- [ ] **Adım 2: Başarısız olduğunu doğrula** — `npm test` → FAIL.
- [ ] **Adım 3: `print.css` ve `ExamPrintPage`'i yaz;** yazdırma yolunu `App.tsx`'te `AppShell` dışına al.
- [ ] **Adım 4:** `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula (zorunlu görsel kontrol)** — Chrome'da `/sinavlar/:id/yazdir` → Yazdır önizlemesinde: A4'e sığıyor, iki sütun düzgün, soru ortadan bölünmüyor, matematik net, cevap anahtarı ayrı sayfada. Ekran çubuğu baskıda **görünmüyor**. Önizleme ekran görüntüsünü rapora ekle (dosya yolu ver).
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): A4 yazdırma görünümü ve cevap anahtarı sayfası"`

---

### Task 7: Öğrenci ekranları

**Files:**
- Create: `web/src/pages/StudentsPage.tsx`, `web/src/pages/StudentDetailPage.tsx`, `web/src/pages/students.hooks.ts`
- Test: `web/src/pages/StudentsPage.test.tsx`, `web/src/pages/StudentDetailPage.test.tsx`

**Sözleşme.**
- **Liste:** kart ızgarası; her kartta rumuz, seviye rozeti, "N soru verildi", "M öneri bekliyor", "Aç". Üstte "Öğrenci ekle" (modal: rumuz, zayıf kazanımlar çoklu seçim, seviye 1-10 ya da "Belirtilmedi"). Boş durum: "Henüz öğrenci eklemediniz." + gizlilik notu: "Yalnız rumuz ve zayıf konular saklanır; not ya da kişisel veri tutulmaz."
- **Detay sayfası** (`/ogrenciler/:id`):
  - Başlık: rumuz + "Düzenle" + "Arşivle" (onaylı).
  - **Zayıf kazanımlar** bölümü: havuz kazanımlarından çoklu seçim, kaydet.
  - **"Bu öğrenci için soru üret"**: adet (varsayılan 5) + üret; üretilen kartlar aynı kart akışı bileşenleriyle (`CardView` + `ScorePad`, `student_id` bağlamında) puanlanır; kısayollar aynıdır.
  - **Geçmiş:** "Verilen sorular" listesi (tarihle), "Çalışma kağıtları" listesi (aç/indir/yazdır bağlantılarıyla).
  - **"Çalışma kağıdı oluştur"**: bu öğrencinin onaylı sorularından seçim + başlık + biçim → `api.students.worksheet`; başarıda sınav detayına yönlendirir.
  - Öğrenciye özel üretimde kart "Benzer soru daha önce verildi" rozetini gösterir (sunucudan gelen `similar_given`).
- Arşivlenen öğrenci listeden kalkar; detay sayfası açılırsa "Bu öğrenci arşivlendi." uyarısı ve üretim düğmeleri pasif.

- [ ] **Adım 1: Başarısız testleri yaz** — en az: (1) liste sayaçları API'den doğru yazılır, boş durumda gizlilik notu görünür; (2) "Öğrenci ekle" `api.students.create` çağırır, rumuz boşken çağırmaz; (3) detayda "soru üret" `api.students.generate(id, count)` çağırır ve dönen kartlar puanlanabilir (bir kartı onaylamak `api.cards.review` çağırır); (4) zayıf kazanım kaydı `api.students.update` çağırır; (5) çalışma kağıdı oluşturma `api.students.worksheet` çağırır ve yönlendirir; (6) arşivli öğrencide üretim düğmesi pasiftir.
- [ ] **Adım 2–4:** başarısızlığı doğrula → yaz → `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Elle doğrula** — demo hesapta öğrenci ekle, zayıf kazanım seç, 5 soru üret, puanla, çalışma kağıdı oluştur ve yazdırma görünümünü aç.
- [ ] **Adım 6: Commit** — `git commit -m "feat(web): öğrenci listesi, öğrenci sayfası ve çalışma kağıdı akışı"`

---

### Task 8: Panel ve ayarlar

**Files:**
- Create: `web/src/pages/DashboardPage.tsx`, `web/src/pages/SettingsPage.tsx`
- Test: `web/src/pages/DashboardPage.test.tsx`, `web/src/pages/SettingsPage.test.tsx`

**Panel sözleşmesi** (`/panel`, giriş sonrası varsayılan sayfa):
- **Sonraki adım kartı** (en üstte, birincil): `next_step` değerine göre metin ve düğme —
  `upload_pool` → "Havuzunuz boş. İlk soru dosyanızı yükleyin." / "Havuza git";
  `fix_pool` → "N soru elle kontrol bekliyor." / "Elle kontrole git";
  `generate` → "Yeni öneriler üretmeye hazırsınız." / "Öneri üret";
  `review` → "N öneri puanlanmayı bekliyor." / "Puanlamaya devam et";
  `build_exam` → "Onaylı sorularınızdan sınav oluşturabilirsiniz." / "Sınav oluştur".
- **Sayaçlar:** onaylı soru, bekleyen öneri, havuzdaki soru, öğrenci sayısı, sınav sayısı.
- **Öğrenme kanıtı bölümü:** `first_window`/`last_window` doluysa iki sütunlu karşılaştırma — "İlk N kart: onay %X, ortalama kurgu Y" vs "Son N kart: onay %X, ortalama kurgu Y" + fark oku (artış yeşil, düşüş kırmızı) ve tek cümlelik yorum ("Öneriler sizin ölçünüze yaklaşıyor."). Pencere yoksa: "Öğrenme eğrisi için en az 20 puanlama gerekiyor (şu an N)."
- **Zorluk uyumu:** `difficulty_deviation` varsa "Sistemin zorluk tahmini sizinkinden ortalama X puan sapıyor." (≤1.5 ise yeşil rozet "uyumlu").
- **Şablon durumu:** deneme/etkin/devre dışı sayıları; devre dışı > 0 ise açıklama: "Sürekli reddedilen N şablon üretimden çıkarıldı."

**Ayarlar sözleşmesi** (`/ayarlar`):
- **Dershane** bölümü: ad değiştirme (owner), oluşturulma tarihi.
- **Ekip** bölümü (owner): üye tablosu (ad, e-posta, rol), "Davet kodu oluştur" → kod kutusu + "Kopyala" + son kullanma tarihi + açıklama ("Bu kodu yeni hocaya verin; kayıt ekranında 'Davetle katıl' bağlantısını kullansın."), üye çıkarma (onaylı, kendini çıkaramaz uyarısı sunucudan gelir).
- **Yapay zekâ** bölümü: `llm_enabled` durum rozeti; kapalıysa "Sunucuya `ANTHROPIC_API_KEY` tanımlandığında dosya/fotoğraf okuma, reçete önerisi ve metin güzelleştirme açılır." metni.
- **Veri** bölümü: "Yedek indir" (owner; `api.workspace.backupUrl()`), gizlilik notu, "Çalışma alanını sil" (owner; kırmızı, ad yazarak onay; başarıda `/giris`e atar).
- teacher rolündeki kullanıcıda owner'a özel bölümler görünmez.

- [ ] **Adım 1: Başarısız testleri yaz** — panel: her `next_step` değeri için doğru metin/düğme (parametrik test), pencere yokken eşik metni, sapma rozeti; ayarlar: davet kodu oluşturma ve kopyalama, ad değiştirme çağrısı, teacher rolünde owner bölümlerinin olmaması, silme akışında ad eşleşmeden düğmenin pasif olması.
- [ ] **Adım 2–4:** başarısızlığı doğrula → yaz → `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] **Adım 5: Commit** — `git commit -m "feat(web): panel (öğrenme kanıtı) ve ayarlar ekranı"`

---

### Task 9: Derleme bütünleşmesi ve uçtan uca duman testi

**Files:**
- Create: `web/playwright.config.ts`, `web/e2e/akis.spec.ts`
- Modify: `web/package.json` (`e2e` betiği), `README.md` (arayüz bölümü), depo kökü `.gitignore` (`web/test-results/`, `web/playwright-report/`)
- Test: Playwright senaryosu

**Sözleşme.**
- `npm run build` → `web/dist`; FastAPI `QC_WEB_DIST` ile bunu sunar (Plan B Task 8). Elle doğrulama: `npm run build && QC_DATA_DIR=/tmp/qc-e2e QC_WEB_DIST=$PWD/web/dist .venv/bin/questioncrator serve --port 8123` → `http://127.0.0.1:8123` uygulamayı açar, derin bağlantı (`/ogrenciler`) yenilendiğinde de çalışır.
- **Playwright senaryosu** (tek dosya, tek tarayıcı — chromium): `webServer` olarak yukarıdaki komutu başlatır (`reuseExistingServer: false`, temiz `QC_DATA_DIR` = `test-results/veri`).
  Akış: kayıt ol (örnek havuzla) → panelde "Öneri üret" → 6 kart üret → iki kartı klavyeyle puanla (`A`) → soru bankasında 2 soru → otomatik sınav oluştur (2 soru) → sınav detayında cevap anahtarı görünür → yazdırma görünümü açılır ve başlık + "Ad Soyad" alanı görünür → Word indirme bağlantısının yanıtı 200 ve `content-type` docx.
  Ek doğrulama: öğrenci ekle → 2 soru üret → biri onaylanır → çalışma kağıdı oluşturulur.
- Playwright kurulumu ağ gerektirir (`npx playwright install chromium`); ağ yoksa bu task `BLOCKED` raporlanır, diğer adımlar (derleme bütünleşmesi + elle doğrulama) yine tamamlanır.

- [ ] **Adım 1: `npm run build` ve sunucudan servis edilmeyi elle doğrula;** sonucu rapora yaz.
- [ ] **Adım 2: Playwright'i kur ve senaryoyu yaz** — `npm i -D @playwright/test && npx playwright install chromium`.
- [ ] **Adım 3: `npm run e2e` yeşil olana kadar çalıştır** (kırılganlık: ağ/port çakışması; sabit port 8123 yerine `PORT` env'i kullan).
- [ ] **Adım 4: README'ye arayüz ve e2e bölümlerini ekle.**
- [ ] **Adım 5: Commit** — `git commit -m "feat(web): derleme bütünleşmesi ve uçtan uca duman testi"`

---

## Plan C Bitiş Kontrolü

- [ ] `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` temiz.
- [ ] Tüm ekranlar demo veriyle elle gezildi; 360 px genişlikte yatay kaydırma yok.
- [ ] Kart akışı yalnız klavyeyle kullanılabiliyor; puanlamadan onay verilemiyor.
- [ ] Yazdırma önizlemesi A4'te düzgün; cevap anahtarı ayrı sayfada.
- [ ] Playwright duman testi yeşil (ya da ağ yokluğu gerekçesiyle ledger'a işlenmiş).
- [ ] Bağımsız kod incelemesi + bulguların ikinci geçişte doğrulanması.
