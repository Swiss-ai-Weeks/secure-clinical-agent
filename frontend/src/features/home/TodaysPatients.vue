<template>
  <ClinicalCard title="Today's patients"><div class="patients"><RouterLink v-for="patient in patients" :key="patient.id" class="patient" :to="`/patients/${patient.id}/overview`"><span class="avatar">{{ patient.avatarInitials }}</span><span><strong>{{ patient.fullName }}</strong><small>{{ patient.age }} years · {{ patient.appointmentTime }} · {{ patient.appointmentType }}</small><small>{{ patient.reasonForVisit }}</small><em v-if="patient.warning">{{ patient.warning }}</em></span><span aria-hidden="true">→</span></RouterLink></div></ClinicalCard>
</template>
<script setup lang="ts">
import { RouterLink } from 'vue-router';
import type { PatientSummary } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
defineProps<{ patients: PatientSummary[] }>();
</script>
<style scoped>
.patients { display: grid; gap: 10px; }.patient { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); color: var(--color-plum); padding: 12px; text-decoration: none; }.patient:hover { border-color: var(--color-pink); background: var(--color-pink-soft); }.avatar { display: grid; width: 42px; height: 42px; place-items: center; border-radius: 50%; background: var(--color-pink); font-size: 14px; font-weight: 850; }.patient strong, .patient small, .patient em { display: block; }.patient small { margin-top: 2px; color: var(--color-muted); font-size: 14px; }.patient em { margin-top: 5px; color: var(--color-danger); font-size: 14px; font-style: normal; font-weight: 700; }
</style>
