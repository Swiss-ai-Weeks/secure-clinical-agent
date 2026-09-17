<template>
  <ClinicalCard title="✦ Clinical Brief" :ai="true">
    <AccessGateMulti :fields="['majorDiagnoses', 'labs']"><ul class="brief"><li v-for="statement in briefStatements" :key="statement">{{ statement }}</li></ul></AccessGateMulti>
    <div class="actions"><button type="button">View sources</button><button type="button">Regenerate summary</button><button type="button" class="actions__primary" @click="ui.openAskPanel(patient.id)">Ask follow-up</button></div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGateMulti from '../../components/access/AccessGateMulti.vue';
import { useUiStore } from '../../stores/useUiStore';
defineProps<{ patient: Patient }>();
const ui = useUiStore();
const briefStatements = [
  'Emma’s migraine frequency has increased from approximately once per month to three times per month since June.',
  'Her latest LDL measurement is elevated compared with her previous result.',
  'No neurological red flags have been documented.'
];
</script>

<style scoped>
.brief { display: grid; gap: 12px; margin: 0; padding-left: 22px; }.brief li::marker { content: '✦  '; color: var(--color-warning); }.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 700; }.actions .actions__primary { border-color: var(--color-plum); background: var(--color-plum); color: white; }
</style>
