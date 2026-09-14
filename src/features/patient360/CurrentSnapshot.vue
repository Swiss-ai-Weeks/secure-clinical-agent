<template>
  <ClinicalCard title="Current snapshot"><div class="snapshot">
    <section><h3>Conditions</h3><ul><li v-for="condition in patient.majorDiagnoses" :key="condition">{{ condition }}</li></ul></section>
    <section><h3>Medications</h3><ul><li v-for="medication in patient.medications" :key="medication.id"><strong>{{ medication.name }}</strong><span>{{ medication.dosage }} · {{ medication.frequency }}</span></li></ul></section>
    <section><h3>Allergies</h3><ul><li v-for="allergy in patient.majorAllergies" :key="allergy" class="danger">Severe allergy: {{ allergy }}</li></ul></section>
    <section><h3>Latest measurements</h3><div class="metrics"><MetricTile v-for="measurement in patient.measurements" :key="measurement.id" :label="measurement.label" :value="measurement.value" :detail="measurement.date" /></div></section>
    <section><h3>Latest labs</h3><div class="labs"><article v-for="lab in patient.labs" :key="lab.id" class="lab"><div><strong>{{ lab.label }}</strong><span>{{ lab.value }} {{ lab.unit }} · reference {{ lab.referenceRange }}</span></div><span v-if="lab.abnormal" class="abnormal"><TrendingUp :size="18" aria-hidden="true" /> Above reference range</span><span v-else>Within reference range</span></article></div></section>
    <section><h3>Things to review</h3><ul><li v-for="risk in patient.riskIndicators" :key="risk">{{ risk }}</li></ul></section>
  </div></ClinicalCard>
</template>

<script setup lang="ts">
import { TrendingUp } from 'lucide-vue-next';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import MetricTile from '../../components/ui/MetricTile.vue';
defineProps<{ patient: Patient }>();
</script>

<style scoped>
.snapshot { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }.snapshot section { min-width: 0; }.snapshot h3 { margin: 0 0 8px; font-size: 1rem; }.snapshot ul { display: grid; gap: 7px; margin: 0; padding-left: 20px; }.snapshot li { padding-left: 2px; }.snapshot li.danger { color: var(--color-danger); }.snapshot li span, .lab span { display: block; color: var(--color-muted); font-size: 14px; }.metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.labs { display: grid; gap: 8px; }.lab { display: flex; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 12px; }.abnormal { display: inline-flex !important; align-items: center; gap: 4px; color: var(--color-danger) !important; font-weight: 750; }
@media (max-width: 700px) { .snapshot { grid-template-columns: 1fr; } }
</style>
