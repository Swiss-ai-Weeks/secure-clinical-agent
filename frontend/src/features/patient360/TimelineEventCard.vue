<template>
  <article class="event" :class="{ highlighted }">
    <p v-if="highlighted" class="event__notice">Source highlighted from AI answer</p>
    <div class="event__meta"><time :datetime="event.date">{{ formattedDate }}</time><ProvenanceBadge :provenance="event.provenance" /></div>
    <h2>{{ event.title }}</h2><p>{{ event.summary }}</p>
    <ul><li v-for="tag in event.tags" :key="tag">{{ tag }}</li></ul>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { TimelineEvent } from '../../types/patient360';
import ProvenanceBadge from '../../components/ui/ProvenanceBadge.vue';
const props = defineProps<{ event: TimelineEvent; highlighted: boolean }>();
const formattedDate = computed(() => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${props.event.date}T12:00:00`)));
</script>

<style scoped>
.event { border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); padding: 20px; transition: border-color .2s, box-shadow .2s; }.event.highlighted { border: 4px solid var(--color-pink); box-shadow: 0 0 0 5px var(--color-pink-soft); }.event__notice { margin: 0 0 12px; color: var(--color-warning); font-weight: 800; }.event__meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: var(--color-muted); font-size: 14px; }.event h2 { margin: 10px 0 6px; font-size: 1.25rem; }.event p { margin: 0; }.event ul { display: flex; flex-wrap: wrap; gap: 7px; margin: 14px 0 0; padding: 0; list-style: none; }.event li { border-radius: 999px; background: #f4efe5; padding: 4px 9px; font-size: 14px; }
</style>
