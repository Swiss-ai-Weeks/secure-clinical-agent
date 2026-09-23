<template>
  <article class="event" :class="{ highlighted }">
    <p v-if="highlighted" class="event__notice">Source highlighted from AI answer</p>
    <div class="event__meta"><time :datetime="event.date || undefined">{{ formattedDate }}</time><ProvenanceBadge :provenance="event.provenance" /></div>
    <h2>{{ event.title }}</h2><p>{{ event.summary }}</p>
    <ul><li v-for="tag in event.tags" :key="tag">{{ tag }}</li></ul>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { TimelineEvent } from '../../types/patient360';
import ProvenanceBadge from '../../components/ui/ProvenanceBadge.vue';
import { formatLabDate } from '../../services/patientRecord';
const props = defineProps<{ event: TimelineEvent; highlighted: boolean }>();
const formattedDate = computed(() => formatLabDate(props.event.date) || 'Date not recorded');
</script>

<style scoped>
.event {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  padding: var(--space-5);
  box-shadow: var(--shadow-soft);
  transition: border-color .2s, box-shadow .2s;
}
.event.highlighted {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}
.event__notice {
  margin: 0 0 12px;
  color: var(--color-accent-ink);
  font-weight: 700;
  font-size: var(--text-sm);
}
.event__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.event h2 { margin: 10px 0 6px; font-size: 1.2rem; font-weight: 700; letter-spacing: -0.01em; }
.event p { margin: 0; color: var(--color-muted); }
.event ul { display: flex; flex-wrap: wrap; gap: 7px; margin: 14px 0 0; padding: 0; list-style: none; }
.event li {
  border-radius: var(--radius-pill);
  background: var(--color-surface-muted);
  padding: 4px 9px;
  font-size: var(--text-sm);
}
</style>
