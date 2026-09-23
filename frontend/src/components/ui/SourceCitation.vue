<template>
  <button class="citation" type="button" @click="$emit('select', sourceId)">
    <span>{{ typeLabel }}</span>{{ label }}
  </button>
</template>
<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  label: string;
  sourceId: string;
  sourceType?: string;
}>();
defineEmits<{ select: [sourceId: string] }>();

const TYPE_LABELS: Record<string, string> = {
  lab: 'Lab',
  medication: 'Med',
  note: 'Note',
  document: 'Document',
  condition: 'Condition',
  visit: 'Visit',
  identity: 'Identity'
};

const typeLabel = computed(() => TYPE_LABELS[props.sourceType ?? ''] ?? 'Source');
</script>
<style scoped>
.citation {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  padding: 0 12px;
  cursor: pointer;
  font-weight: 550;
  font-size: var(--text-sm);
  letter-spacing: -0.01em;
  transition: border-color 140ms ease, background 140ms ease;
}
.citation:hover {
  border-color: rgb(29 78 216 / 35%);
  background: var(--color-accent-soft);
}
.citation span {
  color: var(--color-accent-ink);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
</style>
