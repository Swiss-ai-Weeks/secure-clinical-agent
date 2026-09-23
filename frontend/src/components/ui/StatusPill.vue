<template><span class="pill" :class="tone">{{ label }}</span></template>
<script setup lang="ts">
withDefaults(defineProps<{ label: string; tone?: 'neutral' | 'warning' | 'danger' | 'success' }>(), { tone: 'neutral' });
</script>
<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  height: 24px;
  min-height: 24px;
  max-height: 24px;
  border-radius: var(--radius-pill);
  padding: 0 10px;
  background: var(--color-surface-muted);
  color: var(--color-muted-strong);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 1;
  white-space: nowrap;
  vertical-align: middle;
}
.warning { background: var(--color-warning-soft); color: var(--color-warning); }
.danger { background: var(--color-danger-soft); color: var(--color-danger); }
.success { background: var(--color-success-soft); color: var(--color-success); }
</style>
