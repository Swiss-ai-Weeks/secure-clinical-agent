<template>
  <span class="badge" :class="provenance">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Provenance } from '../../types/patient360';

const props = defineProps<{ provenance: Provenance }>();
const label = computed(() => {
  if (props.provenance === 'ai-generated') return '✦ AI generated';
  if (props.provenance === 'patient-reported') return 'Patient reported';
  return 'Clinical record';
});
</script>

<style scoped>
.badge { display: inline-flex; align-items: center; min-height: 32px; border-radius: 999px; padding: 0 12px; font-size: 14px; font-weight: 750; }
.clinical { background: #f4efe5; }
.patient-reported { background: var(--color-pink-soft); }
.ai-generated { background: var(--color-yellow); }
</style>
