<template>
  <section class="labs">
    <header><p>Patient 360</p><h1>Laboratory results</h1></header>
    <p v-if="missing" class="missing">Resource not found</p>
    <div v-else class="labs__grid">
      <ClinicalCard title="Latest results">
        <div class="results">
          <article v-for="lab in patient?.labs" :key="lab.id">
            <div><h2>{{ lab.label }}</h2><p>{{ lab.date }} · source {{ lab.sourceId }}</p></div>
            <div>
              <strong>{{ lab.value }} {{ lab.unit }}</strong>
              <span>Reference {{ lab.referenceRange || '—' }}</span>
              <StatusPill :label="lab.abnormal ? 'Above reference range' : 'Recorded'" :tone="lab.abnormal ? 'danger' : 'success'" />
            </div>
          </article>
          <p v-if="!patient?.labs.length">No visible laboratory rows.</p>
        </div>
      </ClinicalCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import StatusPill from '../../components/ui/StatusPill.vue';

const route = useRoute();
const patient = ref<Patient | null>(null);
const missing = ref(false);

async function load() {
  missing.value = false;
  try {
    patient.value = await apiClient.getPatient(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
    patient.value = null;
  }
}
onMounted(load);
watch(() => route.params.patientId, load);
</script>

<style scoped>
.labs { display: grid; gap: 20px; }.labs header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.labs h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.labs__grid { display: grid; gap: 20px; }.results { display: grid; gap: 10px; }.results article { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--color-line); padding-bottom: 12px; }.results h2 { margin: 0; font-size: 1.05rem; }.results p, .results span { display: block; margin: 4px 0; color: var(--color-muted); font-size: 14px; }.missing { color: var(--color-muted); }
</style>
