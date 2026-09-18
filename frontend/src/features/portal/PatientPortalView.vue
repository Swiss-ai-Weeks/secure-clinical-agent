<template>
  <section class="portal">
    <header>
      <p>Patient portal</p>
      <h1>Welcome{{ session.me?.display ? `, ${session.me.display}` : '' }}</h1>
      <span>Consents on your record, including grant and revoke.</span>
    </header>
    <ConsentCard :patient-key="patientKey" :relations="relations" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { grantableRelations } from '../../services/consents';
import { useSessionStore } from '../../stores/useSessionStore';
import ConsentCard from '../clinic/ConsentCard.vue';

const session = useSessionStore();
const patientKey = ref('');
const relations = computed(() => grantableRelations(session.me?.role ?? ''));

async function load() {
  if (session.me?.self_patient_id) {
    patientKey.value = session.me.self_patient_id;
    return;
  }
  const visible = (await apiClient.getPatients().catch(() => [])).find(patient => patient.status === 'Visible');
  patientKey.value = visible?.id ?? '';
}

useLiveLoad(load);
</script>

<style scoped>
.portal { display: grid; gap: 20px; max-width: 1100px; }.portal header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.portal h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }
</style>
