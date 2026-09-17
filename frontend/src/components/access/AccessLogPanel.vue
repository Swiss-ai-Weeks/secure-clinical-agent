<!--
  TEMPORARY DEMO PANEL — in-memory only, cleared on refresh. This is not the
  Audit & Privacy page's real audit trail; it exists to show what a client
  would send a backend audit endpoint for each field access, in a real
  integration. See src/stores/useAccessControlStore.ts.
-->
<template>
  <div class="access-log" :class="{ 'access-log--open': ui.accessLogOpen }">
    <button type="button" class="access-log__toggle" @click="ui.toggleAccessLog()">{{ ui.accessLogOpen ? 'Close access log' : `Access log (demo) · ${access.accessLog.length}` }}</button>
    <div v-if="ui.accessLogOpen" class="access-log__panel">
      <header><strong>Access log — demo simulation</strong><span>Frontend-only, in-memory. Not the real audit trail.</span></header>
      <p v-if="!access.accessLog.length" class="access-log__empty">No field access checks yet — switch roles or open a patient record.</p>
      <ul v-else class="access-log__rows">
        <li v-for="entry in access.accessLog" :key="entry.id">
          <span class="access-log__decision" :class="entry.allowed ? 'allow' : 'deny'">{{ entry.allowed ? 'ALLOW' : 'DENY' }}</span>
          <span class="access-log__detail">
            <strong>{{ entry.fieldLabel }}</strong> ({{ entry.tier }}) · {{ entry.roleLabel }}
            <em v-if="entry.supervisionNote">{{ entry.supervisionNote }}</em>
          </span>
          <time>{{ entry.timestamp }}</time>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAccessControlStore } from '../../stores/useAccessControlStore';
import { useUiStore } from '../../stores/useUiStore';
const access = useAccessControlStore();
const ui = useUiStore();
</script>

<style scoped>
.access-log { position: fixed; right: 20px; bottom: 20px; z-index: 40; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.access-log__toggle { border: 1px solid var(--color-line); border-radius: 999px; background: var(--color-plum); color: white; padding: 0 16px; height: 38px; font-weight: 750; cursor: pointer; box-shadow: var(--shadow-soft); }
.access-log__panel { width: min(380px, 90vw); max-height: 50vh; overflow-y: auto; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); box-shadow: var(--shadow-soft); padding: 16px; }
.access-log__panel header { display: flex; flex-direction: column; gap: 2px; margin-bottom: 10px; }
.access-log__panel header span { color: var(--color-muted); font-size: 12px; }
.access-log__empty { color: var(--color-muted); font-size: 14px; margin: 0; }
.access-log__rows { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.access-log__rows li { display: grid; grid-template-columns: auto 1fr auto; align-items: start; gap: 8px; border-bottom: 1px solid var(--color-line); padding-bottom: 8px; font-size: 13px; }
.access-log__rows li:last-child { border-bottom: 0; padding-bottom: 0; }
.access-log__decision { display: inline-flex; align-items: center; justify-content: center; height: 20px; padding: 0 8px; border-radius: 999px; font-size: 10px; font-weight: 800; }
.access-log__decision.allow { background: #e5f5e8; color: var(--color-success); }
.access-log__decision.deny { background: #fde8e7; color: var(--color-danger); }
.access-log__detail strong { color: var(--color-plum); }
.access-log__detail em { display: block; margin-top: 2px; color: var(--color-muted); font-size: 11px; font-style: normal; }
.access-log__rows time { color: var(--color-muted); font-size: 11px; white-space: nowrap; }
</style>
