<template>
  <ClinicalCard title="Needs attention">
    <div class="attention">
      <article v-for="item in items" :key="item.id">
        <div class="attention__body">
          <StatusPill
            :label="item.severity === 'review' ? 'Review' : item.severity === 'warning' ? 'Warning' : 'Urgent'"
            :tone="item.severity === 'urgent' ? 'danger' : item.severity === 'warning' ? 'warning' : 'neutral'"
          />
          <h3>{{ item.title }}</h3>
          <p>{{ item.detail }}</p>
        </div>
        <ProvenanceBadge :provenance="item.provenance" />
      </article>
      <p v-if="!items.length" class="empty">Nothing needs attention right now.</p>
    </div>
  </ClinicalCard>
</template>
<script setup lang="ts">
import type { AttentionItem } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import ProvenanceBadge from '../../components/ui/ProvenanceBadge.vue';
defineProps<{ items: AttentionItem[] }>();
</script>
<style scoped>
.attention { display: grid; gap: 0; }
.attention article {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
}
.attention article:first-child { padding-top: 0; }
.attention article:last-child { border-bottom: 0; padding-bottom: 0; }
.attention__body {
  display: grid;
  gap: var(--space-2);
  min-width: 0;
}
.attention h3 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: var(--leading-snug);
}
.attention p, .empty {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
</style>
