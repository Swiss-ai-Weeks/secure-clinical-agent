<template>
  <main class="placeholder-view">
    <p class="placeholder-view__eyebrow">Patient360</p>
    <h1>{{ title }}</h1>
    <p>This view is being prepared for the clinical demo.</p>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

const titles: Record<string, string> = {
  home: 'Today',
  patients: 'Patients',
  'patient-overview': 'Patient overview',
  'patient-timeline': 'Timeline',
  'patient-labs': 'Laboratory results',
  'patient-medications': 'Medications',
  'patient-documents': 'Documents',
  'patient-notes': 'Notes',
  tasks: 'Tasks & follow-ups',
  cohort: 'Cohort insights',
  audit: 'Audit & privacy',
  portal: 'Patient portal'
};

const title = computed(() => titles[String(route.name)] ?? 'Patient360');
</script>

<style scoped>
.placeholder-view { padding: 48px; }
.placeholder-view__eyebrow { color: var(--color-muted); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
</style>
