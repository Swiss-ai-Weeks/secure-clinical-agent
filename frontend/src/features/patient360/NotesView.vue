<template>
  <section class="notes">
    <header>
      <p>Patient 360</p>
      <h1>Notes</h1>
    </header>
    <ResourceNotFound v-if="missing" :patient-key="patientId" />
    <template v-else-if="!loading">
    <p v-if="error" class="empty">{{ error }}</p>
    <p v-else-if="!notes.length" class="empty">No published notes are visible for this record.</p>
    <div
      v-for="note in notes"
      :id="`source-${note.id}`"
      :key="note.id"
      class="note"
      :class="{ highlighted: ui.highlightedSourceId === note.id }"
    >
      <ClinicalCard :title="note.title" :eyebrow="`${note.author} · ${note.date}`">
        <p class="note-text">{{ note.text }}</p>
        <div v-if="canAsk || note.storageKey" class="actions">
          <button v-if="canAsk" type="button" @click="ui.openAskPanel(patientId, 'Summarize the latest note')">Ask about this note</button>
          <button v-if="note.storageKey" type="button" :disabled="removing === note.storageKey" @click="remove(note.storageKey)">
            {{ removing === note.storageKey ? 'Deleting…' : 'Delete' }}
          </button>
        </div>
      </ClinicalCard>
    </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { canLaunchAsk } from '../../services/workspace';
import type { ClinicalNote } from '../../types/patient360';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUiStore } from '../../stores/useUiStore';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import ResourceNotFound from './ResourceNotFound.vue';

const route = useRoute();
const ui = useUiStore();
const session = useSessionStore();
const notes = ref<ClinicalNote[]>([]);
const removing = ref('');
const error = ref('');
const missing = ref(false);
const patientId = computed(() => String(route.params.patientId));
const canAsk = computed(() => canLaunchAsk({
  panels: session.panels,
  workspace: session.workspace,
  patientId: patientId.value,
  onDuty: session.me?.session.on_duty
}));

async function loadNotes() {
  error.value = '';
  missing.value = false;
  try {
    notes.value = (await apiClient.getPatient(String(route.params.patientId))).notes;
  } catch (err) {
    missing.value = err instanceof ApiError && err.notFound;
    error.value = missing.value ? '' : (err as Error).message;
  }
}

const { loading } = useLiveLoad(loadNotes);

async function remove(storageKey: string) {
  removing.value = storageKey;
  error.value = '';
  try {
    await apiClient.deleteDocument(patientId.value, storageKey);
    await loadNotes();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Delete failed';
  } finally {
    removing.value = '';
  }
}

watch(
  () => [ui.highlightedSourceId, loading.value, notes.value.length] as const,
  async ([id, busy]) => {
    if (!id || busy) return;
    await nextTick();
    document.getElementById(`source-${id}`)?.scrollIntoView({ block: 'center' });
  }
);
</script>

<style scoped>
.notes {
  display: grid;
  gap: var(--space-5);
  max-width: 900px;
}
.note.highlighted :deep(.card) {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}
.note-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.65;
  color: var(--color-ink);
}
.empty { color: var(--color-muted); margin: 0; }
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-5);
}
.actions button {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-ink);
  padding: 0 var(--space-3);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
}
</style>
