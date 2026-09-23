<template>
  <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
  <div v-else-if="patient && !loading" class="overview">
    <PatientHeader :patient="patient" />
    <ConsentCard v-if="session.hasPanel('consents')" :patient-key="patient.id" :relations="relations" title="Grant access" />
    <section class="overview__grid">
      <ClinicalBrief v-if="session.workspace === 'clinical'" :patient="patient" />
      <SinceLastVisit v-if="session.workspace === 'clinical'" :patient="patient" />
      <CurrentSnapshot :patient="patient" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { grantableRelations } from '../../services/consents';
import { ApiError } from '../../services/http';
import { defaultPatientPath } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';
import type { Patient } from '../../types/patient360';
import ConsentCard from '../clinic/ConsentCard.vue';
import PatientHeader from './PatientHeader.vue';
import ResourceNotFound from './ResourceNotFound.vue';
import ClinicalBrief from './ClinicalBrief.vue';
import SinceLastVisit from './SinceLastVisit.vue';
import CurrentSnapshot from './CurrentSnapshot.vue';

const route = useRoute();
const router = useRouter();
const session = useSessionStore();
const patient = ref<Patient | null>(null);
const missing = ref(false);
const relations = computed(() => grantableRelations(session.me?.role ?? ''));

async function load() {
  const key = String(route.params.patientId);
  if (session.workspace === 'kitchen') {
    await router.replace(defaultPatientPath('kitchen', key));
    return;
  }
  missing.value = false;
  try {
    patient.value = await apiClient.getPatient(key);
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
    patient.value = null;
  }
}

const { loading } = useLiveLoad(load);
</script>

<style scoped>
.overview { display: grid; gap: 24px; }.overview__grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }.overview__grid > :last-child { grid-column: 1 / -1; }
@media (max-width: 900px) { .overview__grid { grid-template-columns: 1fr; }.overview__grid > :last-child { grid-column: auto; } }
</style>
