<template>
  <section class="redteam">
    <header>
      <p>Governance</p>
      <h1>Red team</h1>
      <span>Honest scoreboard. Attack success rate {{ asr }} · {{ passed }} pass / {{ failed }} fail / {{ partial }} partial</span>
    </header>
    <article v-for="row in cases" :key="String(row.id)" :class="`tone-${row.result || 'catalogued'}`">
      <strong>{{ row.id }}</strong>
      <span>{{ row.owasp }} · {{ row.mpib || 'MPIB' }} · {{ row.expect }}</span>
      <em>{{ row.result || 'catalogued' }}</em>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { apiClient } from '../../services/apiClient';

const cases = ref<Array<Record<string, unknown>>>([]);
const passed = ref(0);
const failed = ref(0);
const partial = ref(0);
const asr = computed(() => {
  const n = cases.value.length;
  return n ? `${Math.round((failed.value / n) * 100)}%` : '—';
});

onMounted(async () => {
  const body = await apiClient.redteam();
  cases.value = body.cases;
  passed.value = Number(body.pass ?? cases.value.filter(row => row.result === 'pass').length);
  failed.value = Number(body.fail ?? cases.value.filter(row => row.result === 'fail').length);
  partial.value = Number(body.partial ?? cases.value.filter(row => row.result === 'partial').length);
});
</script>

<style scoped>
.redteam { display: grid; gap: 12px; max-width: 900px; }
.redteam header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.redteam article { display: grid; gap: 4px; border: 1px solid var(--color-line); border-radius: var(--radius-card); padding: 12px 16px; }
.tone-fail { border-color: #b42318; }
.tone-partial { border-color: #b54708; }
.tone-pass { border-color: #027a48; }
</style>
