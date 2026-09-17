<template>
  <ClinicalCard title="Since your last consultation">
    <div class="changes">
      <button v-for="change in ungatedChanges" :key="change.label" type="button" @click="ui.highlightSource(change.target)"><span>{{ change.label }}</span><span aria-hidden="true">→</span></button>
      <AccessGateMulti :fields="['labs', 'medications']">
        <button v-for="change in gatedChanges" :key="change.label" type="button" @click="ui.highlightSource(change.target)"><span>{{ change.label }}</span><span aria-hidden="true">→</span></button>
      </AccessGateMulti>
    </div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGateMulti from '../../components/access/AccessGateMulti.vue';
import { useUiStore } from '../../stores/useUiStore.js';
const ui = useUiStore();
// Generic, non-lab/medication facts — visible to every role.
const ungatedChanges = [
  { label: '3 new symptom entries', target: 'event-patient-update-sept-02' },
  { label: 'No new allergies', target: 'allergies' }
];
// Lab- and medication-derived facts — same tags as LabsView.vue / MedicationsView.vue.
const gatedChanges = [
  { label: '1 new laboratory result', target: 'event-lab-aug-18' },
  { label: 'LDL increased 12%', target: 'event-lab-aug-18' },
  { label: 'Patient reported starting magnesium', target: 'event-patient-update-sept-02' },
  { label: 'No clinician-entered medication changes', target: 'medications' }
];
</script>

<style scoped>
.changes { display: grid; gap: 8px; }.changes button { display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 10px 14px; text-align: left; cursor: pointer; }.changes button:hover { border-color: var(--color-pink); background: var(--color-pink-soft); }
</style>
