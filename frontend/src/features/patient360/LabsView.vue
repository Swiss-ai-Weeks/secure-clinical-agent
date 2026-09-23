<template>
  <section class="labs">
    <header>
      <p>Patient 360</p>
      <h1>Laboratory results</h1>
      <span v-if="!loading && !missing">{{ resultCountLabel }}</span>
    </header>
    <ResourceNotFound v-if="missing" :patient-key="String(route.params.patientId)" />
    <div v-else class="labs__grid">
      <div v-if="!loading" class="labs__toolbar">
        <div class="labs__search">
          <label for="labs-search">Search results</label>
          <input
            id="labs-search"
            v-model="query"
            type="search"
            placeholder="Analyte, unit, or flag"
            autocomplete="off"
          />
        </div>
        <LargeTabs v-model="flagFilter" label="Flag filters" :items="flagFilters" />
      </div>
      <ClinicalCard title="Latest results">
        <div v-if="!loading" class="results">
          <article v-for="group in filteredGroups" :key="group.latest.id">
            <div class="primary" aria-label="Latest result">
              <div class="name">
                <h2>{{ group.label }}</h2>
                <p class="when">{{ formatLabDate(group.latest.date) }}</p>
              </div>
              <strong class="num">{{ group.latest.value }}</strong>
              <span class="unit">{{ group.latest.unit }}</span>
              <StatusPill
                :label="labFlagLabel(group.latest.flag)"
                :tone="group.latest.flag === 'high' || group.latest.flag === 'low' ? (group.latest.flag === 'high' ? 'danger' : 'warning') : group.latest.flag === 'normal' ? 'success' : 'neutral'"
              />
              <span v-if="group.latest.referenceRange" class="ref">Reference {{ group.latest.referenceRange }}</span>
            </div>
            <div v-if="group.prior.length" class="history">
              <p class="history__label">Earlier results</p>
              <ul class="history__list">
                <li v-for="item in visiblePrior(group)" :key="item.id">
                  <span class="history__value">
                    <span class="num">{{ item.value }}</span>
                    <span v-if="item.unit" class="unit">{{ item.unit }}</span>
                  </span>
                  <span class="history__date">{{ formatLabDate(item.date) }}</span>
                </li>
              </ul>
              <button
                v-if="hiddenCount(group) > 0"
                type="button"
                class="history__more"
                :aria-expanded="isExpanded(group.label)"
                @click="toggleEarlier(group.label)"
              >
                {{ isExpanded(group.label) ? 'Show fewer results' : `Show earlier results (${hiddenCount(group)})` }}
              </button>
            </div>
          </article>
          <p v-if="!filteredGroups.length" class="empty">{{ emptyCopy }}</p>
        </div>
      </ClinicalCard>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { formatLabDate, groupLabs, labFlagLabel } from '../../services/patientRecord';
import { ApiError } from '../../services/http';
import type { LabResult, Patient } from '../../types/patient360';
import ClinicalCard from '../../components/ui/ClinicalCard.vue';
import LargeTabs from '../../components/ui/LargeTabs.vue';
import StatusPill from '../../components/ui/StatusPill.vue';
import ResourceNotFound from './ResourceNotFound.vue';

const PRIOR_VISIBLE = 3;

const route = useRoute();
const patient = ref<Patient | null>(null);
const missing = ref(false);
const query = ref('');
const flagFilter = ref('all');
const expanded = reactive<Record<string, boolean>>({});
const groups = computed(() => groupLabs(patient.value?.labs ?? []));
const flagFilters = computed(() => {
  const items = [
    { label: 'All', value: 'all' },
    { label: 'High', value: 'high' },
    { label: 'Low', value: 'low' },
    { label: 'In range', value: 'normal' }
  ];
  if (groups.value.some(group => group.latest.flag === 'unknown')) {
    items.push({ label: 'Recorded', value: 'unknown' });
  }
  return items;
});
const filteredGroups = computed(() => {
  const needle = query.value.trim().toLowerCase();
  const flag = flagFilter.value;
  return groups.value.filter(group => {
    if (flag !== 'all' && group.latest.flag !== flag) return false;
    if (needle && !labGroupHaystack(group).includes(needle)) return false;
    return true;
  });
});
const filtering = computed(() => query.value.trim().length > 0 || flagFilter.value !== 'all');
const resultCountLabel = computed(() => {
  const shown = filteredGroups.value.length;
  const total = groups.value.length;
  if (filtering.value) return `${shown} of ${total} results`;
  return total === 1 ? '1 result' : `${total} results`;
});
const emptyCopy = computed(() => (
  filtering.value && groups.value.length
    ? 'No laboratory results match this filter.'
    : 'No visible laboratory rows.'
));

