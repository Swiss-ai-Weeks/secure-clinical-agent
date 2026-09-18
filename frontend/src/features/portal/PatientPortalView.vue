<template>
  <section class="portal">
    <header>
      <p>Patient portal</p>
      <h1>Welcome{{ session.me?.display ? `, ${session.me.display}` : '' }}</h1>
      <span>Consents on your record. Other portal cards stay placeholders until later slices.</span>
    </header>
    <ClinicalCard title="Consents">
      <p v-if="!patientKey">No self patient on this session.</p>
      <ul v-else>
        <li v-for="consent in consents" :key="consent.consent_id ?? consent.relation + consent.grantee_user_id">
          {{ consent.grantee_user_id }} · {{ consent.relation }} · {{ consent.status }}
          <button v-if="consent.consent_id && consent.status === 'active'" type="button" @click="revoke(consent.consent_id)">Revoke</button>
        </li>
      </ul>
      <p v-if="error">{{ error }}</p>
    </ClinicalCard>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { Consent } from '../../types/api';

const session = useSessionStore();
const consents = ref<Consent[]>([]);
const error = ref('');
const patientKey = computed(() => session.me?.self_patient_id);

async function load() {
  if (!patientKey.value) return;
  try {
    consents.value = (await apiClient.listConsents(patientKey.value)).consents;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not load consents';
  }
}

async function revoke(id: string) {
  try {
    await apiClient.revokeConsent(id);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Revoke failed';
  }
}

onMounted(load);
</script>

<style scoped>
.portal { display: grid; gap: 20px; max-width: 1100px; }.portal header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.portal h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.portal ul { display: grid; gap: 8px; padding-left: 0; list-style: none; }
</style>
