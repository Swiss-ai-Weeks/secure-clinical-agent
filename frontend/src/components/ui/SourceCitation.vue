<template><button class="citation" type="button" @click="$emit('select', sourceId)"><span>Source</span>{{ label }}</button></template>
<script setup lang="ts">
defineProps<{ label: string; sourceId: string }>();
defineEmits<{ select: [sourceId: string] }>();
</script>
<style scoped>
.citation { display: inline-flex; align-items: center; gap: 8px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 700; }.citation span { color: var(--color-muted); font-size: 14px; }
</style>
