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
.metric { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 16px; }
p, span { display: block; color: var(--color-muted); font-size: 14px; } p { margin: 0 0 4px; } strong { display: block; font-size: 1.25rem; } span { margin-top: 4px; }
</style>
