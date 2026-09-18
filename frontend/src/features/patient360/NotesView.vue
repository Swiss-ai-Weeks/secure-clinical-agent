<template>
  <section class="notes">
    <header>
      <p>Patient 360</p>
      <h1>Notes</h1>
    </header>
    <p v-if="error" class="empty">{{ error }}</p>
    <p v-else-if="!notes.length" class="empty">No published notes are visible for this record.</p>
    <ClinicalCard v-for="note in notes" :key="note.id" :title="note.title" :eyebrow="`${note.author} · ${note.date}`">
      <p class="note-text">{{ note.text }}</p>
      <div class="actions">
        <button type="button" @click="ui.openAskPanel(patientId)">✦ Summarize note</button>
      </div>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { ClinicalNote } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';

const route = useRoute();
const ui = useUiStore();
const notes = ref<ClinicalNote[]>([]);
const error = ref('');
const patientId = String(route.params.patientId);

onMounted(async () => {
  try {
    const patient = await apiClient.getPatient(patientId);
    notes.value = patient.notes;
  } catch (err) {
    error.value = err instanceof ApiError && err.notFound ? 'No published notes are visible for this record.' : (err as Error).message;
  }
});
</script>

<style scoped>
.notes { display: grid; gap: 20px; max-width: 900px; }
.notes header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.notes h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }
.note-text { line-height: 1.65; }
.empty { color: var(--color-muted); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-yellow-soft); padding: 0 10px; cursor: pointer; font-weight: 700; }
</style>
