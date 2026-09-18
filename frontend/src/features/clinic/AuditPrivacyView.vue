<template>
  <section class="audit">
    <header>
      <p>Governance</p>
      <h1>Audit & privacy</h1>
      <span>Live `audit.audit_events` rows visible to this session.</span>
    </header>
    <div class="audit__table">
      <article v-for="row in rows" :key="row.id">
        <time>{{ (row.recorded_at || '').slice(11, 16) || '—' }}</time>
        <strong>{{ row.agent_user || 'system' }}</strong>
        <span>{{ row.event_type }} {{ row.entity_patient || '' }} {{ row.reason_code || '' }}</span>
      </article>
      <p v-if="!rows.length">No audit rows for this session yet.</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import type { AuditRow } from '../../types/api';

const rows = ref<AuditRow[]>([]);

useLiveLoad(async () => {
  rows.value = (await apiClient.listAudit().catch(() => ({ events: [] }))).events;
});
</script>

<style scoped>
.audit { display: grid; gap: 20px; max-width: 1000px; }
.audit header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.audit h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }
.audit__table { border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); overflow: hidden; }
.audit__table article { display: grid; grid-template-columns: 80px 150px 1fr; gap: 16px; border-bottom: 1px solid var(--color-line); padding: 18px; }
.audit time, .audit span { color: var(--color-muted); }
</style>
