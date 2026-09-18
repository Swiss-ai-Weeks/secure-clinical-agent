<template>
  <ClinicalCard :title="title">
    <p v-if="!patientKey">No visible record on this session.</p>
    <template v-else>
      <ul>
        <li v-for="consent in consents" :key="consent.consent_id ?? consent.relation + consent.grantee_user_id">
          {{ consent.grantee_user_id }} · {{ consent.relation }} · {{ consent.status }}
          <button v-if="consent.consent_id && consent.status === 'active'" type="button" @click="revoke(consent.consent_id)">Revoke</button>
        </li>
        <li v-if="!consents.length">No consents on this record.</li>
      </ul>
      <form v-if="relations.length" class="grant" @submit.prevent="grant">
        <label>Grantee
          <select v-model="grantee" required>
            <option disabled value="">Choose a persona</option>
            <option v-for="persona in grantees" :key="persona.user_id" :value="persona.user_id">{{ persona.display }} · {{ persona.user_id }}</option>
          </select>
        </label>
        <label>Relation
          <select v-model="relation">
            <option v-for="item in relations" :key="item" :value="item">{{ item }}</option>
          </select>
        </label>
        <label v-if="needsExpiry">Expiry
          <input v-model="expiry" type="date" required />
        </label>
        <label>Justification
          <input v-model="justification" type="text" />
        </label>
        <button type="submit">Grant</button>
      </form>
      <p v-if="error">{{ error }}</p>
    </template>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { apiClient } from '../../services/apiClient';
import { defaultExpiryDate, expiryIso, expiryRequired } from '../../services/consents';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { Consent } from '../../types/api';

const props = defineProps<{ patientKey: string; relations: string[]; title?: string }>();
const title = computed(() => props.title ?? 'Consents');
const session = useSessionStore();
const consents = ref<Consent[]>([]);
const error = ref('');
const grantee = ref('');
const relation = ref(props.relations[0] ?? '');
const expiry = ref(defaultExpiryDate());
const justification = ref('');
const needsExpiry = computed(() => expiryRequired(relation.value));
const grantees = computed(() => session.personas.filter(persona => persona.user_id !== session.me?.user_id));

async function load() {
  error.value = '';
  consents.value = [];
  if (!props.patientKey) return;
  try {
    consents.value = (await apiClient.listConsents(props.patientKey)).consents;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Could not load consents';
  }
}

async function grant() {
  error.value = '';
  try {
    await apiClient.grantConsent({
      patient_key: props.patientKey,
      grantee_user_id: grantee.value,
      relation: relation.value,
      expiry: needsExpiry.value ? expiryIso(expiry.value) : undefined,
      justification: justification.value || undefined
    });
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Grant failed';
  }
}

async function revoke(id: string) {
  error.value = '';
  try {
    await apiClient.revokeConsent(id);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Revoke failed';
  }
}

watch(() => [props.patientKey, props.relations.join(',')] as const, () => {
  relation.value = props.relations[0] ?? '';
  void load();
}, { immediate: true });
</script>

<style scoped>
ul { display: grid; gap: 8px; padding-left: 0; list-style: none; }
.grant { display: grid; gap: 10px; margin-top: 16px; }
.grant select, .grant input, .grant button { min-height: 40px; }
button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 12px; cursor: pointer; }
</style>
