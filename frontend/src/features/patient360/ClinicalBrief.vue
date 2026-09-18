<template>
  <ClinicalCard title="✦ Clinical Brief" :ai="true">
    <ul class="brief"><li v-for="statement in briefStatements" :key="statement">{{ statement }}</li></ul>
    <article v-if="summary" class="summary" :class="{ refused: summary.refused }">
      <p>{{ summary.answer }}</p>
      <p v-if="summary.policy_reason" class="error">{{ summary.policy_reason }}</p>
    </article>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="actions">
      <button type="button" @click="viewSources">View sources</button>
      <button type="button" :disabled="loading" @click="regenerate">{{ loading ? 'Regenerating…' : 'Regenerate summary' }}</button>
      <button type="button" class="actions__primary" @click="ui.openAskPanel(patient.id)">Ask follow-up</button>
    </div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { AiAnswer, Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { useUiStore } from '../../stores/useUiStore';

const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();
const summary = ref<AiAnswer | null>(null);
const loading = ref(false);
const error = ref('');
const briefStatements = computed(() => {
  const statements = [`Record ${props.patient.id} · ${props.patient.fullName}.`];
  if (props.patient.majorDiagnoses.length) statements.push(`Conditions on file: ${props.patient.majorDiagnoses.join(', ')}.`);
  if (props.patient.labs[0]) statements.push(`Latest lab: ${props.patient.labs[0].label} ${props.patient.labs[0].value} ${props.patient.labs[0].unit}.`);
  if (props.patient.majorAllergies.length) statements.push(`Allergies: ${props.patient.majorAllergies.join(', ')}.`);
  if (props.patient.riskIndicators.length) statements.push(props.patient.riskIndicators.join(' '));
  return statements;
});

function viewSources() {
  const first = props.patient.labs[0]?.sourceId || props.patient.notes[0]?.id;
  if (first) ui.highlightSource(first);
  ui.openAskPanel(props.patient.id);
}

async function regenerate() {
  loading.value = true;
  error.value = '';
  try {
    summary.value = await apiClient.askPatient360({
      scope: 'patient',
      patientId: props.patient.id,
      question: 'Summarize the visible record since the last visit.'
    });
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not regenerate the summary';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.brief { display: grid; gap: 12px; margin: 0; padding-left: 22px; }
.brief li::marker { content: '✦  '; color: var(--color-warning); }
.summary { margin-top: 16px; border-radius: var(--radius-control); background: var(--color-yellow-soft); padding: 12px; }
.summary.refused { background: #fde8e8; }
.error { color: var(--color-danger); }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 700; }
.actions .actions__primary { border-color: var(--color-plum); background: var(--color-plum); color: white; }
</style>
