<template>
  <ClinicalCard title="✦ Clinical Brief" :ai="true">
    <AccessGateMulti :fields="['majorDiagnoses', 'labs']"><ul class="brief"><li v-for="statement in briefStatements" :key="statement">{{ statement }}</li></ul></AccessGateMulti>
    <div class="actions"><button type="button">View sources</button><button type="button">Regenerate summary</button><button type="button" class="actions__primary" @click="ui.openAskPanel(patient.id)">Ask follow-up</button></div>
  </ClinicalCard>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import AccessGateMulti from '../../components/access/AccessGateMulti.vue';
import { useUiStore } from '../../stores/useUiStore';
const props = defineProps<{ patient: Patient }>();
const ui = useUiStore();

/**
 * Derives the three-line brief from the patient's own majorDiagnoses/labs —
 * and ONLY those two fields, matching exactly what AccessGateMulti above
 * checks. Pulling from any other field (medications, riskIndicators,
 * riskAssessment, ...) here would leak that field's content to a role the
 * gate never checked for it — the same leak pattern already fixed once in
 * this component (see CurrentSnapshot.vue / SinceLastVisit.vue history).
 */
function buildBriefStatements(patient: Patient): string[] {
  const first = patient.fullName.split(' ')[0];
  const lines: string[] = [];

  if (patient.majorDiagnoses.length > 0) {
    const [primary, ...rest] = patient.majorDiagnoses;
    lines.push(
      rest.length
        ? `${first}'s primary diagnosis is ${primary}, alongside ${rest.join(', ')}.`
        : `${first}'s primary diagnosis is ${primary}, which remains the focus of ongoing care.`
    );
  } else {
    lines.push(`${first} has no active diagnoses on file.`);
  }

  const abnormalLab = patient.labs.find(lab => lab.abnormal);
  if (abnormalLab) {
    const trendWord = abnormalLab.trend === 'up' ? 'increased' : abnormalLab.trend === 'down' ? 'decreased' : 'changed';
    const comparison = abnormalLab.previousValue ? ` from ${abnormalLab.previousValue} ${abnormalLab.unit} previously` : '';
    lines.push(`${first}'s latest ${abnormalLab.label} is ${abnormalLab.value} ${abnormalLab.unit}, outside the reference range of ${abnormalLab.referenceRange}, having ${trendWord}${comparison}.`);
  } else if (patient.labs.length > 0) {
    const lab = patient.labs[0];
    lines.push(`${first}'s latest ${lab.label} is ${lab.value} ${lab.unit}, within the reference range of ${lab.referenceRange}.`);
  } else {
    lines.push('No new lab results have been recorded since the last visit.');
  }

  lines.push(abnormalLab ? 'No other lab flags have been documented beyond the result noted above.' : 'No abnormal lab flags have been documented.');

  return lines;
}

const briefStatements = computed(() => buildBriefStatements(props.patient));
</script>

<style scoped>
.brief { display: grid; gap: 12px; margin: 0; padding-left: 22px; }.brief li::marker { content: '✦  '; color: var(--color-warning); }.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 20px; }.actions button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-surface); padding: 0 12px; cursor: pointer; font-weight: 700; }.actions .actions__primary { border-color: var(--color-plum); background: var(--color-plum); color: white; }
</style>
