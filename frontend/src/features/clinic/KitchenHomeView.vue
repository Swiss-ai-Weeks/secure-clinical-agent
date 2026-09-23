<template>
  <section class="kitchen">
    <header>
      <p>{{ kitchenEyebrow }}</p>
      <h1>Ward diet board</h1>
      <span>Ward counts and tray cards from diet orders. Clinical labs and notes stay off this workspace.</span>
    </header>
    <template v-if="!loading">
    <ClinicalCard title="Ward diet counts">
      <p v-if="missing" class="empty">No ward diet aggregate is available for this session.</p>
      <p v-else-if="aggregate">{{ aggregate.row_count }} visible cells · {{ aggregate.suppressed_cells }} suppressed · k_min {{ aggregate.obligations.k_min ?? 'none' }}</p>
      <table v-if="aggregate?.rows.length">
        <thead><tr><th>Ward</th><th>Count</th><th>Suppressed</th></tr></thead>
        <tbody>
          <tr v-for="(row, index) in aggregate.rows" :key="index">
            <td>{{ wardLabel(row) }}</td>
            <td>{{ row.suppressed ? '—' : row.count }}</td>
            <td>{{ row.suppressed ? 'yes' : 'no' }}</td>
          </tr>
        </tbody>
      </table>
    </ClinicalCard>
    <ClinicalCard title="Trays on this ward">
      <div class="trays">
        <RouterLink v-for="tray in trays" :key="tray.id" class="tray" :to="defaultPatientPath('kitchen', tray.id)">
          <span class="avatar">{{ tray.avatarInitials }}</span>
          <span>
            <strong>{{ tray.fullName }}</strong>
            <small>{{ tray.reason || tray.reasonForVisit || 'Diet order' }}</small>
          </span>
          <span aria-hidden="true">→</span>
        </RouterLink>
        <p v-if="!trays.length" class="empty">No diet orders are visible on this session.</p>
      </div>
    </ClinicalCard>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { accessLevel, withAccessLevel } from '../../services/accessLevel';
import { defaultPatientPath } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';
import type { QueryResponse } from '../../types/api';
import type { PatientSummary } from '../../types/patient360';

const session = useSessionStore();
const kitchenEyebrow = computed(() => withAccessLevel(session.me?.display ?? 'Dietary staff', accessLevel(session.me) || 'Dietary'));
const aggregate = ref<QueryResponse | null>(null);
const trays = ref<PatientSummary[]>([]);
const missing = ref(false);

function wardLabel(row: Record<string, unknown>): string {
  const dims = (row.dims ?? row) as Record<string, unknown>;
  const ward = dims.ward;
  if (ward == null || ward === '') return 'Unspecified ward';
  return String(ward);
}

const { loading } = useLiveLoad(async () => {
  missing.value = false;
  try {
    aggregate.value = await apiClient.query('diet', { aggregate: { group_by: ['ward'] } });
  } catch (error) {
    aggregate.value = null;
    missing.value = error instanceof ApiError && error.notFound;
  }
  trays.value = await apiClient.getPatients().catch(() => []);
});
</script>

<style scoped>
.kitchen { display: grid; gap: 20px; max-width: 1100px; }
.kitchen header span, .empty { color: var(--color-muted); }
table { width: 100%; border-collapse: collapse; }
th, td { border-bottom: 1px solid var(--color-line); text-align: left; padding: 8px; }
.trays { display: grid; gap: 10px; }
.tray { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); color: var(--color-ink); padding: 12px; text-decoration: none; }
.tray:hover { border-color: rgb(29 78 216 / 28%); background: var(--color-accent-soft); }
.avatar { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 50%; background: var(--color-accent-soft); color: var(--color-accent-ink); font-size: 14px; font-weight: 700; }
.tray strong, .tray small { display: block; }
.tray small { margin-top: 2px; color: var(--color-muted); font-size: 14px; }
</style>
