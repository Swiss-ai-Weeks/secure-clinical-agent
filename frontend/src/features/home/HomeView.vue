<template>
  <section v-if="session.workspace === 'family'"><PatientPortalView /></section>
  <KitchenHomeView v-else-if="session.workspace === 'kitchen'" />
  <CohortInsightsView v-else-if="session.workspace === 'research'" />
  <AuditPrivacyView v-else-if="session.workspace === 'audit'" />
  <section v-else-if="dashboard" class="home">
    <header>
      <p>Home</p>
      <h1>Today</h1>
      <span>{{ dashboard.greeting }}</span>
      <span>Start with the patients on your roster.</span>
    </header>
    <div class="home__grid">
      <TodaysPatients :patients="dashboard.todaysPatients" />
      <MorningBriefing :briefing="dashboard.briefing" />
      <NeedsAttention :items="dashboard.attention" />
      <RecentPatientActivity :events="dashboard.recentActivity" />
    </div>
  </section>
  <section v-else class="home">
    <header>
      <p>Home</p>
      <h1>Today</h1>
      <span>{{ session.me?.display ?? 'Clinical workspace' }}</span>
      <span>No patients on your roster yet.</span>
    </header>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import type { HomeDashboard } from '../../types/patient360';
import { useSessionStore } from '../../stores/useSessionStore';
import AuditPrivacyView from '../clinic/AuditPrivacyView.vue';
import CohortInsightsView from '../clinic/CohortInsightsView.vue';
import KitchenHomeView from '../clinic/KitchenHomeView.vue';
import PatientPortalView from '../portal/PatientPortalView.vue';
import TodaysPatients from './TodaysPatients.vue';
import MorningBriefing from './MorningBriefing.vue';
import NeedsAttention from './NeedsAttention.vue';
import RecentPatientActivity from './RecentPatientActivity.vue';

const session = useSessionStore();
const dashboard = ref<HomeDashboard | null>(null);

useLiveLoad(async () => {
  if (session.workspace !== 'clinical') {
    dashboard.value = null;
    return;
  }
  dashboard.value = await apiClient.getHomeDashboard();
});

</script>

<style scoped>
.home {
  display: grid;
  gap: var(--space-6);
  max-width: 1120px;
}
.home__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-5);
}
.home__grid > :first-child,
.home__grid > :last-child {
  grid-column: 1 / -1;
}
@media (max-width: 840px) {
  .home__grid { grid-template-columns: 1fr; }
  .home__grid > :first-child,
  .home__grid > :last-child { grid-column: auto; }
}
</style>
