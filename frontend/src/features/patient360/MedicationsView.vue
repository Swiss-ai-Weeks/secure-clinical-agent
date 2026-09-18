<template>
  <section class="medications"><header><p>Patient 360</p><h1>Medications</h1><button type="button" @click="ui.openAskPanel(patientId)">✦ Summarize changes over six months</button></header><AccessGate field="medications"><ClinicalCard title="Current medications"><div v-if="currentMedications.length" class="medication-list"><article v-for="medication in currentMedications" :key="medication.id"><h2>{{ medication.name }}</h2><p>{{ medication.dosage }} · {{ medication.frequency }} · {{ medication.route }}</p><dl><div><dt>Started</dt><dd>{{ medication.startDate }}</dd></div><div><dt>Prescriber</dt><dd>{{ medication.prescriber }}</dd></div><div><dt>Reason</dt><dd>{{ medication.reason }}</dd></div></dl></article></div></ClinicalCard><ClinicalCard title="Historical medications"><div v-if="historicalMedications.length" class="medication-list"><article v-for="medication in historicalMedications" :key="medication.id"><h2>{{ medication.name }}</h2><p>{{ medication.dosage }} · {{ medication.frequency }} · {{ medication.route }}</p><dl><div><dt>Started</dt><dd>{{ medication.startDate }}</dd></div><div><dt>Stopped</dt><dd>{{ medication.stopDate }}</dd></div><div><dt>Prescriber</dt><dd>{{ medication.prescriber }}</dd></div><div><dt>Reason</dt><dd>{{ medication.reason }}</dd></div></dl></article></div><p v-else class="empty-copy">No historical medications recorded in this demo.</p></ClinicalCard></AccessGate></section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { mockApi } from '../../services/mockApi';
import type { Patient } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGate from '../../components/access/AccessGate.vue';
const route = useRoute(); const ui = useUiStore(); const patient = ref<Patient | null>(null); const patientId = computed(() => String(route.params.patientId));
const currentMedications = computed(() => patient.value?.medications.filter(medication => medication.current) ?? []); const historicalMedications = computed(() => patient.value?.medications.filter(medication => !medication.current) ?? []);
onMounted(async () => { patient.value = await mockApi.getPatient(patientId.value); });
</script>

<style scoped>
.medications { display: grid; gap: 20px; max-width: 1000px; }.medications header { display: flex; flex-wrap: wrap; align-items: end; justify-content: space-between; gap: 16px; }.medications header p { width: 100%; margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.medications h1 { margin: 0; font-size: clamp(2rem, 4vw, 3rem); }.medications header button { border: 0; border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 16px; cursor: pointer; font-weight: 750; }.medications :deep(.medication-list) { display: grid; gap: 12px; }.medications :deep(.medication-list article) { border-bottom: 1px solid var(--color-line); padding-bottom: 12px; }.medications :deep(.medication-list article:last-child) { border-bottom: 0; }.medications :deep(.medication-list h2) { margin: 0; font-size: 1.1rem; }.medications :deep(.medication-list p) { margin: 4px 0 10px; color: var(--color-muted); }.medications :deep(dl) { display: flex; flex-wrap: wrap; gap: 20px; margin: 0; }.medications :deep(dt) { color: var(--color-muted); font-size: 13px; font-weight: 700; }.medications :deep(dd) { margin: 0; }.medications :deep(.empty-copy) { color: var(--color-muted); }
</style>
