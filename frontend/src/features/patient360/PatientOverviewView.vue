<template>
  <div v-if="patient" class="overview"><PatientHeader :patient="patient" /><section class="overview__grid"><ClinicalBrief :patient="patient" /><SinceLastVisit :patient="patient" /><CurrentSnapshot :patient="patient" /></section></div>
  <p v-else class="loading">Loading Patient 360…</p>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { mockApi } from '../../services/mockApi';
import type { Patient } from '../../types/patient360';
import PatientHeader from './PatientHeader.vue';
import ClinicalBrief from './ClinicalBrief.vue';
import SinceLastVisit from './SinceLastVisit.vue';
import CurrentSnapshot from './CurrentSnapshot.vue';
const route = useRoute();
const patient = ref<Patient | null>(null);
onMounted(async () => { patient.value = await mockApi.getPatient(String(route.params.patientId)); });
</script>

<style scoped>
.overview { display: grid; gap: 24px; }.overview__grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }.overview__grid > :last-child { grid-column: 1 / -1; }.loading { color: var(--color-muted); }
@media (max-width: 900px) { .overview__grid { grid-template-columns: 1fr; }.overview__grid > :last-child { grid-column: auto; } }
</style>
