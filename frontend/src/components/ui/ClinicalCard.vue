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
.card { background: var(--color-surface); border: 1px solid var(--color-line); border-radius: var(--radius-card); padding: 22px; box-shadow: var(--shadow-soft); }
.card.ai { background: var(--color-yellow-soft); }
.card__header { margin-bottom: 16px; }
.card__eyebrow { margin: 0 0 4px; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
h2 { margin: 0; font-size: clamp(1.35rem, 2vw, 1.8rem); }
</style>
