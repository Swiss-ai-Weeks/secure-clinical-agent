<template>
  <section class="timeline">
    <header><p>Patient 360</p><h1>Timeline</h1><span>{{ filteredEvents.length }} visible clinical events</span></header>
    <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
    <template v-else-if="!loading">
      <div class="timeline__search">
        <label for="timeline-search">Search timeline</label>
        <input id="timeline-search" v-model="query" type="search" placeholder="Title, summary, or date" />
      </div>
      <LargeTabs v-model="filter" label="Timeline filters" :items="filters" />
      <div v-if="filteredEvents.length" class="timeline__events">
        <TimelineEventCard v-for="event in filteredEvents" :key="event.id" :event="event" :highlighted="ui.highlightedSourceId === event.id" />
      </div>
      <p v-else class="empty">No timeline events match this filter.</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { filterTimeline } from '../../services/patientRecord';
import type { TimelineEvent } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import LargeTabs from '../../components/ui/LargeTabs.vue';
import ResourceNotFound from './ResourceNotFound.vue';
import TimelineEventCard from './TimelineEventCard.vue';

const route = useRoute();
const ui = useUiStore();
const events = ref<TimelineEvent[]>([]);
const missing = ref(false);
const filter = ref('all');
const query = ref('');
const filters = [
  { label: 'All', value: 'all' },
  { label: 'Visits', value: 'visit' },
  { label: 'Labs', value: 'lab' },
  { label: 'Medications', value: 'medication' },
  { label: 'Patient updates', value: 'patient-update' },
  { label: 'Documents', value: 'document' },
  { label: 'Notes', value: 'note' }
];
const filteredEvents = computed(() => {
  const matched = filterTimeline(events.value, { kind: filter.value, query: query.value });
  const highlight = ui.highlightedSourceId;
  if (!highlight || matched.some(event => event.id === highlight)) return matched;
  const ids = new Set(matched.map(event => event.id));
  ids.add(highlight);
  return events.value.filter(event => ids.has(event.id));
});

const { loading } = useLiveLoad(async () => {
  missing.value = false;
  try {
    events.value = await apiClient.getTimeline(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
  }
});
</script>

<style scoped>
.timeline { display: grid; gap: 20px; max-width: 980px; }
.timeline header span, .empty { color: var(--color-muted); }
.timeline__search { display: grid; gap: 10px; }
.timeline__search label { font-weight: 650; }
.timeline__search input { min-height: 44px; width: 100%; }
.timeline__events { display: grid; gap: 14px; }
</style>
