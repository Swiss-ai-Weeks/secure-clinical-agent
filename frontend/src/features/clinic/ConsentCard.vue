<template>
  <ClinicalCard v-if="visible" :title="title" eyebrow="Sharing">
    <p v-if="!patientKey" class="lede">No visible record on this session.</p>
    <div v-else class="consent">
      <p class="lede">Who can see this record, and for how long.</p>
      <p v-if="mode === 'error'" class="error" role="alert">{{ error }}</p>
      <div v-else class="consent__layout" :class="{ 'consent__layout--form': relations.length }">
        <section class="access" aria-labelledby="current-access-heading">
          <header class="section-head">
            <h3 id="current-access-heading">Current access</h3>
            <span>{{ consents.length }} {{ consents.length === 1 ? 'grant' : 'grants' }}</span>
          </header>
          <ul>
            <li v-for="row in rows" :key="row.key" :class="row.consent.status">
              <span class="avatar" aria-hidden="true">{{ row.initials }}</span>
              <div class="who">
                <strong>{{ row.name }}</strong>
                <small>{{ [row.level, row.relation, row.until].filter(Boolean).join(' · ') }}</small>
              </div>
              <div class="actions">
                <StatusPill :label="row.status" :tone="row.tone" />
                <button
                  v-if="row.consent.consent_id && row.consent.status === 'active'"
                  type="button"
                  class="revoke"
                  :disabled="busy"
                  :aria-busy="busy"
                  @click="revoke(row.consent.consent_id)"
                >Revoke</button>
              </div>
            </li>
            <li v-if="!consents.length" class="empty-row">
              <strong>No one has access yet</strong>
              <span>{{ emptyHint }}</span>
            </li>
          </ul>
        </section>
        <form v-if="relations.length" class="grant" @submit.prevent="grant">
          <header class="section-head">
            <h3>Grant new access</h3>
          </header>
          <div class="grant__fields">
            <div class="field">
              <label for="grant-who">Who</label>
              <select id="grant-who" v-model="grantee" required>
                <option disabled value="">Choose a person</option>
                <option v-for="persona in grantees" :key="persona.user_id" :value="persona.user_id">
                  {{ personAccessLabel(persona) }}
                </option>
              </select>
            </div>
            <div class="field">
              <label for="grant-relation">Access type</label>
              <select id="grant-relation" v-model="relation">
                <option v-for="item in relations" :key="item" :value="item">{{ relationLabel(item) }}</option>
              </select>
            </div>
            <div v-if="needsExpiry" class="field">
              <label for="grant-expiry">Expires</label>
              <input id="grant-expiry" v-model="expiry" type="date" required />
            </div>
            <div class="field">
              <label for="grant-justification">Justification</label>
              <input id="grant-justification" v-model="justification" type="text" placeholder="Optional — recorded in the audit log" />
            </div>
          </div>
          <p v-if="relationHint(relation)" class="hint">{{ relationHint(relation) }}</p>
          <div class="grant__actions">
            <button type="submit" :disabled="busy || !grantee" :aria-busy="busy">Grant</button>
          </div>
        </form>
      </div>
      <p v-if="error && mode === 'ready'" class="error" role="alert">{{ error }}</p>
    </div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import { apiClient } from '../../services/apiClient';
import {
  consentStatusLabel,
  consentStatusTone,
  defaultExpiryDate,
  expiryIso,
  expiryRequired,
  initialsFor,
  relationHint,
  relationLabel
} from '../../services/consents';
import { accessLevel, personAccessLabel } from '../../services/accessLevel';
import { formatLabDate } from '../../services/patientRecord';
import { ApiError } from '../../services/http';
import { useSessionStore } from '../../stores/useSessionStore';
import type { Consent } from '../../types/api';

const props = defineProps<{ patientKey: string; relations: string[]; title?: string }>();
const title = computed(() => props.title ?? 'Consents');
const session = useSessionStore();
const consents = ref<Consent[]>([]);
const error = ref('');
const busy = ref(false);
const mode = ref<'loading' | 'ready' | 'hidden' | 'error'>('loading');
const visible = computed(() => mode.value === 'ready' || mode.value === 'error');
const emptyHint = computed(() => (
  props.relations.includes('care_team')
    ? 'Delegate care-team or consultant access from the form.'
    : 'Grant a caregiver, notes-only access, or a block from the form.'
));
const grantee = ref('');
const relation = ref(props.relations[0] ?? '');
const expiry = ref(defaultExpiryDate());
const justification = ref('');
const needsExpiry = computed(() => expiryRequired(relation.value));
const grantees = computed(() => session.personas.filter(persona => persona.user_id !== session.me?.user_id));

const rows = computed(() => {
  const rank = (status: string) => (status === 'active' ? 0 : status === 'expired' ? 1 : 2);
  return [...consents.value]
    .sort((a, b) => rank(a.status) - rank(b.status) || a.grantee_user_id.localeCompare(b.grantee_user_id))
    .map(consent => {
      const persona = session.personas.find(entry => entry.user_id === consent.grantee_user_id);
      const name = persona?.display ?? 'Unknown user';
      const level = accessLevel(persona?.user_id === session.me?.user_id ? session.me : persona);
      return {
        consent,
        key: consent.consent_id ?? `${consent.relation}-${consent.grantee_user_id}`,
        name,
        level,
        initials: initialsFor(name, consent.grantee_user_id),
        relation: relationLabel(consent.relation),
        status: consentStatusLabel(consent.status),
        tone: consentStatusTone(consent.status),
        until: untilCopy(consent)
      };
    });
});

