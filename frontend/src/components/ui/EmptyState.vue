<template>
  <section class="empty">
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
    <slot />
  </section>
</template>
<script setup lang="ts">defineProps<{ title: string; description: string }>();</script>
<style scoped>
.empty {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  background: var(--color-surface-raised);
  padding: var(--space-8) var(--space-6);
  text-align: center;
}
.empty h2 {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
}
.empty p {
  margin: var(--space-2) auto 0;
  max-width: 28rem;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
</style>
