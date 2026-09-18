<template>
  <section v-if="dashboard" class="home">
    <header>
      <p>{{ session.me?.role ?? 'Clinical workspace' }} · {{ dashboard.greeting }}</p>
      <h1>Today</h1>
      <span>Start with the patients visible to this persona.</span>
    </header>
    <div class="home__grid">
      <TodaysPatients :patients="dashboard.todaysPatients" />
      <MorningBriefing :briefing="dashboard.briefing" />
      <NeedsAttention :items="dashboard.attention" />
      <RecentPatientActivity :events="dashboard.recentActivity" />
    </div>
  </section>
  <p v-else class="loading">Loading today's clinical workspace…</p>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import type { HomeDashboard } from '../../types/patient360';
import { useSessionStore } from '../../stores/useSessionStore';
import TodaysPatients from './TodaysPatients.vue';
import MorningBriefing from './MorningBriefing.vue';
import NeedsAttention from './NeedsAttention.vue';
import RecentPatientActivity from './RecentPatientActivity.vue';

const session = useSessionStore();
const dashboard = ref<HomeDashboard | null>(null);

useLiveLoad(async () => {
  dashboard.value = await apiClient.getHomeDashboard();
});
</script>

<style scoped>
.home { display: grid; gap: 22px; }.home header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.home h1 { margin: 4px 0; font-size: clamp(2.2rem, 5vw, 3.5rem); }.home header span, .loading { color: var(--color-muted); }.home__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }.home__grid > :first-child, .home__grid > :last-child { grid-column: 1 / -1; } @media (max-width: 840px) { .home__grid { grid-template-columns: 1fr; }.home__grid > :first-child, .home__grid > :last-child { grid-column: auto; } }
</style>
