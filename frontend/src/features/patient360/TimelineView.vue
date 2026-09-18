<template>
  <section class="timeline">
    <header><p>Patient 360</p><h1>Timeline</h1><span>{{ events.length }} visible clinical events</span></header>
    <p v-if="missing">Resource not found</p>
    <template v-else>
      <LargeTabs v-model="filter" label="Timeline filters" :items="filters" />
      <div class="timeline__events"><TimelineEventCard v-for="event in filteredEvents" :key="event.id" :event="event" :highlighted="ui.highlightedSourceId === event.id" /></div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { TimelineEvent } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import LargeTabs from '../../components/ui/LargeTabs.vue';
import TimelineEventCard from './TimelineEventCard.vue';

const route = useRoute();
const ui = useUiStore();
const events = ref<TimelineEvent[]>([]);
const missing = ref(false);
const filter = ref('all');
const filters = [{ label: 'All', value: 'all' }, { label: 'Visits', value: 'visit' }, { label: 'Labs', value: 'lab' }, { label: 'Medications', value: 'medication' }];
const filteredEvents = computed(() => filter.value === 'all' ? events.value : events.value.filter(event => event.kind === filter.value));

useLiveLoad(async () => {
  missing.value = false;
  events.value = [];
  try {
    events.value = await apiClient.getTimeline(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
  }
});
</script>

<style scoped>
.timeline { display: grid; gap: 20px; max-width: 980px; }.timeline header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.timeline h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.timeline header span { color: var(--color-muted); }.timeline__events { display: grid; gap: 14px; }
</style>
