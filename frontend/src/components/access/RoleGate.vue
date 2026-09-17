<!--
  FRONTEND-ONLY DEMO SIMULATION — see src/data/accessControl.ts. Same idea as
  AccessGate.vue, but for page-level access decided by role identity rather
  than a field's tier (e.g. "only Compliance officers open this page", which
  a tier comparison alone can't express since other roles may already have
  full T3 field reach). A real backend would refuse the route/API entirely
  for a session without the right role, rather than the client deciding.
-->
<template>
  <template v-if="allowed"><slot /></template>
  <AccessDenialCard v-else :label="label" />
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import type { AccessRole } from '../../types/patient360';
import { useAccessControlStore } from '../../stores/useAccessControlStore';
import AccessDenialCard from './AccessDenialCard.vue';

const props = defineProps<{ pageKey: string; label: string; allowedRoles: AccessRole[] }>();
const access = useAccessControlStore();

const allowed = computed(() => props.allowedRoles.includes(access.role));

watch(
  [() => access.role, () => props.pageKey],
  () => access.logPageAccess(props.pageKey, props.label, allowed.value),
  { immediate: true }
);
</script>
