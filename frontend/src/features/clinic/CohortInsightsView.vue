<template>
  <section class="cohort">
    <header>
      <p>Aggregates</p>
      <h1>Cohort insights</h1>
      <span>Live <code>/tools/query</code> aggregates. Small cells are suppressed.</span>
    </header>
    <ClinicalCard title="Conditions by code">
      <form class="filters" @submit.prevent="run">
        <label v-if="session.me?.role === 'researcher'">Project
          <input v-model="projectId" />
        </label>
        <button type="submit">Run aggregate</button>
      </form>
      <p v-if="missing">Resource not found</p>
      <p v-else-if="result">{{ result.row_count }} visible cells · {{ result.suppressed_cells }} suppressed · k_min {{ result.obligations.k_min ?? 'none' }}</p>
      <table v-if="result?.rows.length">
        <thead><tr><th>Dims</th><th>Count</th><th>Suppressed</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in result.rows" :key="index">
            <td>{{ JSON.stringify(row.dims ?? row) }}</td>
            <td>{{ row.suppressed ? '—' : row.count }}</td>
            <td>{{ row.suppressed ? 'yes' : 'no' }}</td>
          </tr>
        </tbody>
      </table>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { QueryResponse } from '../../types/api';

const session = useSessionStore();
const projectId = ref('cohort_2026');
const result = ref<QueryResponse | null>(null);
const missing = ref(false);

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

useLiveLoad(run);
</script>

<style scoped>
.cohort { display: grid; gap: 20px; }.cohort header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.filters { display: flex; gap: 12px; align-items: end; margin-bottom: 12px; } table { width: 100%; border-collapse: collapse; } th, td { border-bottom: 1px solid var(--color-line); text-align: left; padding: 8px; }
</style>
