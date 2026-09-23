<template>
  <div class="shell" :class="{ 'shell--nav-collapsed': navCollapsed }">
    <aside class="nav" aria-label="Primary">
      <RouterLink class="brand" to="/" :title="navCollapsed ? 'Patient360' : undefined">
        <span class="brand__mark" aria-hidden="true">P360</span>
        <span class="brand__text">Patient360</span>
      </RouterLink>
      <nav class="nav__list">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          v-slot="{ href, navigate, isActive, isExactActive }"
          :to="item.to"
          custom
        >
          <a
            class="nav__item"
            :class="{ 'router-link-active': item.to === '/' ? isExactActive : isActive }"
            :href="href"
            :title="navCollapsed ? item.label : undefined"
            :aria-label="item.label"
            @click="navigate"
          >
            <component :is="item.icon" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </a>
        </RouterLink>
      </nav>
      <button
        type="button"
        class="nav__collapse"
        :aria-label="navCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        :aria-expanded="!navCollapsed"
        :title="navCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        @click="toggleNav"
      >
        <PanelLeftOpen v-if="navCollapsed" aria-hidden="true" />
        <PanelLeftClose v-else aria-hidden="true" />
        <span class="nav__collapse-label">{{ navCollapsed ? 'Expand' : 'Collapse' }}</span>
      </button>
    </aside>
    <div class="workspace">
      <header class="topbar">
        <div class="topbar__identity">
          <p>{{ roleLabel }}</p>
          <strong>{{ session.display }}</strong>
        </div>
        <div class="topbar__actions">
          <label class="persona">
            <span>Persona</span>
            <select :value="currentLogin" :disabled="session.switching" :aria-busy="session.switching" @change="onPersona($event)">
              <option value="" disabled>Choose a persona</option>
              <option v-for="persona in session.personas" :key="persona.login" :value="persona.login">{{ personaOption(persona) }}</option>
            </select>
          </label>
          <label v-if="session.hasPanel('break_glass')" class="aal">
            <input type="checkbox" :checked="session.me?.session.auth_level === 2" :disabled="session.switching" @change="onAal($event)" />
            <span>AAL2</span>
          </label>
          <button
            v-if="showAsk"
            class="ask-button"
            type="button"
            title="Ask about the open chart"
            @click="ui.openAskPanel(patientId)"
          >Ask Patient360</button>
        </div>
      </header>
      <nav v-if="patientId" class="patient-tabs" aria-label="Patient sections">
        <RouterLink v-for="tab in patientTabs" :key="tab.to" :to="tab.to">{{ tab.label }}</RouterLink>
      </nav>
      <main class="content" :class="{ 'content--viewer': isViewer }" :aria-busy="busy">
        <slot />
        <div v-if="busy" class="content__overlay">
          <LoadingIndicator :message="loadingMessage" />
        </div>
      </main>
    </div>
    <AskPatient360Panel />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { RouterLink, useRoute, useRouter } from 'vue-router';
import { ClipboardList, Home, LockKeyhole, PanelLeftClose, PanelLeftOpen, Search, Users } from 'lucide-vue-next';
import { accessLevel, personAccessLabel } from '../../services/accessLevel';
import { canLaunchAsk, navItemsFor, patientTabsFor } from '../../services/workspace';
import type { Persona } from '../../types/api';
import { useUiStore } from '../../stores/useUiStore';
import { useSessionStore } from '../../stores/useSessionStore';
import LoadingIndicator from '../ui/LoadingIndicator.vue';
import AskPatient360Panel from './AskPatient360Panel.vue';

const NAV_COLLAPSE_KEY = 'patient360.navCollapsed';

const NAV_ICONS = {
  Home,
  'My people': Users,
  'Ward trays': Users,
  Patients: Search,
  'Tasks / Follow-ups': ClipboardList,
  'Cohort Insights': Users,
  'Audit & Privacy': LockKeyhole,
  'Red team': LockKeyhole,
  Appointments: ClipboardList
} as const;

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const session = useSessionStore();
const navCollapsed = ref(false);
const patientId = computed(() => typeof route.params.patientId === 'string' ? route.params.patientId : undefined);
const isViewer = computed(() => route.name === 'patient-ohif');
const showAsk = computed(() => canLaunchAsk({
  panels: session.panels,
  workspace: session.workspace,
  patientId: patientId.value,
  onDuty: session.me?.session.on_duty
}));
const currentLogin = computed(() => session.personas.find(p => p.user_id === session.me?.user_id)?.login ?? '');
const roleLabel = computed(() => (session.me ? accessLevel(session.me) || 'Signed in' : 'Sign in'));

function personaOption(persona: Persona): string {
  if (persona.user_id === session.me?.user_id) return personAccessLabel({ ...persona, ...session.me });
  return personAccessLabel(persona);
}

