<!--
  FRONTEND-ONLY DEMO SIMULATION of a role/tier access check — see
  src/data/accessControl.ts for the caveat. This component decides,
  client-side, whether to render its slot content, a tier badge, or a
  denial state, based on the current demo role.

  In a real system, a backend Policy Decision Point (PDP) would already
  have filtered `field` out of the API response for a role that can't see
  it — this component would then simply render what it was given, with no
  allow/deny branch of its own. Keep this component's boundary in mind if
  wiring it to a real backend: `checkAccess` is the one call to swap out.
-->
<template>
  <div class="access-gate">
    <template v-if="decision.allowed">
      <span class="access-gate__badge" :class="decision.tier.toLowerCase()">{{ decision.tier }}</span>
      <div class="access-gate__content"><slot /></div>
    </template>
    <AccessDenialCard v-else :label="decision.label" :tier="decision.tier" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { decideAccess } from '../../data/accessControl';
import { useAccessControlStore } from '../../stores/useAccessControlStore';
import AccessDenialCard from './AccessDenialCard.vue';

const props = defineProps<{ field: string }>();
const access = useAccessControlStore();

// Pure decision for rendering — no side effects, so the template can read it
// freely without re-logging on every unrelated re-render. Reads access.role
// directly so it recomputes when the role changes.
const decision = computed(() => decideAccess(access.role, props.field));

// Logging is the side effect, and runs only when role or field actually
// changes (including once on mount) — not on arbitrary re-renders.
watch(
  [() => access.role, () => props.field],
  () => access.checkAccess(props.field),
  { immediate: true }
);
</script>

<style scoped>
.access-gate { display: inline-flex; flex-direction: column; gap: 6px; width: 100%; }
.access-gate__badge { align-self: flex-start; display: inline-flex; align-items: center; height: 20px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: 0.02em; }
.access-gate__badge.t0 { background: #eef2ff; color: #3b4a9c; }
.access-gate__badge.t1 { background: var(--color-pink-soft); color: var(--color-plum); }
.access-gate__badge.t2 { background: #fff0c8; color: var(--color-warning); }
.access-gate__badge.t3 { background: #fde8e7; color: var(--color-danger); }
.access-gate__content { width: 100%; }
</style>
