<template>
  <section class="imaging">
    <header>
      <p>Patient 360</p>
      <h1>Imaging</h1>
    </header>
    <p v-if="error" class="empty">{{ error }}</p>
    <article v-for="study in studies" :key="String(study.cite_id)">
      <h2>{{ study.procedure_display || study.modality }}</h2>
      <p>{{ study.study_at }} · {{ study.modality }}</p>
      <SignedMediaButton
        v-if="session.hasPanel('imaging') && studyId(study)"
        :patient-key="patientId"
        :study-id="studyId(study)"
      />
    </article>
    <article v-for="report in reports" :key="String(report.cite_id)">
      <h2>{{ report.display || 'Report' }}</h2>
      <p v-if="report.conclusion_text">{{ report.conclusion_text }}</p>
      <p v-else>Metadata only for this role.</p>
      <SignedMediaButton
        v-if="session.hasPanel('imaging') && studyId(report)"
        :patient-key="patientId"
        :study-id="studyId(report)"
      />
    </article>
    <p v-if="!studies.length && !reports.length && !error" class="empty">No imaging is visible for this record.</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import SignedMediaButton from '../../components/ui/SignedMediaButton.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';

const route = useRoute();
const session = useSessionStore();
const studies = ref<Record<string, unknown>[]>([]);
const reports = ref<Record<string, unknown>[]>([]);
const error = ref('');
const patientId = computed(() => String(route.params.patientId));

function studyId(row: Record<string, unknown>): string | undefined {
  const value = String(row.study_id || row.orthanc_id || row.cite_id || '');
  return value || undefined;
}

useLiveLoad(async () => {
  error.value = '';
  studies.value = [];
  reports.value = [];
  try {
    const body = await apiClient.imaging(String(route.params.patientId));
    studies.value = body.studies;
    reports.value = body.reports;
  } catch (err) {
    error.value = err instanceof ApiError && err.notFound ? 'No imaging is visible for this record.' : (err as Error).message;
  }
});
</script>

<style scoped>
.imaging { display: grid; gap: 16px; max-width: 900px; }
.imaging header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.imaging h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }
.imaging article { border: 1px solid var(--color-line); border-radius: var(--radius-card); padding: 16px; }
.empty { color: var(--color-muted); }
</style>
