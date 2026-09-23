<template>
  <section class="medications">
    <header><p>Patient 360</p><h1>Medications</h1></header>
    <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
    <template v-else-if="!loading">
      <ClinicalCard title="Current medications">
        <div v-if="currentMedications.length" class="medication-list">
          <article v-for="medication in currentMedications" :key="medication.id">
            <h2>{{ medication.name }}</h2>
            <p>{{ medication.dosage }} · {{ medication.frequency }}</p>
          </article>
        </div>
        <p v-else class="empty-copy">No current medications visible.</p>
      </ClinicalCard>
      <ClinicalCard title="Historical medications">
        <div v-if="historicalMedications.length" class="medication-list">
          <article v-for="medication in historicalMedications" :key="medication.id">
            <h2>{{ medication.name }}</h2>
            <p>{{ medication.dosage }}</p>
          </article>
        </div>
        <p v-else class="empty-copy">No historical medications recorded.</p>
      </ClinicalCard>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import ResourceNotFound from './ResourceNotFound.vue';

const route = useRoute();
const patient = ref<Patient | null>(null);
const missing = ref(false);
const currentMedications = computed(() => patient.value?.medications.filter(medication => medication.current) ?? []);
const historicalMedications = computed(() => patient.value?.medications.filter(medication => !medication.current) ?? []);

const { loading } = useLiveLoad(async () => {
  missing.value = false;
  try {
    patient.value = await apiClient.getPatient(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
    patient.value = null;
  }
});
</script>

<style scoped>
.medications { display: grid; gap: var(--space-5); max-width: 1000px; }
.medication-list { display: grid; gap: 0; }
.medication-list article {
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
}
.medication-list article:last-child { border-bottom: 0; }
.medication-list h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.medication-list p, .empty-copy {
  margin: var(--space-1) 0 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
</style>
