<template><section class="audit"><header><p>Governance</p><h1>Audit & privacy</h1><span>Every AI answer is scoped to the records your role may access.</span></header><RoleGate page-key="auditPage" label="Audit & privacy" :allowed-roles="AUDIT_PAGE_ALLOWED_ROLES"><div class="audit__labels"><StatusPill label="AI query access" tone="warning" /><StatusPill label="Patient record access" tone="neutral" /><StatusPill label="Blocked access" tone="danger" /></div><div class="audit__table"><p v-if="!access.accessLog.length" class="audit__empty">No access checks recorded yet this session — switch roles or open a patient record to generate entries.</p><article v-for="entry in access.accessLog" :key="entry.id"><time>{{ entry.timestamp }}</time><strong>{{ entry.roleLabel }}</strong><span>{{ describeEntry(entry) }}</span></article></div></RoleGate></section></template>
<script setup lang="ts">
import StatusPill from '../../components/ui/StatusPill.vue';
import RoleGate from '../../components/access/RoleGate.vue';
import { AUDIT_PAGE_ALLOWED_ROLES } from '../../data/accessControl';
import { useAccessControlStore, type AccessLogEntry } from '../../stores/useAccessControlStore';

// Full session log (useAccessControlStore.accessLog) — same source
// AccessLogPanel.vue reads, unfiltered. This mirrors the "Session audit" tab
// in the original design reference (frontend/design-reference/patient360-core-screen.html):
// "What was asked, returned, and denied this session — the same trail the
// backend logs." A compliance-review page narrowing that to a subset (e.g.
// only denials, or only one patient) would need its own explicit product
// decision — nothing in the spec calls for that narrowing, so this stays the
// full trail rather than silently filtering it.
const access = useAccessControlStore();

function describeEntry(entry: AccessLogEntry): string {
  const isPageEntry = entry.tier === 'PAGE';
  const verb = isPageEntry
    ? (entry.allowed ? 'Opened' : 'Blocked from opening')
    : (entry.allowed ? 'Viewed' : 'Denied access to');
  const tierSuffix = isPageEntry ? '' : ` (${entry.tier})`;
  const supervision = entry.supervisionNote ? ` · ${entry.supervisionNote}` : '';
  return `${verb} ${entry.fieldLabel}${tierSuffix}${supervision}`;
}
</script>
<style scoped>.audit { display: grid; gap: 20px; max-width: 1000px; }.audit header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.audit h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.audit header span { color: var(--color-muted); }.audit__labels { display: flex; flex-wrap: wrap; gap: 8px; }.audit__table { border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); overflow: hidden; }.audit__table article { display: grid; grid-template-columns: 80px 150px 1fr; gap: 16px; border-bottom: 1px solid var(--color-line); padding: 18px; }.audit__table article:last-child { border-bottom: 0; }.audit__empty { margin: 0; padding: 18px; color: var(--color-muted); font-size: 14px; }.audit time, .audit span { color: var(--color-muted); } @media (max-width: 600px) { .audit__table article { grid-template-columns: 1fr; gap: 4px; } }</style>