function untilCopy(consent: Consent): string {
  if (consent.relation === 'blocked') return 'Access denied';
  if (!consent.expiry) return 'No end date';
  const when = formatLabDate(consent.expiry);
  return consent.status === 'expired' ? `Ended ${when}` : `Until ${when}`;
}

function explain(err: unknown, fallback: string): string {
  if (err instanceof ApiError && (err.notFound || err.message === 'Resource not found')) {
    return 'This session cannot change sharing on this record.';
  }
  return err instanceof ApiError ? err.message : fallback;
}

async function load() {
  error.value = '';
  if (!props.patientKey) {
    consents.value = [];
    mode.value = 'ready';
    return;
  }
  mode.value = mode.value === 'ready' ? 'ready' : 'loading';
  try {
    consents.value = (await apiClient.listConsents(props.patientKey)).consents;
    mode.value = 'ready';
  } catch (err) {
    consents.value = [];
    if (err instanceof ApiError && err.notFound) {
      mode.value = 'hidden';
      return;
    }
    mode.value = 'error';
    error.value = explain(err, 'Could not load consents');
  }
}

async function grant() {
  error.value = '';
  busy.value = true;
  try {
    await apiClient.grantConsent({
      patient_key: props.patientKey,
      grantee_user_id: grantee.value,
      relation: relation.value,
      expiry: needsExpiry.value ? expiryIso(expiry.value) : undefined,
      justification: justification.value || undefined
    });
    justification.value = '';
    await load();
  } catch (err) {
    error.value = explain(err, 'Grant failed');
  } finally {
    busy.value = false;
  }
}

async function revoke(id: string) {
  error.value = '';
  busy.value = true;
  try {
    await apiClient.revokeConsent(id);
    await load();
  } catch (err) {
    error.value = explain(err, 'Revoke failed');
  } finally {
    busy.value = false;
  }
}

watch(() => [props.patientKey, props.relations.join(',')] as const, () => {
  relation.value = props.relations[0] ?? '';
  void load();
}, { immediate: true });
</script>

<style scoped>
.consent { display: grid; gap: 16px; }
.lede { margin: 0; color: var(--color-muted); }
.consent__layout { display: grid; gap: 18px; }
.consent__layout--form { grid-template-columns: minmax(0, 1.2fr) minmax(280px, .9fr); align-items: start; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.section-head h3 { margin: 0; font-size: 1rem; }
.section-head span { color: var(--color-muted); font-size: 13px; font-weight: 700; }
.access ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.access li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px 14px; align-items: center; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 14px 16px; }
.access li.active { box-shadow: inset 3px 0 0 var(--color-success); }
.access li.expired { background: var(--color-warning-soft); box-shadow: inset 3px 0 0 var(--color-warning); }
.access li.revoked { background: var(--color-danger-soft); box-shadow: inset 3px 0 0 var(--color-danger); }
.avatar { display: grid; width: 44px; height: 44px; place-items: center; border-radius: 50%; background: var(--color-accent-soft); color: var(--color-accent-ink); font-size: 14px; font-weight: 700; }
.who { min-width: 0; }
.who strong, .who small { display: block; }
.who strong { font-size: 1.02rem; }
.who small { margin-top: 2px; color: var(--color-muted); font-size: 13px; }
.actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 10px; }
.revoke { min-height: 36px; border: 1px solid rgb(180 35 24 / 28%); border-radius: var(--radius-pill); background: #fff; color: var(--color-danger); padding: 0 14px; font-weight: 650; cursor: pointer; }
.revoke:hover:not(:disabled) { background: var(--color-danger-soft); }
.revoke:disabled, .grant button:disabled { opacity: .55; cursor: not-allowed; }
.revoke:disabled[aria-busy], .grant button:disabled[aria-busy] { cursor: wait; }
.access li.empty-row { display: block; border-style: dashed; background: transparent; padding: 22px 16px; text-align: center; }
.empty-row strong, .empty-row span { display: block; }
.empty-row strong { color: var(--color-ink); }
.empty-row span { margin-top: 4px; color: var(--color-muted); font-size: 14px; }
.grant { display: grid; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-card); background: var(--color-surface-muted); padding: 18px; }
.grant__fields { display: grid; gap: 12px; }
.field { display: grid; gap: 6px; }
.grant label { color: var(--color-muted); font-size: 13px; font-weight: 650; }
.grant select, .grant input { width: 100%; min-height: 44px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); color: var(--color-ink); padding: 0 12px; }
.grant input::placeholder { color: #94a3b8; font-weight: 500; }
.hint { margin: 0; color: var(--color-muted); font-size: 13px; line-height: 1.4; }
.grant__actions { display: grid; }
.grant button { width: 100%; min-height: 44px; border: 0; border-radius: var(--radius-control); background: var(--color-accent); color: white; padding: 0 18px; font-weight: 700; cursor: pointer; }
.error { margin: 0; color: var(--color-danger); font-weight: 700; }
@media (max-width: 900px) {
  .consent__layout--form { grid-template-columns: 1fr; }
  .access li { grid-template-columns: auto minmax(0, 1fr); }
  .actions { grid-column: 2; justify-content: flex-start; }
}
</style>
