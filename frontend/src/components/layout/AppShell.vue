<template>
  <div class="shell">
    <aside class="nav" aria-label="Primary">
      <RouterLink class="brand" to="/">Patient360</RouterLink>
      <RouterLink v-for="item in navItems" :key="item.to" class="nav__item" :to="item.to"><component :is="item.icon" aria-hidden="true" /><span>{{ item.label }}</span></RouterLink>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div>
          <p>{{ session.me?.role ?? 'No session' }}</p>
          <strong>{{ session.display }}</strong>
        </div>
        <div class="topbar__actions">
          <label class="persona">
            <span>Persona</span>
            <select :value="currentLogin" @change="onPersona($event)">
              <option value="" disabled>Choose a persona</option>
              <option v-for="persona in session.personas" :key="persona.login" :value="persona.login">{{ persona.display }}</option>
            </select>
          </label>
          <label v-if="session.hasPanel('break_glass')" class="aal">
            <input type="checkbox" :checked="session.me?.session.auth_level === 2" @change="onAal($event)" />
            AAL2
          </label>
          <button class="ask-button" type="button" @click="ui.openAskPanel(patientId)">✦ Ask Patient360</button>
        </div>
      </header>
      <nav v-if="patientId" class="patient-tabs" aria-label="Patient sections">
        <RouterLink v-for="tab in patientTabs" :key="tab.to" :to="tab.to">{{ tab.label }}</RouterLink>
      </nav>
      <main class="content"><slot /></main>
    </div>
    <AskPatient360Panel />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { ClipboardList, FileText, Home, LockKeyhole, Search, Users } from 'lucide-vue-next';
import { useUiStore } from '../../stores/useUiStore';
import { useSessionStore } from '../../stores/useSessionStore';
import AskPatient360Panel from './AskPatient360Panel.vue';

const route = useRoute();
const ui = useUiStore();
const session = useSessionStore();
const patientId = computed(() => typeof route.params.patientId === 'string' ? route.params.patientId : undefined);
const currentLogin = computed(() => session.personas.find(p => p.user_id === session.me?.user_id)?.login ?? '');

const navItems = computed(() => {
  const items = [{ label: 'Home', to: '/', icon: Home, show: true }];
  if (session.me && (session.hasPanel('labs') || session.hasPanel('diet') || session.hasPanel('allergies_food'))) {
    items.push({ label: 'Patients', to: '/patients', icon: Search, show: true });
  }
  if (session.hasPanel('notes') || session.hasPanel('imaging') || session.hasPanel('imaging_metadata')) {
    items.push({ label: 'Tasks / Follow-ups', to: '/tasks', icon: ClipboardList, show: true });
    items.push({ label: 'Documents / Inbox', to: `/patients/${patientId.value ?? 'p_101'}/documents`, icon: FileText, show: true });
  }
  if (session.hasPanel('aggregate') || session.hasPanel('aggregate_own_patients') || session.hasPanel('aggregate_ward')) {
    items.push({ label: 'Cohort Insights', to: '/cohort', icon: Users, show: true });
  }
  if (session.hasPanel('audit')) items.push({ label: 'Audit & Privacy', to: '/audit', icon: LockKeyhole, show: true });
  items.push({ label: 'Threat model', to: '/threat-model', icon: LockKeyhole, show: Boolean(session.me) });
  if (session.hasPanel('audit') || session.hasPanel('break_glass')) {
    items.push({ label: 'Red team', to: '/redteam', icon: LockKeyhole, show: true });
  }
  if (session.hasPanel('portal')) items.push({ label: 'Portal', to: '/portal', icon: Home, show: true });
  return items.filter(item => item.show);
});

