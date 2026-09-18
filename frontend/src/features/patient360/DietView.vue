<template>
  <section class="diet">
    <header><p>Patient 360</p><h1>Diet and food allergies</h1></header>
    <p v-if="missing">Resource not found</p>
    <div v-else class="grid">
      <ClinicalCard title="Diet orders">
        <ul><li v-for="row in diet" :key="String(row.cite_id)">{{ row.ward }} · {{ Array.isArray(row.diet_codes) ? row.diet_codes.join(', ') : row.diet_codes }}</li></ul>
      </ClinicalCard>
      <ClinicalCard title="Allergies">
        <ul><li v-for="row in allergies" :key="String(row.cite_id)">{{ row.redacted ? 'Redacted' : row.display }}</li></ul>
      </ClinicalCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';

const route = useRoute();
const diet = ref<Array<Record<string, unknown>>>([]);
const allergies = ref<Array<Record<string, unknown>>>([]);
const missing = ref(false);

onMounted(async () => {
  const key = String(route.params.patientId);
  try {
    const [dietQ, allergyQ] = await Promise.all([
      apiClient.query('diet', { patient_key: key }).catch(err => { if (err instanceof ApiError && err.notFound) return null; throw err; }),
      apiClient.query('allergies', { patient_key: key }).catch(err => { if (err instanceof ApiError && err.notFound) return null; throw err; })
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
.diet { display: grid; gap: 20px; }.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; } @media (max-width: 800px) { .grid { grid-template-columns: 1fr; } }
</style>
