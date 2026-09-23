<template>
  <section class="redteam" :aria-busy="running || loading">
    <header>
      <p>Governance</p>
      <h1>Red team</h1>
      <span>
        These cases check whether Patient360 refuses unauthorized access, keeps sessions isolated, and blocks prompt attacks — failures stay visible.
      </span>
    </header>

    <div class="toolbar">
      <button type="button" class="run" :disabled="running" :aria-busy="running" @click="runSuite">
        {{ running ? 'Running suite…' : scored ? 'Re-run suite' : 'Run suite' }}
      </button>
      <p v-if="running" class="running" role="status">
        Scoring the catalog. Pass, partial, and fail appear when this run finishes.
      </p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </div>

    <LoadingIndicator v-if="running" message="Running the suite…" />

    <section v-if="scored" class="last-run" aria-label="Last run">
      <p class="last-run__label">Last run</p>
      <div class="scoreboard">
        <article class="stat stat--pass">
          <p>Passed</p>
          <strong>{{ passed }}</strong>
        </article>
        <article class="stat stat--partial">
          <p>Partial</p>
          <strong>{{ partial }}</strong>
        </article>
        <article class="stat stat--fail">
          <p>Failed</p>
          <strong>{{ failed }}</strong>
        </article>
        <article class="stat stat--asr">
          <p>Attack success</p>
          <strong>{{ asr }}</strong>
          <small>Share of cases that failed</small>
        </article>
      </div>
    </section>

    <p v-else-if="!scored && !running && cases.length && !error" class="hint">
      Results appear after you run the suite. The list below is the catalog of checks.
    </p>

    <p v-if="!running && !loading && !cases.length && !error" class="empty">
      No cases are available on this server. Results appear after the catalog is loaded and you run the suite.
    </p>

    <section v-for="group in groups" :key="group.layer" class="layer">
      <div class="layer__head">
        <div class="layer__title">
          <p>{{ group.rows.length }} {{ group.rows.length === 1 ? 'case' : 'cases' }}</p>
          <h2>{{ group.title }}</h2>
        </div>
        <span v-if="scored">{{ groupMeta(group) }}</span>
      </div>
      <p class="layer__note">{{ group.note }}</p>
      <div class="cases">
        <article
          v-for="row in group.rows"
          :key="String(row.id)"
          :class="['case', `tone-${resultKind(row.result)}`]"
        >
          <div class="case__row">
            <div class="case__copy">
              <h3>{{ caseTitle(row) }}</h3>
              <p>{{ caseSummary(row) }}</p>
            </div>
            <StatusPill :label="resultLabel(row.result)" :tone="resultTone(row.result)" />
          </div>
          <details v-if="techDetails(row).length" class="tech">
            <summary>Technical detail</summary>
            <dl>
              <div v-for="item in techDetails(row)" :key="item.label">
                <dt>{{ item.label }}</dt>
                <dd>{{ item.value }}</dd>
              </div>
            </dl>
          </details>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import {
  attackSuccessRate,
  caseSummary,
  caseTitle,
  groupCountLabel,
  resultKind,
  resultLabel,
  resultTone,
  techDetails,
  type CaseRow
} from '../../services/redTeamLabels';
import LoadingIndicator from '../../components/ui/LoadingIndicator.vue';
import StatusPill from '../../components/ui/StatusPill.vue';

interface LayerGroup {
  layer: string;
  title: string;
  note: string;
  rows: CaseRow[];
}

const LAYERS = [
  {
    layer: 'sandbox',
    title: 'Session isolation',
    note: 'Each sign-in gets its own workspace. Sharing or leaking that workspace is a failure.'
  },
  {
    layer: 'pdp',
    title: 'Access policy',
    note: 'Role, duty, and consent are checked before any chart is shown. Unauthorized and unknown patients look the same.'
  },
  {
    layer: 'safety',
    title: 'Safety rails',
    note: 'Prompt attacks and planted instructions must be refused. A refusal counts only when the safety check reports it.'
  }
] as const;

const cases = ref<CaseRow[]>([]);
const passed = ref(0);
const failed = ref(0);
const partial = ref(0);
const running = ref(false);
const error = ref('');
const asr = computed(() => attackSuccessRate(failed.value, cases.value.length));
const scored = computed(() =>
  cases.value.some(row => ['pass', 'fail', 'partial'].includes(String(row.result || '')))
);

const groups = computed<LayerGroup[]>(() =>
  LAYERS.map(entry => ({
    ...entry,
    rows: cases.value.filter(row => String(row.layer || 'pdp') === entry.layer)
  })).filter(group => group.rows.length > 0)
);

function countOf(rows: CaseRow[], result: string): number {
  return rows.filter(row => String(row.result || '') === result).length;
}

