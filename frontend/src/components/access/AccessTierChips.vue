<template>
  <div class="tier-chips" :aria-label="`Access tiers reachable as ${access.currentRole.label}`"><span v-for="tier in tiers" :key="tier" class="tier-chip" :class="[tier.toLowerCase(), { 'tier-chip--off': !access.reachableTiers.includes(tier) }]">{{ tier }}</span></div>
</template>

<script setup lang="ts">
import { ACCESS_TIERS } from '../../data/accessControl';
import { useAccessControlStore } from '../../stores/useAccessControlStore';
const tiers = ACCESS_TIERS;
const access = useAccessControlStore();
</script>

<style scoped>
.tier-chips { display: flex; gap: 6px; }
.tier-chip { display: inline-flex; align-items: center; justify-content: center; min-width: 28px; height: 22px; border-radius: 999px; padding: 0 8px; font-size: 12px; font-weight: 800; border: 1px solid transparent; }
.tier-chip.t0 { background: #eef2ff; color: #3b4a9c; }
.tier-chip.t1 { background: var(--color-pink-soft); color: var(--color-plum); }
.tier-chip.t2 { background: #fff0c8; color: var(--color-warning); }
.tier-chip.t3 { background: #fde8e7; color: var(--color-danger); }
.tier-chip--off { background: transparent; border-color: var(--color-line); color: var(--color-muted); opacity: 0.55; }
</style>
