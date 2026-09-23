<template>
  <ClinicalCard title="Today's patients">
    <div class="patients">
      <RouterLink v-for="patient in patients" :key="patient.id" class="patient" :to="`/patients/${patient.id}/overview`">
        <span class="avatar">{{ patient.avatarInitials }}</span>
        <span>
          <strong>{{ patient.fullName }}</strong>
          <small>
            {{ [patient.age ? `${patient.age} years` : '', patient.dateOfBirth].filter(Boolean).join(' · ') }}
            <template v-if="patient.appointmentTime"> · {{ patient.appointmentTime }}</template>
            <template v-if="doctor(patient)"> · {{ doctor(patient) }}</template>
            <template v-if="patient.appointmentType"> · {{ patient.appointmentType }}</template>
          </small>
          <small v-if="patient.reasonForVisit">{{ patient.reasonForVisit }}</small>
          <em v-if="patient.warning">{{ patient.warning }}</em>
        </span>
        <span class="chevron" aria-hidden="true">→</span>
      </RouterLink>
      <p v-if="!patients.length" class="empty">No patients are visible on this session.</p>
    </div>
  </ClinicalCard>
</template>
<script setup lang="ts">
import { RouterLink } from 'vue-router';
import type { PatientSummary } from '../../types/patient360';
import { practitionerName } from '../../services/dashboard';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import { useSessionStore } from '../../stores/useSessionStore';
const session = useSessionStore();
defineProps<{ patients: PatientSummary[] }>();

function doctor(patient: PatientSummary): string {
  return practitionerName(patient.appointmentClinician, session.personas);
}
</script>
<style scoped>
.patients { display: grid; gap: var(--space-2); }
.patient {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--space-3);
  border: 1px solid var(--color-line);
  border-radius: 12px;
  color: var(--color-ink);
  padding: var(--space-3) var(--space-4);
  text-decoration: none;
  transition: border-color 140ms ease, background 140ms ease, box-shadow 140ms ease;
}
.patient:hover {
  border-color: rgb(29 78 216 / 28%);
  background: var(--color-accent-soft);
  box-shadow: var(--shadow-soft);
}
.avatar {
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 50%;
  background: var(--color-accent-soft);
  color: var(--color-accent-ink);
  font-size: var(--text-sm);
  font-weight: 600;
}
.patient strong, .patient small, .patient em { display: block; }
.patient strong {
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
}
.patient small {
  margin-top: 2px;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
.patient em {
  margin-top: var(--space-1);
  color: var(--color-danger);
  font-size: var(--text-sm);
  font-style: normal;
  font-weight: 600;
}
.chevron { color: var(--color-muted); font-size: var(--text-md); }
.empty { margin: 0; color: var(--color-muted); font-size: var(--text-sm); }
</style>
