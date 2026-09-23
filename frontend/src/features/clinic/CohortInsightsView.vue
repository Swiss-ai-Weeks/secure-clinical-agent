<template>
  <section class="cohort">
    <header>
      <p>Aggregates</p>
      <h1>Cohort insights</h1>
      <span>Aggregated condition counts for this session. Small cells are suppressed.</span>
    </header>
    <ClinicalCard title="Conditions by code">
      <form class="filters" @submit.prevent="run">
        <label v-if="session.me?.role === 'researcher'">Project
          <input v-model="projectId" />
        </label>
        <button type="submit">Run aggregate</button>
      </form>
      <LoadingIndicator v-if="loading" message="Loading…" />
      <p v-else-if="missing" class="empty">No aggregate is available for this session.</p>
      <p v-else-if="result" class="summary">{{ result.row_count }} visible cells · {{ result.suppressed_cells }} suppressed · k_min {{ result.obligations.k_min ?? 'none' }}</p>
      <table v-if="!loading && result?.rows.length">
        <thead><tr><th>Condition</th><th>Code</th><th>Count</th><th>Suppressed</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in labeledRows" :key="index">
            <td>{{ row.title }}</td>
            <td><code>{{ row.code ?? '—' }}</code></td>
            <td>{{ row.suppressed ? '—' : row.count }}</td>
            <td>{{ row.suppressed ? 'yes' : 'no' }}</td>
          </tr>
        </tbody>
      </table>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import LoadingIndicator from '../../components/ui/LoadingIndicator.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { aggregateCellCode, aggregateCellTitle } from '../../services/aggregateLabels';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { QueryResponse } from '../../types/api';

const session = useSessionStore();
const projectId = ref('cohort_2026');
const result = ref<QueryResponse | null>(null);
const missing = ref(false);

const labeledRows = computed(() =>
  (result.value?.rows ?? []).map(row => ({
    title: aggregateCellTitle(row),
    code: aggregateCellCode(row),
    count: row.count,
    suppressed: Boolean(row.suppressed)
  }))
);

async function run() {
  missing.value = false;
  try {
    result.value = await apiClient.query('conditions', {
      aggregate: session.me?.role === 'researcher' ? { group_by: ['code'], project_id: projectId.value } : { group_by: ['code'] }
    });
  } catch (error) {
    result.value = null;
    missing.value = error instanceof ApiError && error.notFound;
  }
}

const { loading } = useLiveLoad(run);
</script>

<style scoped>
.cohort { display: grid; gap: 20px; }
.cohort header span, .empty, .summary { color: var(--color-muted); }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-bottom: 12px; }
.filters label { display: grid; gap: 4px; font-size: 13px; font-weight: 700; color: var(--color-muted); }
.filters input { min-height: 40px; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 0 10px; }
.filters button { border: 0; border-radius: var(--radius-control); background: var(--color-accent); color: white; padding: 0 14px; font-weight: 700; cursor: pointer; min-height: 40px; }
table { width: 100%; border-collapse: collapse; }
th, td { border-bottom: 1px solid var(--color-line); text-align: left; padding: 8px; }
code { font-size: 13px; color: var(--color-muted); }
</style>
