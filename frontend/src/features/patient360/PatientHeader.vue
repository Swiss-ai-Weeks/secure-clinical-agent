<template>
  <header class="patient-header">
    <div class="patient-header__identity"><div class="avatar">{{ patient.avatarInitials }}</div><div><p class="patient-header__eyebrow">Patient 360</p><h1>{{ patient.fullName }}</h1><p>{{ patient.age }} years · {{ patient.sex }} · {{ patient.patientId }} · {{ patient.assignedClinician }}</p></div></div>
    <div class="patient-header__status"><StatusPill :label="patient.status" tone="success" /><dl><div><dt>Blood type</dt><dd>{{ patient.bloodType }}</dd></div><div><dt>Allergies</dt><dd><span v-if="patient.majorAllergies.length" class="allergy"><strong>Severe allergy:</strong> {{ patient.majorAllergies.join(', ') }}</span><span v-else>None recorded</span></dd></div></dl></div>
    <div class="patient-header__lists"><section><h2>Conditions</h2><ul><li v-for="condition in patient.majorDiagnoses" :key="condition">{{ condition }}</li></ul></section><section><h2>Risk indicators</h2><ul><li v-for="risk in patient.riskIndicators" :key="risk">{{ risk }}</li></ul></section></div>
  </header>
</template>

<script setup lang="ts">
import type { Patient } from '../../types/patient360';
import StatusPill from '../../components/ui/StatusPill.vue';
defineProps<{ patient: Patient }>();
</script>

<style scoped>
.patient-header { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(250px, .9fr); gap: 20px; border: 1px solid var(--color-line); border-radius: var(--radius-panel); background: var(--color-surface); padding: 28px; box-shadow: var(--shadow-soft); }.patient-header__identity { display: flex; align-items: flex-start; gap: 16px; }.avatar { display: grid; flex: 0 0 60px; width: 60px; height: 60px; place-items: center; border-radius: 50%; background: var(--color-pink); font-weight: 850; }.patient-header__eyebrow { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }.patient-header h1 { margin: 2px 0; font-size: clamp(2rem, 4vw, 3.2rem); }.patient-header p { margin: 0; color: var(--color-muted); }.patient-header__status { display: grid; justify-items: start; gap: 14px; }.patient-header dl { display: grid; gap: 8px; margin: 0; }.patient-header dt { color: var(--color-muted); font-size: 14px; font-weight: 700; }.patient-header dd { margin: 0; }.allergy { color: var(--color-danger); }.patient-header__lists { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; border-top: 1px solid var(--color-line); padding-top: 16px; }.patient-header h2 { margin: 0 0 6px; font-size: 1rem; }.patient-header ul { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; }.patient-header li { border-radius: 999px; background: #f4efe5; padding: 5px 10px; font-size: 14px; }
@media (max-width: 650px) { .patient-header { grid-template-columns: 1fr; padding: 20px; }.patient-header__lists { grid-template-columns: 1fr; } }
</style>
