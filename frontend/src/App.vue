<template>
  <AppShell>
    <Suspense>
      <RouterView />
    </Suspense>
  </AppShell>
</template>

<script setup lang="ts">
import AppShell from './components/layout/AppShell.vue';
</script>
