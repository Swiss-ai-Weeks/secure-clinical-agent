<template>
  <div class="missing">
    <h2>Chart not available</h2>
    <p>This chart is not available on the current session. Unauthorized and unknown charts look the same.</p>
    <BreakGlassForm v-if="session.hasPanel('break_glass')" :patient-key="patientKey" />
    <RouterLink class="back" to="/patients">Back to patient directory</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router';
import { useSessionStore } from '../../stores/useSessionStore';
import BreakGlassForm from './BreakGlassForm.vue';

defineProps<{ patientKey: string }>();
const session = useSessionStore();
</script>

<style scoped>
.missing { display: grid; gap: 12px; max-width: 520px; color: var(--color-muted); }
.missing h2 { margin: 0; color: var(--color-ink); font-size: 1.5rem; }
.missing p { margin: 0; }
.back {
  width: max-content;
  color: var(--color-accent-ink);
  font-weight: 650;
  text-decoration: none;
}
.back:hover { text-decoration: underline; }
</style>
