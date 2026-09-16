<template><span class="pill" :class="tone">{{ label }}</span></template>
<script setup lang="ts">
withDefaults(defineProps<{ label: string; tone?: 'neutral' | 'warning' | 'danger' | 'success' }>(), { tone: 'neutral' });
</script>
<style scoped>
.pill { display: inline-flex; align-items: center; min-height: 30px; border-radius: 999px; padding: 0 10px; background: #f4efe5; font-size: 14px; font-weight: 750; }
.warning { background: #fff0c8; color: var(--color-warning); }.danger { background: #fde8e7; color: var(--color-danger); }.success { background: #e5f5e8; color: var(--color-success); }
</style>
