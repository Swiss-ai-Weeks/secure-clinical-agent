<template>
  <div v-if="patient" class="overview">
    <PatientHeader :patient="patient" />
    <section class="overview__grid">
      <ClinicalBrief :patient="patient" />
      <SinceLastVisit :patient="patient" />
      <CurrentSnapshot :patient="patient" />
    </section>
  </div>
  <p v-else-if="missing" class="missing">Resource not found</p>
  <p v-else class="loading">Loading Patient 360…</p>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { Patient } from '../../types/patient360';
import PatientHeader from './PatientHeader.vue';
import ClinicalBrief from './ClinicalBrief.vue';
import SinceLastVisit from './SinceLastVisit.vue';
import CurrentSnapshot from './CurrentSnapshot.vue';

const route = useRoute();
const patient = ref<Patient | null>(null);
const missing = ref(false);

async function load() {
  missing.value = false;
  patient.value = null;
  try {
    patient.value = await apiClient.getPatient(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
  }
}

onMounted(load);
watch(() => route.params.patientId, load);
</script>

<style scoped>
.overview { display: grid; gap: 24px; }.overview__grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }.overview__grid > :last-child { grid-column: 1 / -1; }.loading, .missing { color: var(--color-muted); }
@media (max-width: 900px) { .overview__grid { grid-template-columns: 1fr; }.overview__grid > :last-child { grid-column: auto; } }
</style>
