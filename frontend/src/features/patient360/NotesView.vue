<template>
  <section class="notes"><header><p>Patient 360</p><h1>Notes</h1></header><ClinicalCard v-for="note in patient?.notes" :key="note.id" :title="note.title" :eyebrow="`${note.author} · ${note.date}`"><AccessGate :field="note.category ?? 'clinicalNarrative'"><p class="note-text">{{ note.text }}</p></AccessGate><div class="actions"><button v-for="action in actions" :key="action" type="button" @click="ui.openAskPanel(patientId)">{{ action }}</button></div></ClinicalCard></section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { mockApi } from '../../services/mockApi';
import type { Patient } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGate from '../../components/access/AccessGate.vue';
const route = useRoute(); const ui = useUiStore(); const patient = ref<Patient | null>(null); const patientId = String(route.params.patientId);
const actions = ['✦ Summarize note', '✦ Convert to structured fields', '✦ Extract follow-up tasks', '✦ Draft consultation summary', '✦ Find previous related notes'];
onMounted(async () => { patient.value = await mockApi.getPatient(patientId); });
</script>

<style scoped>
.notes { display: grid; gap: 20px; max-width: 900px; }.notes header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.notes h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.note-text { line-height: 1.65; }.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-yellow-soft); padding: 0 10px; cursor: pointer; font-weight: 700; }
</style>
