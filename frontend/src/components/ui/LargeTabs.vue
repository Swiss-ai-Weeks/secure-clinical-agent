<template>
  <div class="tabs" role="tablist" :aria-label="label">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      role="tab"
      :aria-selected="modelValue === item.value"
      :class="{ active: modelValue === item.value }"
      @click="$emit('update:modelValue', item.value)"
    >{{ item.label }}</button>
  </div>
</template>
<script setup lang="ts">
defineProps<{ modelValue: string; items: Array<{ label: string; value: string }>; label: string }>();
defineEmits<{ 'update:modelValue': [value: string] }>();
</script>
<style scoped>
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.tabs button {
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  color: var(--color-muted-strong);
  padding: 0 14px;
  font-size: var(--text-sm);
  font-weight: 550;
  letter-spacing: -0.01em;
  cursor: pointer;
  transition: background 140ms ease, border-color 140ms ease, color 140ms ease;
}
.tabs button.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
}
</style>
