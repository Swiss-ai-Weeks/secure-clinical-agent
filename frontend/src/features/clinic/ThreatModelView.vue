<template>
  <section class="threat">
    <header>
      <p>Governance</p>
      <h1>Threat model</h1>
    </header>
    <article v-for="row in rows" :key="row.threat">
      <h2>{{ row.threat }}</h2>
      <p><strong>{{ row.status }}</strong> — {{ row.control }}</p>
    </article>
  </section>
</template>

<script setup lang="ts">
const rows = [
  { threat: 'Identity spoofing via prompt or tool args', status: 'closed', control: 'Identity from the run token or session only.' },
  { threat: 'Existence oracle', status: 'closed', control: 'Uniform 404 for unauthorized and nonexistent patients.' },
  { threat: 'Pixel exfiltration via tool', status: 'closed', control: 'Report-only /tools/imaging; /media/sign is dashboard-only.' },
  { threat: 'Indirect injection via notes', status: 'partial', control: 'Presidio + output citation rails; scoreboard stays honest.' },
  { threat: 'Aggregate differencing', status: 'partial', control: 'k-min, complementary suppression, overlap log.' },
  { threat: 'Diet orders imply diagnoses', status: 'residual', control: 'Ward and shift scoped; listed on this page.' }
];
</script>

<style scoped>
.threat { display: grid; gap: 16px; max-width: 900px; }
.threat header p { margin: 0; color: var(--color-muted); font-size: 14px; font-weight: 800; text-transform: uppercase; }
.threat article { border: 1px solid var(--color-line); border-radius: var(--radius-card); padding: 16px; }
.threat h2 { margin: 0 0 8px; font-size: 1.1rem; }
</style>