const patientTabs = computed(() => {
  const key = patientId.value;
  if (!key) return [];
  const tabs: Array<{ label: string; panel: string; to: string }> = [
    { label: 'Overview', panel: 'labs', to: `/patients/${key}/overview` },
    { label: 'Timeline', panel: 'labs', to: `/patients/${key}/timeline` },
    { label: 'Labs', panel: 'labs', to: `/patients/${key}/labs` },
    { label: 'Medications', panel: 'meds', to: `/patients/${key}/medications` },
    { label: 'Appointments', panel: 'appointments', to: `/patients/${key}/appointments` },
    { label: 'Documents', panel: 'notes', to: `/patients/${key}/documents` },
    { label: 'Notes', panel: 'notes', to: `/patients/${key}/notes` },
    { label: 'Imaging', panel: 'imaging', to: `/patients/${key}/imaging` }
  ];
  if (session.hasPanel('diet') || session.hasPanel('allergies_food')) {
    tabs.splice(4, 0, { label: 'Diet', panel: 'diet', to: `/patients/${key}/diet` });
  }
  return tabs.filter(tab => {
    if (tab.label === 'Overview') {
      return ['labs', 'meds', 'encounters', 'diet', 'allergies_food', 'portal'].some(panel => session.hasPanel(panel));
    }
    if (tab.panel === 'diet') return session.hasPanel('diet') || session.hasPanel('allergies_food');
    if (tab.panel === 'labs') return session.hasPanel('labs') || session.hasPanel('portal');
    if (tab.panel === 'imaging') return session.hasPanel('imaging') || session.hasPanel('imaging_metadata');
    return session.hasPanel(tab.panel);
  });
});

onMounted(() => { void session.bootstrap(); });

async function onPersona(event: Event) {
  const login = (event.target as HTMLSelectElement).value;
  await session.switchPersona(login, { auth_level: session.me?.session.auth_level === 1 ? 1 : 2 });
}

async function onAal(event: Event) {
  const login = currentLogin.value;
  if (!login) return;
  await session.switchPersona(login, { auth_level: (event.target as HTMLInputElement).checked ? 2 : 1 });
}
</script>

<style scoped>
.shell { min-height: 100dvh; display: grid; grid-template-columns: 260px minmax(0, 1fr); }.nav { display: flex; flex-direction: column; gap: 8px; padding: 24px 16px; border-right: 1px solid var(--color-line); background: #fff9e8; }.brand { min-height: auto; margin: 0 8px 20px; color: var(--color-plum); font-size: 1.4rem; font-weight: 850; text-decoration: none; }.nav__item { display: flex; align-items: center; gap: 12px; border-radius: var(--radius-control); color: var(--color-plum); padding: 0 12px; text-decoration: none; }.nav__item.router-link-active { background: var(--color-pink-soft); font-weight: 750; }.nav__item svg { width: 20px; }.workspace { min-width: 0; }.topbar { display: flex; align-items: center; justify-content: space-between; gap: 24px; border-bottom: 1px solid var(--color-line); background: rgb(255 253 244 / 92%); padding: 16px 32px; }.topbar p { margin: 0 0 2px; color: var(--color-muted); font-size: 14px; font-weight: 750; text-transform: uppercase; }.topbar__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }.persona { display: grid; gap: 2px; font-size: 12px; font-weight: 700; color: var(--color-muted); }.persona select { min-height: 40px; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 0 8px; }.aal { display: flex; align-items: center; gap: 6px; font-weight: 700; }.ask-button { border: 0; border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 18px; font-weight: 800; cursor: pointer; }.patient-tabs { display: flex; gap: 8px; overflow-x: auto; border-bottom: 1px solid var(--color-line); padding: 12px 32px; }.patient-tabs a { display: inline-flex; align-items: center; min-height: 40px; color: var(--color-muted); padding: 0 10px; text-decoration: none; white-space: nowrap; }.patient-tabs a.router-link-active { border-bottom: 3px solid var(--color-plum); color: var(--color-plum); font-weight: 800; }.content { padding: 32px; }
@media (max-width: 820px) { .shell { grid-template-columns: 1fr; }.nav { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-right: 0; border-bottom: 1px solid var(--color-line); padding: 12px; }.brand { grid-column: 1 / -1; margin: 0 8px 8px; }.nav__item { justify-content: center; padding: 0 6px; font-size: 14px; }.nav__item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.topbar, .patient-tabs, .content { padding-left: 18px; padding-right: 18px; } }
</style>