watch(flagFilters, items => {
  if (!items.some(item => item.value === flagFilter.value)) flagFilter.value = 'all';
});

function labGroupHaystack(group: { label: string; latest: LabResult }): string {
  return [group.label, group.latest.unit, labFlagLabel(group.latest.flag)]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function isExpanded(label: string): boolean {
  return Boolean(expanded[label]);
}

function toggleEarlier(label: string): void {
  expanded[label] = !expanded[label];
}

function hiddenCount(group: { prior: LabResult[] }): number {
  return Math.max(0, group.prior.length - PRIOR_VISIBLE);
}

function visiblePrior(group: { label: string; prior: LabResult[] }): LabResult[] {
  if (isExpanded(group.label) || group.prior.length <= PRIOR_VISIBLE) {
    return group.prior;
  }
  return group.prior.slice(0, PRIOR_VISIBLE);
}

const { loading } = useLiveLoad(async () => {
  missing.value = false;
  try {
    patient.value = await apiClient.getPatient(String(route.params.patientId));
  } catch (error) {
    missing.value = error instanceof ApiError && error.notFound;
    patient.value = null;
  }
});
</script>

<style scoped>
.labs {
  display: grid;
  gap: var(--space-5);
  max-width: 920px;
}
.labs__grid { display: grid; gap: var(--space-5); }
.labs header span {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
.labs__toolbar { display: grid; gap: var(--space-4); }
.labs__search { display: grid; gap: 10px; }
.labs__search label { font-weight: 650; }
.labs__search input { min-height: 44px; width: 100%; }
.results { display: grid; gap: 0; }
.results article {
  display: grid;
  gap: var(--space-3);
  border-bottom: 1px solid var(--color-line);
  padding: var(--space-4) 0;
  min-width: 0;
}
.results article:last-child { border-bottom: 0; }

.primary {
  display: grid;
  /* Shared track sizes so value / unit / flag columns line up across analytes */
  grid-template-columns:
    minmax(7.5rem, 1.15fr)
    5.75rem
    4.5rem
    5.5rem
    minmax(6.5rem, 1fr);
  align-items: center;
  column-gap: var(--space-3);
  row-gap: var(--space-1);
  min-width: 0;
}

.name {
  min-width: 0;
  grid-column: 1;
}
.results h2 {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: var(--leading-snug);
}
.when {
  margin: var(--space-1) 0 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}

.num {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
.primary > .num {
  grid-column: 2;
  justify-self: end;
  margin: 0;
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: -0.015em;
  line-height: 1;
  color: var(--color-ink);
}
.primary > .unit {
  grid-column: 3;
  color: var(--color-muted-strong);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
  line-height: 1;
  white-space: nowrap;
  min-height: 1em;
}
.primary :deep(.pill) {
  grid-column: 4;
  justify-self: start;
  align-self: center;
}
.ref {
  grid-column: 5;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
  white-space: nowrap;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history {
  grid-column: 1 / -1;
  padding-left: 0;
  min-width: 0;
}
.history__label {
  margin: 0 0 var(--space-2);
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
  line-height: var(--leading-tight);
}
.history__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--space-1);
  max-width: 28rem;
}
.history__list li {
  display: grid;
  grid-template-columns: 5.75rem 4.5rem minmax(6rem, 1fr);
  align-items: baseline;
  column-gap: var(--space-3);
  min-width: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
  color: var(--color-ink);
}
.history__value {
  display: contents;
}
.history__value .num {
  grid-column: 1;
  justify-self: end;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum";
}
.history__value .unit {
  grid-column: 2;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.history__date {
  grid-column: 3;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
  white-space: nowrap;
}
.history__more {
  margin: var(--space-2) 0 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-accent);
  font: inherit;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.history__more:hover { color: var(--color-accent-hover); }
.history__more:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: 4px;
}

.empty { margin: 0; color: var(--color-muted); }

@media (max-width: 700px) {
  .primary {
    grid-template-columns: minmax(0, 1fr) auto auto auto;
  }
  .name { grid-column: 1 / -1; }
  .primary > .num { grid-column: 1; justify-self: start; }
  .primary > .unit { grid-column: 2; }
  .primary :deep(.pill) { grid-column: 3; }
  .ref {
    grid-column: 1 / -1;
    white-space: normal;
  }
  .history__list { max-width: none; }
}
</style>
