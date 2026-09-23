<template>
  <section class="portal">
    <header>
      <p>{{ portalEyebrow }}</p>
      <h1>Welcome{{ session.me?.display ? `, ${session.me.display}` : '' }}</h1>
      <span>Your people, consents, and the next appointment on this session.</span>
    </header>
    <div v-if="!loading" class="people">
      <RouterLink
        v-for="person in people"
        :key="person.id"
        class="person"
        :to="defaultPatientPath('family', person.id)"
      >
        <span class="avatar">{{ person.avatarInitials }}</span>
        <span>
          <strong>{{ person.fullName }}</strong>
          <small v-if="personLevel(person)">{{ personLevel(person) }}</small>
          <small v-if="appointments[person.id]">{{ appointments[person.id] }}</small>
        </span>
        <span aria-hidden="true">→</span>
      </RouterLink>
      <p v-if="!people.length" class="empty">No people are visible on this session.</p>
    </div>
    <ConsentCard
      v-if="session.hasPanel('consents')"
      :patient-key="primaryKey"
      :relations="relations"
      title="Consents"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { grantableRelations } from '../../services/consents';
import { nextEncounter, practitionerName } from '../../services/dashboard';
import { formatLabDate } from '../../services/patientRecord';
import { accessLevel } from '../../services/accessLevel';
import { defaultPatientPath, familyPeople } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';
import type { PatientSummary } from '../../types/patient360';
import ConsentCard from '../clinic/ConsentCard.vue';

const session = useSessionStore();
const people = ref<PatientSummary[]>([]);
const appointments = ref<Record<string, string>>({});
const primaryKey = computed(() => session.me?.self_patient_id || people.value[0]?.id || '');
const relations = computed(() => grantableRelations(session.me?.role ?? ''));
const portalEyebrow = computed(() => `${accessLevel(session.me) || 'Family'} portal`);

function personLevel(person: PatientSummary): string {
  if (session.me?.self_patient_id && person.id === session.me.self_patient_id) {
    return accessLevel(session.me);
  }
  return '';
}

async function load() {
  if (!session.me) {
    people.value = [];
    appointments.value = {};
    return;
  }
  const visible = await apiClient.getPatients().catch(() => []);
  people.value = familyPeople(session.me, visible);
  const next: Record<string, string> = {};
  await Promise.all(people.value.map(async person => {
    const query = await apiClient.query('encounters', { patient_key: person.id }).catch(() => null);
    const upcoming = query ? nextEncounter(query.rows) : null;
    if (upcoming?.start) {
      const when = upcoming.start.includes('T')
        ? `${formatLabDate(upcoming.start.slice(0, 10))}${upcoming.start.slice(11, 16) ? ` · ${upcoming.start.slice(11, 16)}` : ''}`
        : formatLabDate(upcoming.start) || upcoming.start;
      const doctor = practitionerName(upcoming.practitioner, session.personas);
      next[person.id] = [doctor, upcoming.type, when].filter(Boolean).join(' · ');
    }
  }));
  appointments.value = next;
}

const { loading } = useLiveLoad(load);
</script>

<style scoped>
.portal { display: grid; gap: 20px; max-width: 1100px; }
.portal header span, .empty { color: var(--color-muted); }
.people { display: grid; gap: 10px; }
.person { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); color: var(--color-ink); padding: 16px; text-decoration: none; }
.avatar { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 50%; background: var(--color-accent-soft); color: var(--color-accent-ink); font-weight: 700; }
.person strong, .person small { display: block; }
.person small { margin-top: 3px; color: var(--color-muted); font-size: 14px; }
</style>
