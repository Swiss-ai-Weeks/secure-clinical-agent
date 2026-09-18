<template>
  <ClinicalCard title="✦ Clinical Brief" :ai="true">
    <ul class="brief"><li v-for="statement in briefStatements" :key="statement">{{ statement }}</li></ul>
    <div class="actions"><button type="button">View sources</button><button type="button">Regenerate summary</button><button type="button" class="actions__primary" @click="ui.openAskPanel(patient.id)">Ask follow-up</button></div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { useUiStore } from '../../stores/useUiStore';
const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();
const briefStatements = computed(() => {
  const statements = [`Record ${props.patient.id} · ${props.patient.fullName}.`];
  if (props.patient.majorDiagnoses.length) statements.push(`Conditions on file: ${props.patient.majorDiagnoses.join(', ')}.`);
  if (props.patient.labs[0]) statements.push(`Latest lab: ${props.patient.labs[0].label} ${props.patient.labs[0].value} ${props.patient.labs[0].unit}.`);
  if (props.patient.majorAllergies.length) statements.push(`Allergies: ${props.patient.majorAllergies.join(', ')}.`);
  if (props.patient.riskIndicators.length) statements.push(props.patient.riskIndicators.join(' '));
  return statements;
});
</script>

<style scoped>
.brief { display: grid; gap: 12px; margin: 0; padding-left: 22px; }.brief li::marker { content: '✦  '; color: var(--color-warning); }.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 700; }.actions .actions__primary { border-color: var(--color-plum); background: var(--color-plum); color: white; }
</style>
