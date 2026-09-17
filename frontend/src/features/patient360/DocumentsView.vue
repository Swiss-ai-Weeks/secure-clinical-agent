<template>
  <section class="documents"><header><p>Patient 360</p><h1>Documents</h1><label class="upload" for="upload-document">Upload document<input id="upload-document" aria-label="Upload document" type="file" @change="upload" /></label></header><ClinicalCard title="Patient documents"><AccessGate field="documents"><div class="documents__list"><article v-for="document in patient?.documents" :key="document.id"><div><h2>{{ document.title }}</h2><p>{{ document.type }} · {{ document.date }} · {{ document.source }}</p></div><div><StatusPill :label="document.processingState" :tone="document.processingState === 'processed' ? 'success' : 'warning'" /><span>Uploaded by {{ document.uploadedBy }}</span></div></article></div></AccessGate></ClinicalCard><ClinicalCard v-if="facts.length" title="Information detected" :ai="true"><AccessGateMulti :fields="['majorDiagnoses', 'medications']"><div class="facts"><article v-for="fact in facts" :key="fact.id"><div><strong>{{ fact.label }}</strong><p>{{ fact.value }}</p><span v-if="fact.status === 'accepted'">Accepted into review queue</span><span v-else-if="fact.status !== 'pending'">{{ fact.status }}</span></div><div class="fact-actions"><button type="button" @click="decide(fact.id, 'accepted')">Accept</button><button type="button" @click="decide(fact.id, 'edited')">Edit</button><button type="button" @click="decide(fact.id, 'rejected')">Reject</button></div></article></div></AccessGateMulti></ClinicalCard></section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { mockApi } from '../../services/mockApi';
import type { ExtractedFact, Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import AccessGateMulti from '../../components/access/AccessGateMulti.vue';
import AccessGate from '../../components/access/AccessGate.vue';
const route = useRoute(); const patient = ref<Patient | null>(null); const facts = ref<ExtractedFact[]>([]); const patientId = String(route.params.patientId);
onMounted(async () => { patient.value = await mockApi.getPatient(patientId); });
async function upload(event: Event) { const file = (event.target as HTMLInputElement).files?.[0]; if (!file) return; facts.value = (await mockApi.uploadDocument(patientId, file.name)).extractedFacts; }
async function decide(factId: string, decision: 'accepted' | 'edited' | 'rejected') { await mockApi.applyExtractedFact(patientId, factId, decision); facts.value = facts.value.map(fact => fact.id === factId ? { ...fact, status: decision } : fact); }
</script>

<style scoped>
.documents { display: grid; gap: 20px; max-width: 1000px; }.documents header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; }.documents header p { width: 100%; margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.documents h1 { margin: 0; font-size: clamp(2rem, 4vw, 3rem); }.upload { display: inline-flex; align-items: center; min-height: 44px; border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 16px; cursor: pointer; font-weight: 750; }.upload input { position: absolute; width: 1px; height: 1px; opacity: 0; }.documents__list, .facts { display: grid; gap: 12px; }.documents__list article, .facts article { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--color-line); padding-bottom: 12px; }.documents__list article:last-child, .facts article:last-child { border-bottom: 0; }.documents h2 { margin: 0; font-size: 1.1rem; }.documents p, .documents span { display: block; margin: 4px 0; color: var(--color-muted); font-size: 14px; }.facts span { color: var(--color-success); font-weight: 750; }.fact-actions { display: flex; flex-wrap: wrap; align-content: start; gap: 8px; }.fact-actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 10px; cursor: pointer; }.fact-actions button:first-child { background: var(--color-plum); color: white; }
</style>