const navItems = computed(() => navItemsFor(session.workspace, session.panels, {
  patientId: patientId.value,
  selfPatientId: session.me?.self_patient_id
}).map(item => ({
  ...item,
  icon: NAV_ICONS[item.label as keyof typeof NAV_ICONS] ?? Home
})));

const patientTabs = computed(() => {
  const key = patientId.value;
  if (!key) return [];
  return patientTabsFor(session.workspace, session.panels, key);
});

const busy = computed(() => !session.ready || session.switching || ui.routePending || ui.pageLoads > 0);
const loadingMessage = computed(() => session.switching ? 'Switching persona…' : 'Loading…');

watch(showAsk, allowed => {
  if (!allowed && ui.askPanelOpen) ui.closeAskPanel();
});

onMounted(() => {
  try {
    navCollapsed.value = localStorage.getItem(NAV_COLLAPSE_KEY) === '1';
  } catch {
    /* ignore storage failures */
  }
  void session.bootstrap();
});

function toggleNav() {
  navCollapsed.value = !navCollapsed.value;
  try {
    localStorage.setItem(NAV_COLLAPSE_KEY, navCollapsed.value ? '1' : '0');
  } catch {
    /* ignore storage failures */
  }
}

async function onPersona(event: Event) {
  const login = (event.target as HTMLSelectElement).value;
  await session.switchPersona(login, { auth_level: session.me?.session.auth_level === 1 ? 1 : 2 });
  if (route.path !== '/') await router.push('/');
}

async function onAal(event: Event) {
  const login = currentLogin.value;
  if (!login) return;
  await session.switchPersona(login, { auth_level: (event.target as HTMLInputElement).checked ? 2 : 1 });
}
</script>

<style scoped>
.shell {
  height: 100dvh;
  max-height: 100dvh;
  min-height: 100dvh;
  max-width: 100vw;
  display: grid;
  grid-template-columns: var(--nav-width) minmax(0, 1fr);
  overflow: hidden;
  background: var(--color-bg);
  transition: grid-template-columns 180ms ease;
}

.shell--nav-collapsed {
  grid-template-columns: var(--nav-width-collapsed) minmax(0, 1fr);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  height: 100%;
  max-height: 100dvh;
  min-height: 0;
  min-width: 0;
  padding: var(--space-5) var(--space-3);
  background: var(--color-nav);
  color: var(--color-nav-ink);
  overflow: hidden;
  border-right: 1px solid rgb(255 255 255 / 4%);
}

.brand {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--space-3);
  min-height: auto;
  margin: 0 var(--space-2);
  padding: var(--space-1) 0 var(--space-2);
  color: var(--color-nav-ink-strong);
  text-decoration: none;
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  border-radius: 10px;
  background: var(--color-accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.brand__text {
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  white-space: nowrap;
  overflow: hidden;
}

.nav__list {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0 var(--space-1);
}

.nav__item {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-height: 40px;
  border-radius: 10px;
  color: var(--color-nav-ink);
  padding: 0 var(--space-3);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: 500;
  letter-spacing: -0.01em;
  transition: background 140ms ease, color 140ms ease;
  min-width: 0;
}

.nav__item:hover {
  background: var(--color-nav-hover);
  color: var(--color-nav-ink-strong);
}

.nav__item.router-link-active {
  background: var(--color-nav-active);
  color: #fff;
  font-weight: 600;
}

.nav__item.router-link-active::before {
  content: "";
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 2px 2px 0;
  background: #60a5fa;
}

.nav__item svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke-width: 1.75;
  opacity: 0.92;
}

.nav__item span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav__collapse {
  margin-top: auto;
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--space-3);
  min-height: 40px;
  width: calc(100% - var(--space-2));
  margin-left: var(--space-1);
  margin-right: var(--space-1);
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 10px;
  background: transparent;
  color: var(--color-nav-ink);
  padding: 0 var(--space-3);
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: background 140ms ease, color 140ms ease, border-color 140ms ease;
}

.nav__collapse:hover {
  background: var(--color-nav-hover);
  border-color: rgb(255 255 255 / 14%);
  color: var(--color-nav-ink-strong);
}

.nav__collapse:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

.nav__collapse svg {
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  stroke-width: 1.75;
  opacity: 0.92;
}

.nav__collapse-label {
  white-space: nowrap;
}

.shell--nav-collapsed .nav {
  padding: var(--space-5) var(--space-2);
  align-items: stretch;
}

.shell--nav-collapsed .brand {
  justify-content: center;
  margin: 0;
  padding-bottom: var(--space-2);
}

.shell--nav-collapsed .brand__text,
.shell--nav-collapsed .nav__item span,
.shell--nav-collapsed .nav__collapse-label {
  display: none;
}

.shell--nav-collapsed .nav__list {
  padding: 0;
  align-items: center;
}

.shell--nav-collapsed .nav__item {
  justify-content: center;
  width: 44px;
  height: 44px;
  min-height: 44px;
  margin: 0 auto;
  padding: 0;
  border-radius: 12px;
}

