<template>
  <div class="tabs" role="tablist" :aria-label="label">
    <button v-for="item in items" :key="item.value" type="button" role="tab" :aria-selected="modelValue === item.value" :class="{ active: modelValue === item.value }" @click="$emit('update:modelValue', item.value)">{{ item.label }}</button>
  </div>
</template>
<script setup lang="ts">
defineProps<{ modelValue: string; items: Array<{ label: string; value: string }>; label: string }>();
defineEmits<{ 'update:modelValue': [value: string] }>();
</script>
<style scoped>
.tabs { display: flex; flex-wrap: wrap; gap: 8px; }.tabs button { border: 1px solid var(--color-line); border-radius: 999px; background: var(--color-surface); padding: 0 16px; cursor: pointer; }.tabs button.active { background: var(--color-plum); border-color: var(--color-plum); color: white; }
</style>
