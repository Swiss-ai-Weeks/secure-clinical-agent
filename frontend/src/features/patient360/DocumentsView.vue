<template>
  <section class="documents">
    <header>
      <p>Patient 360</p>
      <h1>Documents</h1>
      <label v-if="!missing && canUpload" class="upload" :class="{ busy: uploading }" for="upload-document">
        {{ uploading ? 'Uploading…' : 'Upload document' }}
        <input id="upload-document" aria-label="Upload document" type="file" :disabled="uploading" @change="upload" />
      </label>
    </header>
    <p v-if="status" :class="{ error: statusError }" role="status">{{ status }}</p>
    <ResourceNotFound v-if="missing" :patient-key="patientId" />
    <ClinicalCard v-else title="Patient documents">
      <div v-if="!loading" class="documents__list">
        <article v-for="document in documents" :key="document.id">
          <div>
            <h2>{{ document.title }}</h2>
            <p>{{ document.type }} · {{ document.date }} · {{ document.source }}</p>
            <p v-if="document.summary" class="summary">{{ document.summary }}</p>
            <SignedMediaButton
              v-if="document.objectKey || document.studyId"
              :patient-key="patientId"
              :object-key="document.objectKey"
              :study-id="document.studyId"
              :label="document.title"
            />
            <button
              v-if="canUpload && document.objectKey?.startsWith('notes/')"
              type="button"
              class="delete"
              :disabled="removing === document.objectKey"
              @click="remove(document.objectKey)"
            >
              {{ removing === document.objectKey ? 'Deleting…' : 'Delete' }}
            </button>
          </div>
          <StatusPill :label="document.processingState" :tone="document.processingState === 'processed' ? 'success' : 'warning'" />
        </article>
        <p v-if="!documents.length" class="empty">No uploaded or imaging documents are visible.</p>
      </div>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import SignedMediaButton from '../../components/ui/SignedMediaButton.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import ResourceNotFound from './ResourceNotFound.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { MedicalDocument } from '../../types/patient360';

const route = useRoute();
const documents = ref<MedicalDocument[]>([]);
const status = ref('');
const statusError = ref(false);
const uploading = ref(false);
const removing = ref('');
const missing = ref(false);
const canUpload = ref(false);
const patientId = computed(() => String(route.params.patientId));

async function refresh() {
  const patient = await apiClient.getPatient(patientId.value);
  documents.value = patient.documents;
  canUpload.value = patient.canUpload === true;
}

const { loading } = useLiveLoad(async () => {
  status.value = '';
  statusError.value = false;
  missing.value = false;
  canUpload.value = false;
  try {
    await refresh();
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
    canUpload.value = false;
  }
});

function uploadStatus(name: string, result: { status: string; reason?: string }) {
  if (result.reason === 'content_safety' || result.reason === 'content_safety_unavailable') {
    return `${name} was blocked and was not added to the chart.`;
  }
  if (result.status !== 'processed') return `${name} stayed in quarantine.`;
  return `${name}: ${result.status}`;
}

async function remove(objectKey: string) {
  removing.value = objectKey;
  status.value = '';
  statusError.value = false;
  try {
    await apiClient.deleteDocument(patientId.value, objectKey);
    status.value = 'Document deleted.';
    await refresh();
  } catch (error) {
    statusError.value = true;
    status.value = error instanceof ApiError ? error.message : 'Delete failed';
  } finally {
    removing.value = '';
  }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  uploading.value = true;
  status.value = '';
  statusError.value = false;
  try {
    const result = await apiClient.uploadDocument(patientId.value, file);
    status.value = uploadStatus(file.name, result);
    await refresh();
  } catch (error) {
    statusError.value = true;
    status.value = error instanceof ApiError ? error.message : 'Upload failed';
  } finally {
    uploading.value = false;
    input.value = '';
  }
}
</script>

<style scoped>
.documents {
  display: grid;
  gap: var(--space-5);
  max-width: min(1000px, 100%);
  min-width: 0;
}
.documents header {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  column-gap: var(--space-4);
  row-gap: var(--space-2);
}
.documents header p { grid-column: 1 / -1; }
.documents header h1 { margin: 0; }
.upload {
  position: relative;
  display: inline-flex;
  align-items: center;
  min-height: 40px;
  border-radius: var(--radius-control);
  background: var(--color-accent);
  color: white;
  padding: 0 var(--space-4);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.upload.busy { opacity: 0.7; cursor: wait; }
.upload input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.delete {
  margin-top: var(--space-3);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: transparent;
  color: var(--color-ink);
  padding: 0 var(--space-3);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
}
.documents__list { display: grid; gap: 0; min-width: 0; }
.documents__list article {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-width: 0;
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
}
.documents__list article:last-child { border-bottom: 0; }
.documents__list article > div { min-width: 0; max-width: 100%; }
.documents h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.documents__list p {
  margin: var(--space-1) 0 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.summary { margin-top: var(--space-2); }
.empty { margin: 0; color: var(--color-muted); }
.error { color: var(--color-danger); font-weight: 600; }
@media (max-width: 650px) {
  .documents header { grid-template-columns: 1fr; }
  .documents__list article {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