.shell--nav-collapsed .nav__item.router-link-active::before {
  display: none;
}

.shell--nav-collapsed .nav__item.router-link-active {
  background: var(--color-accent);
  color: #fff;
  box-shadow: 0 4px 12px rgb(29 78 216 / 35%);
}

.shell--nav-collapsed .nav__collapse {
  justify-content: center;
  width: 44px;
  height: 44px;
  min-height: 44px;
  margin: auto auto 0;
  padding: 0;
  border-radius: 12px;
}

.workspace {
  min-width: 0;
  min-height: 0;
  max-width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-x: clip;
  overflow-y: auto;
}

.topbar {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  border-bottom: 1px solid var(--color-line);
  background: rgb(255 255 255 / 88%);
  backdrop-filter: blur(12px);
  padding: var(--space-3) var(--space-7);
}

.topbar__identity {
  min-width: 0;
}

.topbar__identity p {
  margin: 0 0 2px;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}

.topbar__identity strong {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}

.topbar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  justify-content: flex-end;
  gap: var(--space-3);
  min-width: 0;
}

.persona {
  display: grid;
  gap: 2px;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-muted);
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}

.persona select {
  min-height: 38px;
  min-width: 14rem;
  max-width: min(22rem, 56vw);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  padding: 0 0.7rem;
  font-size: var(--text-sm);
  font-weight: 500;
  text-transform: none;
  letter-spacing: -0.01em;
  color: var(--color-ink);
}

.aal {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  padding: 0 12px;
  font-size: var(--text-sm);
  font-weight: 550;
  color: var(--color-muted-strong);
}

.ask-button {
  white-space: nowrap;
}

.patient-tabs {
  display: flex;
  flex: 0 0 auto;
  gap: var(--space-1);
  overflow-x: auto;
  border-bottom: 1px solid var(--color-line);
  background: var(--color-surface);
  padding: 0 var(--space-7);
}

.patient-tabs a {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  color: var(--color-muted);
  padding: 0 var(--space-3);
  text-decoration: none;
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 500;
  letter-spacing: -0.01em;
  border-bottom: 2px solid transparent;
  transition: color 140ms ease, border-color 140ms ease;
}

.patient-tabs a:hover {
  color: var(--color-ink);
}

.patient-tabs a.router-link-active {
  border-bottom-color: var(--color-accent);
  color: var(--color-accent-ink);
  font-weight: 600;
}

.content {
  position: relative;
  flex: 1;
  min-width: 0;
  padding: var(--space-7) var(--space-7) var(--space-8);
}

.content--viewer {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding-top: var(--space-4);
  padding-bottom: var(--space-4);
}

.content--viewer :deep(.ohif) {
  flex: 1 1 auto;
  min-height: 0;
}

.content__overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgb(245 247 251 / 86%);
  backdrop-filter: blur(2px);
  z-index: 2;
}

@media (max-width: 820px) {
  .shell,
  .shell--nav-collapsed {
    height: auto;
    max-height: none;
    min-height: 100dvh;
    grid-template-columns: 1fr;
    overflow: visible;
  }

  .nav {
    height: auto;
    max-height: none;
    gap: var(--space-3);
    padding: var(--space-3);
    border-right: 0;
    border-bottom: 1px solid rgb(255 255 255 / 8%);
    overflow: visible;
  }

  .nav__list {
    flex: none;
    overflow: visible;
  }

  .workspace {
    height: auto;
    overflow: visible;
  }

  .brand {
    margin: 0 var(--space-1) var(--space-1);
  }

  .shell--nav-collapsed .brand {
    justify-content: flex-start;
    margin: 0 var(--space-1) var(--space-1);
  }

  .shell--nav-collapsed .brand__text,
  .shell--nav-collapsed .nav__item span {
    display: inline;
  }

  .nav__collapse {
    display: none;
  }

  .nav__list {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-1);
    padding: 0;
  }

  .nav__item {
    justify-content: center;
    padding: 0 6px;
    font-size: 13px;
  }

  .nav__item.router-link-active::before {
    display: none;
  }

  .shell--nav-collapsed .nav__item {
    width: auto;
    height: auto;
    min-height: 40px;
    margin: 0;
    justify-content: center;
    padding: 0 6px;
    border-radius: 10px;
    box-shadow: none;
  }

  .shell--nav-collapsed .nav__item.router-link-active {
    background: var(--color-nav-active);
    box-shadow: none;
  }

  .nav__item span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .topbar,
  .patient-tabs,
  .content {
    padding-left: var(--space-4);
    padding-right: var(--space-4);
  }

  .topbar {
    align-items: stretch;
    flex-direction: column;
  }

  .topbar__actions {
    justify-content: stretch;
  }

  .persona,
  .persona select,
  .ask-button {
    width: 100%;
  }
}
</style>
