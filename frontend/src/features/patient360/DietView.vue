<template>
  <section class="diet">
    <header>
      <p>{{ session.workspace === 'kitchen' ? 'Kitchen' : 'Patient 360' }}</p>
      <h1>Diet and food allergies</h1>
    </header>
    <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
    <div v-else-if="!loading" class="grid">
      <ClinicalCard title="Diet orders">
        <ul>
          <li v-for="row in diet" :key="String(row.cite_id)">{{ formatDietOrder(row) }}</li>
          <li v-if="!diet.length" class="empty">No diet order on this chart. Only an admitted ward stay carries a NutritionOrder.</li>
        </ul>
      </ClinicalCard>
      <ClinicalCard :title="session.hasPanel('allergies_food') ? 'Food allergies' : 'Allergies'">
        <ul>
          <li v-for="row in allergies" :key="String(row.cite_id)">{{ row.redacted ? 'REDACT' : row.display }}</li>
          <li v-if="!allergies.length" class="empty">No known allergies.</li>
        </ul>
      </ClinicalCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import ResourceNotFound from './ResourceNotFound.vue';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { formatDietOrder } from '../../services/patientRecord';
import { allergyQueryDataset } from '../../services/workspace';
import { useSessionStore } from '../../stores/useSessionStore';

const route = useRoute();
const session = useSessionStore();
const diet = ref<Array<Record<string, unknown>>>([]);
const allergies = ref<Array<Record<string, unknown>>>([]);
const missing = ref(false);

const { loading } = useLiveLoad(async () => {
  const key = String(route.params.patientId);
  missing.value = false;
  const allergyDataset = allergyQueryDataset(session.panels);
  try {
    const [dietQ, allergyQ] = await Promise.all([
      apiClient.query('diet', { patient_key: key }).catch(err => { if (err instanceof ApiError && err.notFound) return null; throw err; }),
      allergyDataset
        ? apiClient.query(allergyDataset, { patient_key: key }).catch(err => { if (err instanceof ApiError && err.notFound) return null; throw err; })
        : Promise.resolve(null)
    ]);
    if (!dietQ && !allergyQ) missing.value = true;
    diet.value = dietQ?.rows ?? [];
    allergies.value = allergyQ?.rows ?? [];
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
  }
});
</script>

<style scoped>
.diet { display: grid; gap: 20px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.empty { color: var(--color-muted); list-style: none; margin-left: 0; padding-left: 0; }
@media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
