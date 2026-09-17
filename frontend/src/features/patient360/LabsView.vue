<template>
  <section class="labs"><header><p>Patient 360</p><h1>Laboratory results</h1></header><AccessGate field="labs"><div class="labs__grid"><ClinicalCard title="LDL cholesterol trend"><Line :data="chartData" :options="chartOptions" /><div class="actions"><button type="button" @click="ask">✦ Explain trend</button><button type="button" @click="ask">✦ Compare with previous results</button><button type="button" @click="ask">✦ Find related history</button></div></ClinicalCard><ClinicalCard title="Latest results"><div class="results"><article v-for="lab in patient?.labs" :key="lab.id"><div><h2>{{ lab.label }}</h2><p>{{ lab.date }} · source {{ lab.sourceId }}</p></div><div><strong>{{ lab.value }} {{ lab.unit }}</strong><span>Reference {{ lab.referenceRange }} · previous {{ lab.previousValue ?? '—' }}</span><StatusPill :label="lab.abnormal ? 'Above reference range' : 'Within reference range'" :tone="lab.abnormal ? 'danger' : 'success'" /></div></article></div></ClinicalCard></div></AccessGate></section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { Chart as ChartJS, CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend } from 'chart.js';
import { Line } from 'vue-chartjs';
import { mockApi } from '../../services/mockApi';
import type { Patient } from '../../types/patient360';
import { useUiStore } from '../../stores/useUiStore';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import AccessGate from '../../components/access/AccessGate.vue';
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend);
const route = useRoute(); const ui = useUiStore(); const patient = ref<Patient | null>(null);
const chartData = { labels: ['Mar', 'Aug'], datasets: [{ label: 'LDL cholesterol (mmol/L)', data: [3.7, 4.2], borderColor: '#b42318', backgroundColor: '#f6b8c8', tension: .35 }] };
const chartOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { suggestedMin: 3, suggestedMax: 5 } } };
const ask = () => ui.openAskPanel(String(route.params.patientId));
onMounted(async () => { patient.value = await mockApi.getPatient(String(route.params.patientId)); });
</script>

<style scoped>
.labs { display: grid; gap: 20px; }.labs header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.labs h1 { margin: 4px 0; font-size: clamp(2rem, 4vw, 3rem); }.labs__grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 20px; }.labs :deep(canvas) { max-height: 270px; }.actions { display: grid; gap: 8px; margin-top: 16px; }.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; text-align: left; cursor: pointer; font-weight: 700; }.results { display: grid; gap: 10px; }.results article { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--color-line); padding-bottom: 12px; }.results article:last-child { border-bottom: 0; }.results h2 { margin: 0; font-size: 1.05rem; }.results p, .results span { display: block; margin: 4px 0; color: var(--color-muted); font-size: 14px; }.results strong { font-size: 1.1rem; } @media (max-width: 800px) { .labs__grid { grid-template-columns: 1fr; } }
</style>
