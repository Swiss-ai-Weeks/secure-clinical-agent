<!--
  FRONTEND-ONLY DEMO SIMULATION — see src/data/accessControl.ts. Single
  source of truth for the "you can't reach this" copy and styling, used by
  AccessGate.vue (field-tier denials), RoleGate.vue (page-level denials),
  and the Ask Patient360 answer path (mockApi.askPatient360 /
  AskPatient360Panel.vue) — so every denial in the app reads identically
  instead of drifting into slightly different wording per surface.
-->
<template>
  <div class="access-denied" role="note">
    <strong>Restricted — {{ label }}<template v-if="tier"> ({{ tier }})</template></strong>
    <p>This falls outside what your current role, {{ access.currentRole.label }}, can access.</p>
  </div>
</template>

<script setup lang="ts">
import { useAccessControlStore } from '../../stores/useAccessControlStore';

defineProps<{ label: string; tier?: string }>();
const access = useAccessControlStore();
</script>

<style scoped>
.access-denied { border: 1px solid #f3c9c4; border-radius: var(--radius-control); background: #fff6f5; padding: 12px 14px; }
.access-denied strong { display: block; margin-bottom: 4px; color: var(--color-danger); font-size: 14px; }
.access-denied p { margin: 0; color: var(--color-muted); font-size: 14px; }
</style>
