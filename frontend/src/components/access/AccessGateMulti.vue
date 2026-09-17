<!--
  FRONTEND-ONLY DEMO SIMULATION — see src/data/accessControl.ts. Sibling of
  AccessGate.vue for content synthesized from MORE THAN ONE tagged field —
  e.g. a narrative brief that states both a diagnosis trend and a lab trend
  in the same prose, which can't be cleanly split per-sentence the way
  CurrentSnapshot.vue splits independent sections.

  Every field this content touches is checked and logged individually (same
  checkAccess() as AccessGate), but the content renders as a single
  all-or-nothing unit: if ANY touched field is denied, the whole thing is
  replaced by one AccessDenialCard — never a partial or reworded version.
  Same principle as the Ask Patient360 answer path in mockApi.ts, where a
  query touching a denied field is refused outright rather than papered over.
-->
<template>
  <div class="access-gate">
    <template v-if="allowed">
      <span v-for="tier in tiers" :key="tier" class="access-gate__badge" :class="tier.toLowerCase()">{{ tier }}</span>
      <div class="access-gate__content"><slot /></div>
    </template>
    <AccessDenialCard v-else :label="firstDenied.label" :tier="firstDenied.tier" />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import { decideAccess } from '../../data/accessControl';
import { useAccessControlStore } from '../../stores/useAccessControlStore';
import AccessDenialCard from './AccessDenialCard.vue';

const props = defineProps<{ fields: string[] }>();
const access = useAccessControlStore();

// Pure decisions for rendering — access.role is read directly so this
// recomputes when the role changes.
const decisions = computed(() => props.fields.map(field => decideAccess(access.role, field)));
const allowed = computed(() => decisions.value.every(decision => decision.allowed));
const firstDenied = computed(() => decisions.value.find(decision => !decision.allowed) ?? decisions.value[0]);
const tiers = computed(() => Array.from(new Set(decisions.value.map(decision => decision.tier))));

// Logging is the side effect: every field this component touches gets its
// own checkAccess() call, so the access log reflects all of them — not just
// whichever one happened to gate the render.
watch(
  [() => access.role, () => props.fields.join(',')],
  () => props.fields.forEach(field => access.checkAccess(field)),
  { immediate: true }
);
</script>

<style scoped>
.access-gate { display: inline-flex; flex-direction: column; gap: 6px; width: 100%; }
.access-gate__badge { align-self: flex-start; display: inline-flex; align-items: center; height: 20px; padding: 0 8px; border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: 0.02em; margin-right: 4px; }
.access-gate__badge.t0 { background: #eef2ff; color: #3b4a9c; }
.access-gate__badge.t1 { background: var(--color-pink-soft); color: var(--color-plum); }
.access-gate__badge.t2 { background: #fff0c8; color: var(--color-warning); }
.access-gate__badge.t3 { background: #fde8e7; color: var(--color-danger); }
.access-gate__content { width: 100%; }
</style>
