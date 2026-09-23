<template>
  <section class="imaging">
    <header>
      <p>Patient 360</p>
      <h1>Imaging</h1>
    </header>
    <ResourceNotFound v-if="missing" :patient-key="patientId" />
    <p v-else-if="error && !loading" class="empty">{{ error }}</p>
    <template v-else-if="!loading">
      <ClinicalCard v-for="study in studies" :key="String(study.cite_id)" :title="String(study.procedure_display || study.modality || 'Imaging study')" :eyebrow="studyEyebrow(study)">
        <div v-if="session.hasPanel('imaging') && pixelId(study)" class="study-actions">
          <RouterLink
            class="study-row"
            :to="{ name: 'patient-ohif', params: { patientId }, query: { study: pixelId(study) } }"
            :aria-label="`Open in viewer: ${study.procedure_display || study.modality || 'Imaging study'}`"
          >
            <span class="study-row__meta">
              <span class="study-row__eyebrow">{{ studyThumbHint(study) }}</span>
              <span class="study-row__title">{{ study.procedure_display || study.modality || 'Imaging study' }}</span>
            </span>
            <span class="study-row__action">Open in viewer</span>
          </RouterLink>
          <button
            v-if="isCt(study)"
            type="button"
            class="reprocess"
            :disabled="reprocessBusy === pixelId(study)"
            @click="reprocess(study)"
          >
            {{ reprocessBusy === pixelId(study) ? 'Reprocessing…' : 'Reprocess CT' }}
          </button>
          <p v-if="reprocessNote[pixelId(study) || '']" class="meta">{{ reprocessNote[pixelId(study) || ''] }}</p>
        </div>
        <p v-else-if="!session.hasPanel('imaging')" class="meta">Metadata only for this role.</p>
      </ClinicalCard>
      <ClinicalCard v-for="report in reports" :key="String(report.cite_id)" :title="String(report.display || 'Imaging report')" eyebrow="Report">
        <p v-if="report.conclusion_text">{{ report.conclusion_text }}</p>
        <p v-else class="meta">Metadata only for this role.</p>
        <SignedMediaButton
          v-if="session.hasPanel('imaging') && reportKey(report)"
          :patient-key="patientId"
          :object-key="reportKey(report)"
          :label="String(report.display || 'Imaging report')"
        />
      </ClinicalCard>
      <p v-if="!studies.length && !reports.length" class="empty">No imaging is visible for this record.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import SignedMediaButton from '../../components/ui/SignedMediaButton.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { formatLabDate } from '../../services/patientRecord';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import ResourceNotFound from './ResourceNotFound.vue';

const route = useRoute();
const session = useSessionStore();
const studies = ref<Record<string, unknown>[]>([]);
const reports = ref<Record<string, unknown>[]>([]);
const error = ref('');
const missing = ref(false);
const reprocessBusy = ref('');
const reprocessNote = ref<Record<string, string>>({});
const patientId = computed(() => String(route.params.patientId));

function pixelId(row: Record<string, unknown>): string | undefined {
  const value = String(row.orthanc_id || '');
  return value || undefined;
}

function reportKey(row: Record<string, unknown>): string | undefined {
  const value = String(row.report_ref || '');
  return value || undefined;
}

function studyEyebrow(study: Record<string, unknown>): string {
  const when = study.study_at ? formatLabDate(String(study.study_at)) : '';
  const modality = study.modality ? String(study.modality) : '';
  return [when, modality].filter(Boolean).join(' · ');
}

function isCt(study: Record<string, unknown>): boolean {
  return String(study.modality || '').toUpperCase() === 'CT';
}

async function reprocess(study: Record<string, unknown>) {
  const studyId = pixelId(study);
  if (!studyId) return;
  reprocessBusy.value = studyId;
  reprocessNote.value = { ...reprocessNote.value, [studyId]: '' };
  try {
    const body = await apiClient.reprocessStudy(patientId.value, studyId);
    reprocessNote.value = {
      ...reprocessNote.value,
      [studyId]: body.report_text || 'VISTA-3D overlay stored. Open the viewer to toggle it.'
    };
  } catch (err) {
    reprocessNote.value = {
      ...reprocessNote.value,
      [studyId]: err instanceof ApiError && err.notFound
        ? 'This study cannot be reprocessed.'
        : (err as Error).message
    };
  } finally {
    reprocessBusy.value = '';
  }
}

function studyThumbHint(study: Record<string, unknown>): string {
  const modality = study.modality ? String(study.modality) : 'Study';
  const frames = Number(study.instance_count || 0);
  if (frames > 1) return `${modality} · ${frames} frames`;
  return modality;
}

const { loading } = useLiveLoad(async () => {
  error.value = '';
  missing.value = false;
  try {
    const body = await apiClient.imaging(String(route.params.patientId));
    studies.value = body.studies;
    reports.value = body.reports;
  } catch (err) {
    missing.value = err instanceof ApiError && err.notFound;
    error.value = missing.value ? '' : (err as Error).message;
  }
});
</script>

<style scoped>
.imaging {
  display: grid;
  gap: var(--space-5);
  max-width: 900px;
}
.empty, .meta {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.study-actions {
  display: grid;
  gap: var(--space-3);
  margin-top: var(--space-3);
}
.reprocess {
  justify-self: start;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--color-line);
  border-radius: 10px;
  background: var(--color-surface);
  color: var(--color-ink);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}
.reprocess:disabled {
  cursor: wait;
  opacity: 0.7;
}
.study-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
  margin-top: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-line);
  border-radius: 12px;
  background: var(--color-surface-raised);
  color: inherit;
  text-decoration: none;
}
.study-row:hover {
  border-color: rgb(29 78 216 / 28%);
  background: var(--color-accent-soft);
}
.study-row__meta { display: grid; gap: 2px; min-width: 0; }
.study-row__eyebrow {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.study-row__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-md);
  font-weight: 600;
  color: var(--color-ink);
}
.study-row__action {
  flex: 0 0 auto;
  color: var(--color-accent-ink);
  font-size: var(--text-sm);
  font-weight: 600;
}
</style>
