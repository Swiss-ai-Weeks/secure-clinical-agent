# Patient360

Vue workspace for the Patient360 demo. Clinical views, Ask, notes, imaging, uploads, audit, and the red-team scoreboard call the live backend through `/api` (Vite proxy to `127.0.0.1:8088`).

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:4173`. Start the backend (compose publishes it on `127.0.0.1:8088`; host `8080` is OpenShell on this lab) so the persona switcher can `POST /auth/dev-login`.

## Demo path

1. Choose **Dr. Sarah Chen** in the persona switcher (AAL2).
2. Open **p_101** Elisabeth Keller — identity banner, labs, meds, grant `care_team` / `consultant`. No break-glass on a chart you can already open.
3. **Patients → Emergency chart key `p_205`**. Overview is a uniform not-found until **Open break-glass** (AAL2, 20+ character justification). Subsequent reads are `BTG`.
4. On Imaging or Documents, **Open signed copy** issues a dashboard-only `/media/sign` URL (no pixel viewer).
5. Switch to **Priya Nair** — per-patient pages are not found; Cohort Insights runs aggregates (`cohort_2026`).
6. Switch to **Maria Santos** — own banner on `p_103`, portal grant/revoke, book/cancel.
7. Switch to **Nina Haller** — `p_104` with adolescent rows redacted; portal grants on the visible child record.
8. Switch to **Tomas Lindqvist** — diet and food allergies only.
9. Ask Patient360 calls `/chat` (in-proc). Refusals and `policy_reason` stay visible. Notes use `/tools/notes`.

## Backend integration

`src/services/apiClient.ts` is the cookie-credential client (`credentials: 'include'`). `/me.panels` gates the shell. Home, tasks, and search are derived from identity, `/tools/query`, and `/audit`. `src/services/mockApi.ts` remains for unit fixtures only.
