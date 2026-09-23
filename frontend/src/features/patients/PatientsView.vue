<template>
  <section class="patient-search">
    <header>
      <p>{{ copy.eyebrow }}</p>
      <h1>{{ copy.title }}</h1>
      <span>{{ copy.hint }}</span>
    </header>
    <div class="search-box">
      <label for="patient-search">Find a patient</label>
      <input id="patient-search" v-model="query" placeholder="Search by name or date of birth" />
    </div>
    <form v-if="session.hasPanel('break_glass')" class="search-box emergency" @submit.prevent="openEmergency">
      <label for="emergency-key">Emergency chart open</label>
      <p>Open a chart that is not on this roster. Unauthorized and unknown charts look the same until break-glass succeeds.</p>
      <div class="emergency__row">
        <input id="emergency-key" v-model="emergencyKey" placeholder="Chart identifier from your runbook" />
        <button type="submit">Open chart</button>
      </div>
    </form>
    <p v-if="loading">Searching patient records…</p>
    <div v-else class="results">
      <RouterLink v-for="patient in results" :key="patient.id" :to="defaultPatientPath(session.workspace, patient.id)">
        <span class="avatar">{{ patient.avatarInitials }}</span>
        <span>
          <strong>{{ patient.fullName }}</strong>
          <small v-if="secondaryLine(patient)">{{ secondaryLine(patient) }}</small>
          <p v-if="patient.reason">{{ patient.reason }}</p>
        </span>
        <span aria-hidden="true">→</span>
      </RouterLink>
      <p v-if="!results.length" class="empty">No visible patients match this search.</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { defaultPatientPath, directoryCopy } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';
import type { PatientSummary } from '../../types/patient360';

const session = useSessionStore();
const router = useRouter();
const copy = computed(() => directoryCopy(session.workspace));

const query = ref('');
const emergencyKey = ref('');
const results = ref<PatientSummary[]>([]);
const loading = ref(false);

function secondaryLine(patient: PatientSummary): string {
  // Prefer human labels. Raw keys belong in emergency open, not the roster row.
  if (session.workspace === 'kitchen') return patient.reason || patient.reasonForVisit || '';
  return patient.dateOfBirth || '';
}

function openEmergency() {
  const key = emergencyKey.value.trim();
  if (!key) return;
  void router.push(defaultPatientPath(session.workspace, key));
}

async function search() {
  loading.value = true;
  results.value = await apiClient.searchPatients(query.value);
  loading.value = false;
}

useLiveLoad(search);
watch(query, search);
</script>

<style scoped>
.patient-search { display: grid; gap: var(--space-5); max-width: 1000px; }
.search-box { display: grid; gap: 10px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); padding: var(--space-5); box-shadow: var(--shadow-soft); }
.search-box label { font-weight: 650; }
.search-box input { min-height: 44px; width: 100%; }
.search-box p { margin: 0; color: var(--color-muted); font-size: var(--text-sm); font-weight: 500; }
.emergency__row { display: flex; gap: 8px; }
.emergency__row input { flex: 1; }
.results { display: grid; gap: 10px; }
.results a {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 14px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-ink);
  padding: 16px;
  text-decoration: none;
}
.results a:hover { border-color: rgb(29 78 216 / 28%); background: var(--color-accent-soft); }
.avatar {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 50%;
  background: var(--color-accent-soft);
  color: var(--color-accent-ink);
  font-weight: 700;
}
.results strong, .results small, .results p { display: block; }
.results small, .results p, .empty { margin: 3px 0; color: var(--color-muted); font-size: var(--text-sm); }
</style>
