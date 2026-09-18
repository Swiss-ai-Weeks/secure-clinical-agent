<template>
  <ClinicalCard title="Since your last consultation">
    <div class="changes"><button v-for="change in changes" :key="change.label" type="button" @click="ui.highlightSource(change.target)"><span>{{ change.label }}</span><span aria-hidden="true">→</span></button></div>
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
    { label: `${props.patient.labs.length} laboratory row(s)`, target: props.patient.labs[0]?.id ?? 'labs' },
    { label: `${props.patient.medications.length} medication row(s)`, target: 'medications' },
    { label: `${props.patient.majorAllergies.length} allergy row(s)`, target: 'allergies' }
  ];
  return items;
});
</script>

<style scoped>
.changes { display: grid; gap: 8px; }.changes button { display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 10px 14px; text-align: left; cursor: pointer; }.changes button:hover { border-color: var(--color-pink); background: var(--color-pink-soft); }
</style>
