<template>
  <section class="patient-search">
    <header>
      <p>Directory</p>
      <h1>Patients</h1>
      <span>Demo keys only. Names appear when <code>GET /patients/{'{key}'}/identity</code> permits.</span>
    </header>
    <div class="search-box">
      <label for="patient-search">Find a patient</label>
      <input id="patient-search" v-model="query" placeholder="Patient key or visible name" />
      <div class="modes">
        <button type="button" :class="{ active: mode === 'standard' }" @click="mode = 'standard'">Standard search</button>
        <button type="button" :class="{ active: mode === 'ai' }" @click="mode = 'ai'">Natural-language AI search</button>
      </div>
    </div>
    <p v-if="loading">Searching patient records…</p>
    <div v-else class="results">
      <RouterLink v-for="patient in results" :key="patient.id" :to="`/patients/${patient.id}/overview`">
        <span class="avatar">{{ patient.avatarInitials }}</span>
        <span>
          <strong>{{ patient.fullName }}</strong>
          <small>{{ patient.id }}{{ patient.dateOfBirth ? ` · ${patient.dateOfBirth}` : '' }}</small>
          <em v-if="patient.resultMode === 'ai'">✦ AI generated result</em>
          <p>{{ patient.reason }}</p>
        </span>
        <span aria-hidden="true">→</span>
      </RouterLink>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { RouterLink } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import type { PatientSummary, ResultMode } from '../../types/patient360';
import { useSessionStore } from '../../stores/useSessionStore';

const session = useSessionStore();
const query = ref('');
const mode = ref<ResultMode>('standard');
const results = ref<PatientSummary[]>([]);
const loading = ref(false);

async function search() {
  loading.value = true;
  results.value = await apiClient.searchPatients(query.value, mode.value);
  loading.value = false;
}

watch([query, mode], search);
watch(() => session.me?.user_id, search);
onMounted(search);
</script>

<style scoped>
.patient-search { display: grid; gap: 20px; max-width: 1000px; }.patient-search header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.patient-search h1 { margin: 4px 0; font-size: clamp(2.2rem, 5vw, 3.5rem); }.patient-search header span { color: var(--color-muted); }.search-box { display: grid; gap: 10px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); padding: 20px; }.search-box label { font-weight: 750; }.search-box input { min-height: 48px; width: 100%; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 0 12px; }.modes { display: flex; flex-wrap: wrap; gap: 8px; }.modes button { border: 1px solid var(--color-line); border-radius: 999px; background: var(--color-surface); padding: 0 12px; cursor: pointer; }.modes button.active { border-color: var(--color-plum); background: var(--color-plum); color: white; }.results { display: grid; gap: 10px; }.results a { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface); color: var(--color-plum); padding: 16px; text-decoration: none; }.avatar { display: grid; width: 48px; height: 48px; place-items: center; border-radius: 50%; background: var(--color-pink); font-weight: 850; }.results strong, .results small, .results em, .results p { display: block; }.results small, .results p { margin: 3px 0; color: var(--color-muted); font-size: 14px; }
</style>
