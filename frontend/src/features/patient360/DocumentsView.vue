<template>
  <section class="documents">
    <header>
      <p>Patient 360</p>
      <h1>Documents</h1>
      <label class="upload" for="upload-document">Upload document
        <input id="upload-document" aria-label="Upload document" type="file" @change="upload" />
      </label>
    </header>
    <p v-if="status">{{ status }}</p>
    <p v-if="missing">Resource not found</p>
    <ClinicalCard v-else title="Patient documents">
      <div class="documents__list">
        <article v-for="document in documents" :key="document.id">
          <div>
            <h2>{{ document.title }}</h2>
            <p>{{ document.type }} · {{ document.date }} · {{ document.source }}</p>
            <SignedMediaButton
              v-if="document.objectKey || document.studyId"
              :patient-key="patientId"
              :object-key="document.objectKey"
              :study-id="document.studyId"
            />
          </div>
          <StatusPill :label="document.processingState" :tone="document.processingState === 'processed' ? 'success' : 'warning'" />
        </article>
        <p v-if="!documents.length">No uploaded or imaging documents are visible.</p>
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
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { MedicalDocument } from '../../types/patient360';

const route = useRoute();
const documents = ref<MedicalDocument[]>([]);
const status = ref('');
const missing = ref(false);
const patientId = computed(() => String(route.params.patientId));

async function refresh() {
  const patient = await apiClient.getPatient(patientId.value);
  documents.value = patient.documents;
}

useLiveLoad(async () => {
  status.value = '';
  missing.value = false;
  documents.value = [];
  try {
    await refresh();
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
  }
});

async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const result = await apiClient.uploadDocument(patientId.value, file);
  status.value = `${file.name}: ${result.status}`;
  await refresh();
}
</script>

<style scoped>
.documents { display: grid; gap: 20px; max-width: 1000px; }
.documents header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; }
.documents header p { width: 100%; margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.documents h1 { margin: 0; font-size: clamp(2rem, 4vw, 3rem); }
.upload { display: inline-flex; align-items: center; min-height: 44px; border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 16px; cursor: pointer; font-weight: 750; }
.upload input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.documents__list { display: grid; gap: 12px; }
.documents__list article { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--color-line); padding-bottom: 12px; }
.documents h2 { margin: 0; font-size: 1.1rem; }
</style>
