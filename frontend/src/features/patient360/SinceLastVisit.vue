<template>
  <ClinicalCard title="Since your last consultation">
    <div v-if="changes.length" class="changes">
      <button v-for="change in changes" :key="change.label" type="button" @click="ui.highlightSource(change.target)">
        <span>{{ change.label }}</span>
        <span aria-hidden="true">→</span>
      </button>
    </div>
    <p v-else class="empty">No visible changes to highlight yet.</p>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { useUiStore } from '../../stores/useUiStore';
const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();
const changes = computed(() => {
  const items = [
    { label: `${props.patient.labs.length} lab result${props.patient.labs.length === 1 ? '' : 's'}`, target: props.patient.labs[0]?.id ?? 'labs', count: props.patient.labs.length },
    { label: `${props.patient.medications.length} medication${props.patient.medications.length === 1 ? '' : 's'}`, target: 'medications', count: props.patient.medications.length },
    { label: `${props.patient.majorAllergies.length} allerg${props.patient.majorAllergies.length === 1 ? 'y' : 'ies'}`, target: 'allergies', count: props.patient.majorAllergies.length }
  ];
  return items.filter(item => item.count > 0);
});
</script>

<style scoped>
.changes { display: grid; gap: 8px; }
.changes button { display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 10px 14px; text-align: left; cursor: pointer; }
.changes button:hover { border-color: rgb(29 78 216 / 28%); background: var(--color-accent-soft); }
.empty { margin: 0; color: var(--color-muted); }
</style>
