<template>
  <div class="shell">
    <aside class="nav" aria-label="Primary">
      <RouterLink class="brand" to="/">Patient360</RouterLink>
      <RouterLink v-for="item in navItems" :key="item.to" class="nav__item" :to="item.to"><component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink>
    </aside>
    <div class="workspace">
      <header class="topbar"><div class="topbar__role"><label for="role-select">Acting as</label><select id="role-select" class="role-select" :value="access.role" @change="access.setRole(($event.target as HTMLSelectElement).value as AccessRole)"><option v-for="opt in access.roleOptions" :key="opt.key" :value="opt.key">{{ opt.label }}</option></select><AccessTierChips /></div><button class="ask-button" type="button" @click="ui.openAskPanel(patientId)">✦ Ask Patient360</button></header>
      <nav v-if="patientId" class="patient-tabs" aria-label="Patient sections"><RouterLink v-for="tab in patientTabs" :key="tab.to" :to="tab.to">{{ tab.label }}</RouterLink></nav>
      <main class="content"><slot /></main>
    </div>
    <AskPatient360Panel />
    <AccessLogPanel />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { ClipboardList, FileText, Home, LockKeyhole, Search, Users } from 'lucide-vue-next';
import { useUiStore } from '../../stores/useUiStore';
import { useAccessControlStore } from '../../stores/useAccessControlStore';
import { AUDIT_PAGE_ALLOWED_ROLES } from '../../data/accessControl';
import type { AccessRole } from '../../types/patient360';
import AskPatient360Panel from './AskPatient360Panel.vue';
import AccessTierChips from '../access/AccessTierChips.vue';
import AccessLogPanel from '../access/AccessLogPanel.vue';

const route = useRoute();
const ui = useUiStore();
const access = useAccessControlStore();
const patientId = computed(() => typeof route.params.patientId === 'string' ? route.params.patientId : undefined);
const allNavItems = [
  { label: 'Home', to: '/', icon: Home }, { label: 'Patients', to: '/patients', icon: Search }, { label: 'Tasks / Follow-ups', to: '/tasks', icon: ClipboardList }, { label: 'Documents / Inbox', to: '/patients/emma-laurent/documents', icon: FileText }, { label: 'Cohort Insights', to: '/cohort', icon: Users }, { label: 'Audit & Privacy', to: '/audit', icon: LockKeyhole, requiresRoles: AUDIT_PAGE_ALLOWED_ROLES }
];
// Demo-only: hides nav entries the current role can't open — the page itself
// still gates its content too (see AuditPrivacyView.vue / RoleGate.vue), so
// direct navigation to a hidden route is never the only thing stopping it.
const navItems = computed(() => allNavItems.filter(item => !item.requiresRoles || item.requiresRoles.includes(access.role)));
const patientTabs = computed(() => ['Overview', 'Timeline', 'Labs', 'Medications', 'Documents', 'Notes'].map(label => ({ label, to: `/patients/${patientId.value}/${label.toLowerCase()}` })));
</script>

<style scoped>
.shell { min-height: 100dvh; display: grid; grid-template-columns: 260px minmax(0, 1fr); }.nav { display: flex; flex-direction: column; gap: 8px; padding: 24px 16px; border-right: 1px solid var(--color-line); background: #fff9e8; }.brand { min-height: auto; margin: 0 8px 20px; color: var(--color-plum); font-size: 1.4rem; font-weight: 850; text-decoration: none; }.nav__item { display: flex; align-items: center; gap: 12px; border-radius: var(--radius-control); color: var(--color-plum); padding: 0 12px; text-decoration: none; }.nav__item.router-link-active { background: var(--color-pink-soft); font-weight: 750; }.nav__item svg { width: 20px; }.workspace { min-width: 0; }.topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; border-bottom: 1px solid var(--color-line); background: rgb(255 253 244 / 92%); padding: 16px 32px; }.topbar__role { display: flex; align-items: center; gap: 12px; }.topbar__role label { color: var(--color-muted); font-size: 13px; font-weight: 750; text-transform: uppercase; }.role-select { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 6px 10px; font-weight: 750; color: var(--color-plum); }.ask-button { border: 0; border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 18px; font-weight: 800; cursor: pointer; }.patient-tabs { display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid var(--color-line); padding: 12px 32px; }.patient-tabs a { display: inline-flex; align-items: center; min-height: 40px; color: var(--color-muted); padding: 0 10px; text-decoration: none; white-space: nowrap; }.patient-tabs a.router-link-active { border-bottom: 3px solid var(--color-plum); color: var(--color-plum); font-weight: 800; }.content { padding: 32px; }
@media (max-width: 820px) { .shell { grid-template-columns: 1fr; }.nav { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-right: 0; border-bottom: 1px solid var(--color-line); padding: 12px; }.brand { grid-column: 1 / -1; margin: 0 8px 8px; }.nav__item { justify-content: center; padding: 0 6px; font-size: 14px; }.nav__item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.topbar, .patient-tabs, .content { padding-left: 18px; padding-right: 18px; } }
</style>
