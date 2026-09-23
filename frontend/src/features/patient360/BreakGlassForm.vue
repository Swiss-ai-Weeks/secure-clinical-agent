<template>
  <form class="btg" @submit.prevent="openGlass">
    <p>Emergency access for this chart. Requires AAL2, a typed justification, and writes a time-boxed emergency grant that is audited as break-glass.</p>
    <label>Break-glass justification
      <textarea v-model="justification" required minlength="20" rows="3" />
    </label>
    <button type="submit" :disabled="pending">Open break-glass</button>
    <p v-if="error" class="btg__error">{{ error }}</p>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';

const props = defineProps<{ patientKey: string }>();
const router = useRouter();
const justification = ref('');
const error = ref('');
const pending = ref(false);

async function openGlass() {
  error.value = '';
  pending.value = true;
  try {
    await apiClient.breakGlass(props.patientKey, justification.value);
    const dest = `/patients/${props.patientKey}/overview`;
    if (router.currentRoute.value.path !== dest) await router.push(dest);
    location.reload();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Break-glass failed';
  } finally {
    pending.value = false;
  }
}
</script>

<style scoped>
.btg { display: grid; gap: 8px; max-width: 420px; color: var(--color-ink); }
.btg p { margin: 0; }
.btg textarea { width: 100%; border: 1px solid var(--color-line); border-radius: var(--radius-control); padding: 8px; }
.btg button { border: 0; border-radius: var(--radius-control); background: var(--color-accent); color: white; padding: 0 12px; min-height: 40px; cursor: pointer; font-weight: 650; }
.btg button:disabled { opacity: .6; cursor: wait; }
.btg__error { color: var(--color-danger); }
</style>
