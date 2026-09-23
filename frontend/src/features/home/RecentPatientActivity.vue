<template>
  <ClinicalCard title="Recent patient activity">
    <div class="activity">
      <article v-for="event in events" :key="event.id">
        <time>{{ event.date }}</time>
        <div>
          <h3>{{ event.title }}</h3>
          <p v-if="event.actor">{{ event.actor }}</p>
          <p v-if="event.summary">{{ event.summary }}</p>
        </div>
      </article>
      <p v-if="!events.length" class="empty">No recent activity for this sign-in.</p>
    </div>
  </ClinicalCard>
</template>
<script setup lang="ts">
import type { TimelineEvent } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
defineProps<{ events: TimelineEvent[] }>();
</script>
<style scoped>
.activity { display: grid; gap: 0; }
.activity article {
  display: grid;
  grid-template-columns: 148px 1fr;
  gap: var(--space-4);
  align-items: start;
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
}
.activity article:first-child { padding-top: 0; }
.activity article:last-child { border-bottom: 0; padding-bottom: 0; }
.activity time {
  color: var(--color-muted);
  font-size: var(--text-sm);
  font-weight: 550;
  font-variant-numeric: tabular-nums;
  line-height: var(--leading-snug);
}
.activity h3 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: var(--leading-snug);
}
.activity p, .empty {
  margin: var(--space-1) 0 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
@media (max-width: 580px) {
  .activity article { grid-template-columns: 1fr; gap: var(--space-1); }
}
</style>
