<template>
  <section class="empty"><h2>{{ title }}</h2><p>{{ description }}</p><slot /></section>
</template>
<script setup lang="ts">defineProps<{ title: string; description: string }>();</script>
<style scoped>
.empty { border: 2px dashed var(--color-line); border-radius: var(--radius-card); padding: 32px; text-align: center; }.empty h2 { margin: 0; }.empty p { color: var(--color-muted); }
</style>
