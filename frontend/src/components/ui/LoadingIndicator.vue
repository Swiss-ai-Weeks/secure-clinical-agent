<template>
  <div class="loading" role="status">
    <Loader2 class="loading__icon" :size="24" aria-hidden="true" />
    <span>{{ message }}</span>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from 'lucide-vue-next';

withDefaults(defineProps<{ message?: string }>(), { message: 'Loading…' });
</script>

<style scoped>
.loading {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: var(--space-3);
  color: var(--color-muted);
  padding: var(--space-6);
  font-size: var(--text-sm);
  font-weight: 600;
}
.loading__icon {
  animation: spin 0.8s linear infinite;
  color: var(--color-accent);
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
