<template>
  <aside v-if="ui.askPanelOpen" class="panel" aria-label="Ask Patient360">
    <header class="panel__header">
      <div>
        <p>✦ Ask Patient360</p>
        <h2>{{ ui.selectedPatientId ? 'Patient context active' : 'Clinic context' }}</h2>
      </div>
      <button type="button" aria-label="Close" @click="ui.closeAskPanel">Close</button>
    </header>
    <form class="question" @submit.prevent="ask">
      <label for="ask-input">Question</label>
      <textarea id="ask-input" v-model="question" rows="3" />
      <button type="submit" :disabled="loading">Ask with sources</button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
    <ol v-if="loading || steps.length" class="steps"><li v-for="step in (loading ? loadingSteps : steps)" :key="step">{{ step }}</li></ol>
    <article v-if="answer" class="answer" :class="{ refused: answer.refused }">
      <h3>{{ answer.refused ? 'Refused' : '✦ Answer' }}</h3>
      <p>{{ answer.answer }}</p>
      <p v-if="answer.policy_reason" class="reason">{{ answer.policy_reason }}</p>
      <div class="citations">
        <button v-for="citation in answer.citations" :key="citation.id" type="button" @click="ui.highlightSource(citation.sourceId)">{{ citation.label }}</button>
      </div>
    </article>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { AiAnswer } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';

const ui = useUiStore();
const question = ref('What changed with this patient since the last visit?');
const loading = ref(false);
const error = ref('');
const answer = ref<AiAnswer | null>(null);
const steps = ref<string[]>([]);
const loadingSteps = ['Searching authorized records...', 'Reading visible notes...', 'Preparing cited summary...'];

async function ask() {
  loading.value = true;
  error.value = '';
  answer.value = null;
  steps.value = [];
  try {
    answer.value = await apiClient.askPatient360({
      scope: ui.selectedPatientId ? 'patient' : 'clinic',
      patientId: ui.selectedPatientId,
      question: question.value
    });
    steps.value = answer.value.retrievalSteps;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Ask failed';
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.panel { position: fixed; z-index: 10; top: 0; right: 0; display: flex; flex-direction: column; gap: 20px; width: min(440px, 100vw); height: 100dvh; overflow-y: auto; border-left: 1px solid var(--color-line); background: var(--color-surface); padding: 24px; box-shadow: -16px 0 40px rgb(40 35 42 / 12%); }
.panel__header { display: flex; justify-content: space-between; gap: 16px; }
.panel__header p { margin: 0 0 4px; color: var(--color-warning); font-weight: 800; }
.panel h2, .panel h3 { margin: 0; }
.panel button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; }
.question { display: grid; gap: 8px; }
.question textarea { width: 100%; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 12px; resize: vertical; }
.question button { background: var(--color-plum); color: white; }
.steps, .answer { border-radius: var(--radius-control); background: var(--color-yellow-soft); padding: 16px; }
.answer.refused { background: #fde8e8; }
.answer p { line-height: 1.6; }
.reason, .error { color: var(--color-danger); }
.citations { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
