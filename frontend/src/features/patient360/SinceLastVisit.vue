<template>
  <ClinicalCard title="Since your last consultation">
    <div class="changes">
      <button v-for="change in ungatedChanges" :key="change.label" type="button" @click="ui.highlightSource(change.target)"><span>{{ change.label }}</span><span aria-hidden="true">→</span></button>
      <AccessGateMulti :fields="['labs', 'medications']">
        <button v-for="change in gatedChanges" :key="change.label" type="button" @click="ui.highlightSource(change.target)"><span>{{ change.label }}</span><span aria-hidden="true">→</span></button>
      </AccessGateMulti>
    </div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGateMulti from '../../components/access/AccessGateMulti.vue';
import { useUiStore } from '../../stores/useUiStore.js';
const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();

interface Change { label: string; target: string }

// Generic, non-lab/medication facts — visible to every role. Sourced only
// from fields that are ALREADY shown ungated elsewhere (majorAllergies,
// reasonForVisit) — never from riskIndicators, which is itself only ever
// shown behind a labs/majorDiagnoses gate elsewhere (PatientHeader), so
// pulling it in here unguarded would reintroduce the same leak this file's
// gated half was just fixed for.
const ungatedChanges = computed<Change[]>(() => [
  props.patient.majorAllergies.length
    ? { label: `Known allergy on file: ${props.patient.majorAllergies.join(', ')}`, target: 'allergies' }
    : { label: 'No allergies on file', target: 'allergies' },
  props.patient.reasonForVisit
    ? { label: `Visit reason: ${props.patient.reasonForVisit}`, target: 'reason-for-visit' }
    : { label: 'No specific visit reason recorded', target: 'reason-for-visit' }
]);

// Lab- and medication-derived facts — pulled only from the two fields
// AccessGateMulti below already checks (labs, medications). Adding a new
// data source here would mean the gate needs updating too; this fix
// intentionally doesn't touch the gate itself.
const gatedChanges = computed<Change[]>(() => {
  const changes: Change[] = [];

  const abnormalLab = props.patient.labs.find(lab => lab.abnormal);
  if (abnormalLab) {
    const trendWord = abnormalLab.trend === 'up' ? 'increased' : abnormalLab.trend === 'down' ? 'decreased' : 'changed';
    changes.push({ label: `${abnormalLab.label} ${trendWord} to ${abnormalLab.value} ${abnormalLab.unit}`, target: abnormalLab.sourceId || abnormalLab.id });
  } else if (props.patient.labs.length > 0) {
    const lab = props.patient.labs[0];
    changes.push({ label: `${props.patient.labs.length} lab result${props.patient.labs.length > 1 ? 's' : ''} on file, within range`, target: lab.sourceId || lab.id });
  } else {
    changes.push({ label: 'No new laboratory results', target: 'labs' });
  }

  const currentMeds = props.patient.medications.filter(medication => medication.current);
  changes.push(
    currentMeds.length
      ? { label: `Current medications: ${currentMeds.map(medication => medication.name).join(', ')}`, target: 'medications' }
      : { label: 'No clinician-entered medication changes', target: 'medications' }
  );

  return changes;
});
</script>

<style scoped>
.changes { display: grid; gap: 8px; }.changes button { display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 10px 14px; text-align: left; cursor: pointer; }.changes button:hover { border-color: var(--color-pink); background: var(--color-pink-soft); }
</style>
