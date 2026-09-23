<template>
  <ClinicalCard title="Today's summary">
    <ul v-if="briefing.length">
      <li v-for="item in briefing" :key="item.id">
        <RouterLink v-if="item.patientId" :to="patientPath(item.patientId)">{{ item.text }}</RouterLink>
        <span v-else>{{ item.text }}</span>
      </li>
    </ul>
    <p v-else class="empty">No summary items yet.</p>
  </ClinicalCard>
</template>
<script setup lang="ts">
import { RouterLink } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
defineProps<{ briefing: Array<{ id: string; text: string; patientId?: string }> }>();
function patientPath(patientId: string) {
  return `/patients/${patientId}/overview`;
}
</script>
<style scoped>
ul {
  display: grid;
  gap: var(--space-3);
  margin: 0;
  padding-left: 1.1rem;
}
li {
  line-height: var(--leading-snug);
}
li::marker { color: var(--color-accent); }
a {
  color: var(--color-accent-ink);
  font-weight: 550;
  text-decoration: none;
}
a:hover { text-decoration: underline; }
.empty { margin: 0; color: var(--color-muted); font-size: var(--text-sm); }
</style>
