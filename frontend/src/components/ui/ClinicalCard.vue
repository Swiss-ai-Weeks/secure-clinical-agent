<template>
  <section class="card" :class="{ ai }" :aria-labelledby="titleId">
    <header class="card__header">
      <p v-if="eyebrow" class="card__eyebrow">{{ eyebrow }}</p>
      <h2 :id="titleId">{{ title }}</h2>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
const props = defineProps<{ title: string; eyebrow?: string; ai?: boolean }>();
const titleId = `card-${props.title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
</script>

<style scoped>
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  padding: var(--space-6);
  box-shadow: var(--shadow-soft);
}

.card.ai {
  background:
    linear-gradient(180deg, var(--color-accent-soft) 0%, var(--color-surface) 42%);
  border-color: rgb(29 78 216 / 14%);
}

.card__header {
  margin-bottom: var(--space-5);
}

.card__eyebrow {
  margin: 0 0 var(--space-1);
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
  line-height: var(--leading-tight);
}

h2 {
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  line-height: var(--leading-tight);
}
</style>
