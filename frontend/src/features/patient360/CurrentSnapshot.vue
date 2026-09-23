<template>
  <ClinicalCard title="Current snapshot"><div class="snapshot">
    <section><h3>Conditions</h3><ul><li v-for="condition in patient.majorDiagnoses" :key="condition">{{ condition }}</li><li v-if="!patient.majorDiagnoses.length">None recorded</li></ul></section>
    <section><h3>Location</h3><ul><li v-if="patient.placement">{{ patient.placement }}</li><li v-else>No current ward placement</li></ul></section>
    <section><h3>Medications</h3><ul><li v-for="medication in patient.medications" :key="medication.id"><strong>{{ medication.name }}</strong><span>{{ medication.dosage }} · {{ medication.frequency }}</span></li><li v-if="!patient.medications.length">None recorded</li></ul></section>
    <section><h3>Allergies</h3><ul><li v-for="allergy in patient.majorAllergies" :key="allergy" class="danger">{{ allergy }}</li><li v-if="!patient.majorAllergies.length">None recorded</li></ul></section>
    <section v-if="patient.measurements.length"><h3>Latest measurements</h3><div class="metrics"><MetricTile v-for="measurement in patient.measurements" :key="measurement.id" :label="measurement.label" :value="measurement.value" :detail="measurement.date" /></div></section>
    <section><h3>Latest labs</h3><div class="labs"><article v-for="group in latestLabs" :key="group.latest.id" class="lab"><div><strong>{{ group.label }}</strong><span>{{ group.latest.value }} {{ group.latest.unit }}<template v-if="group.latest.referenceRange"> · reference {{ group.latest.referenceRange }}</template></span></div><span v-if="group.latest.flag === 'high'" class="abnormal"><TrendingUp :size="18" aria-hidden="true" /> Above reference range</span><span v-else-if="group.latest.flag === 'low'" class="abnormal">Below reference range</span><span v-else>{{ labFlagLabel(group.latest.flag) }}</span></article><p v-if="!latestLabs.length">No visible laboratory rows.</p></div></section>
    <section v-if="session.workspace === 'clinical'"><h3>Notes</h3><article v-if="latestNote" class="note"><strong>{{ latestNote.title }}</strong><span>{{ latestNote.author }}<template v-if="latestNote.date"> · {{ latestNote.date }}</template></span><p>{{ noteExcerpt }}</p></article><p v-else>No published notes are visible for this record.</p></section>
    <section v-if="session.workspace === 'clinical'"><h3>Things to review</h3><ul><li v-for="risk in patient.riskIndicators" :key="risk">{{ risk }}</li><li v-if="!patient.riskIndicators.length">None on visible rows</li></ul></section>
  </div></ClinicalCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { TrendingUp } from 'lucide-vue-next';
import type { Patient } from '../../types/patient360';
import { labFlagLabel, snapshotLabGroups } from '../../services/patientRecord';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import MetricTile from '../../components/ui/MetricTile.vue';
import { useSessionStore } from '../../stores/useSessionStore';
const props = defineProps<{ patient: Patient }>();
const session = useSessionStore();
const latestLabs = computed(() => snapshotLabGroups(props.patient.labs));
const latestNote = computed(() => props.patient.notes[0] ?? null);
const noteExcerpt = computed(() => {
  const text = latestNote.value?.text ?? '';
  return text.length > 280 ? `${text.slice(0, 277).trim()}…` : text;
});
</script>

<style scoped>
.snapshot { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }.snapshot section { min-width: 0; }.snapshot h3 { margin: 0 0 8px; font-size: 1rem; }.snapshot ul { display: grid; gap: 7px; margin: 0; padding-left: 20px; }.snapshot li { padding-left: 2px; }.snapshot li.danger { color: var(--color-danger); }.snapshot li span, .lab span, .note span { display: block; color: var(--color-muted); font-size: 14px; }.note p { margin: 8px 0 0; white-space: pre-wrap; line-height: 1.5; }.metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }.labs { display: grid; gap: 8px; }.lab { display: flex; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 12px; }.abnormal { display: inline-flex !important; align-items: center; gap: 4px; color: var(--color-danger) !important; font-weight: 750; }
@media (max-width: 700px) { .snapshot { grid-template-columns: 1fr; } }
</style>
