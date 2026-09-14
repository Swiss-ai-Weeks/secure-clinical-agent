# Patient360

Vue.js frontend demo for the Patient360 clinical workspace. It uses deterministic mock data only; no backend is required to run it.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

## Demo path

1. Open the Home dashboard.
2. Select Emma Laurent.
3. Review the Patient 360 overview, Clinical Brief, Since Last Visit, and Current Snapshot.
4. Open Timeline.
5. Ask Patient360 what changed with Emma's migraines over the last six months.
6. Click an AI citation to highlight the source event.
7. Open Documents, upload a mock report, and accept an extracted fact.

## Backend integration

All data access is isolated in `src/services/mockApi.ts`. Replace those functions with real backend clients when the backend is ready.
