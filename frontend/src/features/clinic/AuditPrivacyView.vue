<template>
  <section class="audit">
    <header>
      <p>Governance</p>
      <h1>Audit & privacy</h1>
      <span>Access and chart activity visible to you.</span>
    </header>
    <div v-if="!loading" class="audit__table">
      <article v-for="row in displayRows" :key="row.id">
        <time>{{ row.when }}</time>
        <strong>{{ row.actor }}</strong>
        <span>{{ row.action }}</span>
      </article>
      <p v-if="!displayRows.length" class="empty">No activity for this sign-in yet.</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { actorAccessLabel } from '../../services/accessLevel';
import { describeAuditEvent } from '../../services/auditLabels';
import { apiClient } from '../../services/apiClient';
import { useSessionStore } from '../../stores/useSessionStore';
import type { AuditRow } from '../../types/api';

const session = useSessionStore();

const rows = ref<AuditRow[]>([]);

const patientNames = ref<Record<string, string>>({});

const displayRows = computed(() =>
  rows.value.map(row => {
    const described = describeAuditEvent(row, patientNames.value);
    const stamp = row.recorded_at?.slice(11, 16);
    return {
      id: row.id,
      when: stamp || described.date,
      actor: actorAccessLabel(row.agent_user, session.personas, session.me),
      action: described.title
    };
  })
);

const { loading } = useLiveLoad(async () => {
  const [audit, patients] = await Promise.all([
    apiClient.listAudit().catch(() => ({ events: [] as AuditRow[] })),
    apiClient.getPatients().catch(() => [])
  ]);
  rows.value = audit.events;
  patientNames.value = Object.fromEntries(
    patients
      .filter(patient => patient.fullName && patient.fullName !== 'Patient' && !/p_[0-9a-f]/i.test(patient.fullName))
      .map(patient => [patient.id, patient.fullName])
  );
});
</script>

<style scoped>
.audit { display: grid; gap: 20px; max-width: 1000px; }
.audit header span, .empty { color: var(--color-muted); }
.audit__table { border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); overflow: hidden; }
.audit__table article { display: grid; grid-template-columns: 80px minmax(10rem, 0.7fr) 1fr; gap: 16px; border-bottom: 1px solid var(--color-line); padding: 18px; }
.audit__table article:last-child { border-bottom: 0; }
.audit time, .audit span { color: var(--color-muted); }
@media (max-width: 700px) {
  .audit__table article { grid-template-columns: 1fr; gap: 4px; }
}
</style>