function groupMeta(group: LayerGroup): string {
  if (!scored.value) return `${group.rows.length} cases`;
  return groupCountLabel(
    countOf(group.rows, 'pass'),
    countOf(group.rows, 'fail'),
    countOf(group.rows, 'partial')
  );
}

function applyBody(body: {
  cases?: CaseRow[];
  pass?: number;
  fail?: number;
  partial?: number;
}) {
  cases.value = body.cases ?? [];
  passed.value = Number(body.pass ?? cases.value.filter(row => row.result === 'pass').length);
  failed.value = Number(body.fail ?? cases.value.filter(row => row.result === 'fail').length);
  partial.value = Number(body.partial ?? cases.value.filter(row => row.result === 'partial').length);
}

async function runSuite() {
  running.value = true;
  error.value = '';
  try {
    applyBody(await apiClient.redteam());
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Red-team suite failed';
  } finally {
    running.value = false;
  }
}

const { loading } = useLiveLoad(async () => {
  // Show last scored board or the catalog. Do not auto-run on every visit.
  error.value = '';
  try {
    applyBody(await apiClient.listRedteam());
  } catch (err) {
    cases.value = [];
    error.value = err instanceof Error ? err.message : 'Could not load the red-team catalog';
  }
});
</script>

<style scoped>
.redteam {
  display: grid;
  gap: var(--space-5);
  max-width: 1000px;
  min-width: 0;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
}

.running,
.hint,
.empty {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
  max-width: 40rem;
}

.error {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--text-sm);
}

.last-run {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
}

.last-run__label {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
  line-height: var(--leading-tight);
}

.scoreboard {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  min-width: 0;
}

.stat {
  display: grid;
  align-content: start;
  gap: var(--space-1);
  min-width: 0;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  padding: var(--space-4);
  box-shadow: var(--shadow-soft);
}

.stat p,
.stat small {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
  line-height: var(--leading-tight);
}

.stat small {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
}

.stat strong {
  font-size: var(--text-2xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  font-variant-numeric: tabular-nums;
  line-height: var(--leading-tight);
}

.stat--pass strong { color: var(--color-success); }
.stat--partial strong { color: var(--color-warning); }
.stat--fail strong { color: var(--color-danger); }
.stat--asr strong { color: var(--color-ink); }

.layer {
  display: grid;
  gap: var(--space-4);
  min-width: 0;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  padding: var(--space-6);
  box-shadow: var(--shadow-soft);
}

.layer__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-3);
}

.layer__title p,
.layer__head > span,
.layer__note {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
  line-height: var(--leading-tight);
}

.layer h2 {
  margin: var(--space-1) 0 0;
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  line-height: var(--leading-tight);
  text-transform: none;
}

.layer__head > span {
  font-variant-numeric: tabular-nums;
  text-transform: none;
  letter-spacing: -0.01em;
  font-weight: 500;
  font-size: var(--text-sm);
  color: var(--color-muted-strong);
}

.layer__note {
  font-weight: 400;
  font-size: var(--text-sm);
  letter-spacing: -0.01em;
  text-transform: none;
  line-height: var(--leading-snug);
  max-width: 42rem;
}

.cases {
  display: grid;
  min-width: 0;
}

.case {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
}

.case:first-child { padding-top: 0; }
.case:last-child { border-bottom: 0; padding-bottom: 0; }

.tone-fail { box-shadow: inset 3px 0 0 var(--color-danger); padding-left: var(--space-3); }
.tone-partial { box-shadow: inset 3px 0 0 var(--color-warning); padding-left: var(--space-3); }
.tone-pass { box-shadow: inset 3px 0 0 var(--color-success); padding-left: var(--space-3); }

.case__row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  column-gap: var(--space-4);
  row-gap: var(--space-2);
  min-width: 0;
}

.case__copy {
  display: grid;
  gap: var(--space-1);
  min-width: 0;
}

.case h3 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: var(--leading-snug);
}

.case__copy p {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}

.case__row :deep(.pill) {
  justify-self: end;
  flex-shrink: 0;
  margin-top: 2px;
}

.tech {
  min-width: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.tech summary {
  cursor: pointer;
  font-weight: 600;
  color: var(--color-muted-strong);
}

.tech dl {
  display: grid;
  gap: var(--space-2);
  margin: var(--space-3) 0 0;
}

.tech dl > div {
  display: grid;
  grid-template-columns: minmax(7rem, 11rem) minmax(0, 1fr);
  gap: var(--space-3);
  min-width: 0;
}

.tech dt {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}

.tech dd {
  margin: 0;
  min-width: 0;
  color: var(--color-ink);
  overflow-wrap: anywhere;
  word-break: break-word;
}

@media (max-width: 800px) {
  .scoreboard { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .case__row { grid-template-columns: minmax(0, 1fr); }
  .case__row :deep(.pill) { justify-self: start; }
  .tech dl > div { grid-template-columns: 1fr; gap: var(--space-1); }
}
</style>
