<template>
  <span class="badge" :class="provenance">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Provenance } from '../../types/patient360';

const props = defineProps<{ provenance: Provenance }>();
const label = computed(() => {
  if (props.provenance === 'ai-generated') return 'AI generated';
  if (props.provenance === 'patient-reported') return 'Patient reported';
  return 'Clinical record';
});
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 24px;
  min-height: 24px;
  border-radius: var(--radius-pill);
  padding: 0 10px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}
.clinical { background: var(--color-surface-muted); color: var(--color-muted-strong); }
.patient-reported { background: var(--color-accent-soft); color: var(--color-accent-ink); }
.ai-generated { background: var(--color-accent-soft); color: var(--color-accent-ink); }
</style>
