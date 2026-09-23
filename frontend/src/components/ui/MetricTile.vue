<template>
  <article class="metric">
    <p>{{ label }}</p>
    <strong>{{ value }}</strong>
    <span v-if="detail">{{ detail }}</span>
  </article>
</template>

<script setup lang="ts">
defineProps<{ label: string; value: string; detail?: string }>();
</script>

<style scoped>
.metric {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface-raised);
  padding: var(--space-4);
}
p, span {
  display: block;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
p {
  margin: 0 0 var(--space-1);
  font-weight: 550;
  letter-spacing: -0.01em;
}
strong {
  display: block;
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  font-variant-numeric: tabular-nums;
}
span { margin-top: var(--space-1); }
</style>
