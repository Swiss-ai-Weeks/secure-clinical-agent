<template>
  <ClinicalCard title="Clinical brief" :ai="true">
    <ul class="brief"><li v-for="statement in briefStatements" :key="statement">{{ statement }}</li></ul>
    <article v-if="summary" class="summary" :class="{ refused: summary.refused }">
      <template v-for="(block, index) in summaryBlocks" :key="index">
        <ul v-if="block.type === 'list'" class="summary__list">
          <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
            <template v-for="(part, partIndex) in item" :key="partIndex">
              <strong v-if="part.bold">{{ part.text }}</strong>
              <template v-else>{{ part.text }}</template>
            </template>
          </li>
        </ul>
        <p v-else>
          <template v-for="(part, partIndex) in block.parts" :key="partIndex">
            <strong v-if="part.bold">{{ part.text }}</strong>
            <template v-else>{{ part.text }}</template>
          </template>
        </p>
      </template>
      <p v-if="reasonLabel" class="error">{{ reasonLabel }}</p>
    </article>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-if="canAsk" class="actions">
      <button type="button" @click="viewSources">Open Ask</button>
      <button type="button" :disabled="loading" @click="regenerate">{{ loading ? 'Regenerating…' : 'Regenerate summary' }}</button>
      <button type="button" class="actions__primary" @click="ui.openAskPanel(patient.id, 'What should I follow up on for this patient?')">Ask follow-up</button>
    </div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import type { AiAnswer, Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { answerBlocks, policyReasonLabel } from '../../services/askCitations';
import { briefStatements as statementsFor } from '../../services/patientRecord';
import { ApiError } from '../../services/http';
import { canLaunchAsk } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUiStore } from '../../stores/useUiStore';

const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();
const session = useSessionStore();
const summary = ref<AiAnswer | null>(null);
const loading = ref(false);
const error = ref('');
const briefStatements = computed(() => statementsFor(props.patient));
const summaryBlocks = computed(() => (summary.value ? answerBlocks(summary.value.answer) : []));
const reasonLabel = computed(() => policyReasonLabel(summary.value?.policy_reason));
const canAsk = computed(() => canLaunchAsk({
  panels: session.panels,
  workspace: session.workspace,
  patientId: props.patient.id,
  onDuty: session.me?.session.on_duty
}));

function viewSources() {
  const first = props.patient.labs[0]?.sourceId || props.patient.notes[0]?.id;
  if (first) ui.highlightSource(first);
  ui.openAskPanel(props.patient.id, 'What changed with this patient since the last visit?');
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
.brief { display: grid; gap: 12px; margin: 0; padding-left: 1.15rem; }
.brief li::marker { color: var(--color-accent); }
.summary { display: grid; gap: 10px; margin-top: 16px; border-radius: var(--radius-control); background: var(--color-surface); border: 1px solid var(--color-line); padding: 12px; }
.summary p { margin: 0; line-height: 1.65; }
.summary__list { display: grid; gap: 8px; margin: 0; padding-left: 1.15rem; line-height: 1.55; }
.summary.refused { background: var(--color-danger-soft); border-color: rgb(180 35 24 / 18%); }
.error { color: var(--color-danger); }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 650; }
.actions button:disabled { opacity: 0.6; cursor: wait; }
.actions .actions__primary { border-color: var(--color-accent); background: var(--color-accent); color: white; }
</style>
