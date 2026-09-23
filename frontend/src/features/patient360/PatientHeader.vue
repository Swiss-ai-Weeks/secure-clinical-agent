<template>
  <header class="patient-header" :class="{ highlighted: ui.highlightedSourceId === 'identity_banner' }">
    <div class="patient-header__identity">
      <div class="avatar">{{ patient.avatarInitials }}</div>
      <div>
        <p class="patient-header__eyebrow">{{ session.workspace === 'family' ? 'Family record' : 'Patient chart' }}</p>
        <h1>{{ patient.fullName }}</h1>
        <p>{{ identity }}</p>
      </div>
    </div>
    <div class="patient-header__status">
      <StatusPill :label="patient.status" tone="success" />
      <dl>
        <div><dt>Date of birth</dt><dd>{{ dob }}</dd></div>
        <div><dt>Allergies</dt><dd><span v-if="patient.majorAllergies.length" class="allergy">{{ patient.majorAllergies.join(', ') }}</span><span v-else>None recorded</span></dd></div>
      </dl>
      <StatusPill v-if="patient.warning === 'Break-glass active'" :label="patient.warning" tone="danger" />
    </div>
    <div class="patient-header__lists">
      <section>
        <h2>Conditions</h2>
        <ul>
          <li v-for="condition in patient.majorDiagnoses" :key="condition">{{ condition }}</li>
          <li v-if="!patient.majorDiagnoses.length" class="empty">None recorded</li>
        </ul>
      </section>
      <section>
        <h2>Location</h2>
        <ul>
          <li v-if="patient.placement">{{ patient.placement }}</li>
          <li v-else class="empty">No current ward placement</li>
        </ul>
      </section>
      <section v-if="session.workspace === 'clinical'">
        <h2>Risk indicators</h2>
        <ul>
          <li v-for="risk in patient.riskIndicators" :key="risk" class="risk">{{ risk }}</li>
          <li v-if="!patient.riskIndicators.length" class="empty">None on visible rows</li>
        </ul>
      </section>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { Patient } from '../../types/patient360';
import { formatLabDate, identityLine } from '../../services/patientRecord';
import StatusPill from '../../components/ui/StatusPill.vue';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUiStore } from '../../stores/useUiStore';

const props = defineProps<{ patient: Patient }>();
const session = useSessionStore();
const ui = useUiStore();
const identity = computed(() => identityLine(props.patient));
const dob = computed(() => props.patient.dateOfBirth ? formatLabDate(props.patient.dateOfBirth) : 'Not on the identity banner');
</script>

<style scoped>
.patient-header {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(220px, .85fr);
  gap: var(--space-6);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
  padding: var(--space-6) var(--space-7);
  box-shadow: var(--shadow-soft);
}
.patient-header.highlighted {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}
.patient-header__identity {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  min-width: 0;
}
.avatar {
  display: grid;
  flex: 0 0 52px;
  width: 52px;
  height: 52px;
  place-items: center;
  border-radius: 14px;
  background: var(--color-accent-soft);
  color: var(--color-accent-ink);
  font-size: var(--text-sm);
  font-weight: 600;
}
.patient-header__eyebrow {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.patient-header h1 {
  margin: var(--space-1) 0;
  font-size: var(--text-3xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  line-height: var(--leading-tight);
}
.patient-header p { margin: 0; color: var(--color-muted); font-size: var(--text-sm); }
.patient-header__status {
  display: grid;
  justify-items: start;
  align-content: start;
  gap: var(--space-4);
}
.patient-header dl { display: grid; gap: var(--space-3); margin: 0; }
.patient-header dt {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.patient-header dd { margin: 2px 0 0; font-weight: 550; font-size: var(--text-sm); }
.allergy { color: var(--color-danger); }
.patient-header__lists {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-5);
  border-top: 1px solid var(--color-line);
  padding-top: var(--space-5);
}
.patient-header h2 {
  margin: 0 0 var(--space-2);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-muted);
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.patient-header ul {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  list-style: none;
}
.patient-header li {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-muted);
  padding: 0 10px;
  font-size: var(--text-sm);
  font-weight: 500;
  line-height: 1;
}
.patient-header li.risk { background: var(--color-danger-soft); color: var(--color-danger); }
.patient-header li.empty {
  background: transparent;
  color: var(--color-muted);
  padding-left: 0;
  min-height: auto;
}
@media (max-width: 900px) { .patient-header__lists { grid-template-columns: 1fr; } }
@media (max-width: 650px) { .patient-header { grid-template-columns: 1fr; padding: var(--space-5); } }
</style>
