<template>
  <div class="signed">
    <button type="button" @click="open">Open signed copy</button>
    <p v-if="status">{{ status }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';

const props = defineProps<{ patientKey: string; studyId?: string; objectKey?: string }>();
const status = ref('');

async function open() {
  status.value = '';
  try {
    const signed = await apiClient.signMedia({
      patient_key: props.patientKey,
      study_id: props.studyId,
      object_key: props.objectKey
    });
    const body = await apiClient.fetchMedia(signed.url);
    status.value = `Signed. ${body.length} bytes. Expires in ${signed.expires_in}s.`;
  } catch (error) {
    status.value = error instanceof ApiError && error.notFound ? 'Resource not found' : (error as Error).message;
  }
}
</script>

<style scoped>
.signed { display: grid; gap: 6px; margin-top: 8px; }
button { border: 1px solid var(--color-line); border-radius: var(--radius-control); background: var(--color-plum); color: white; padding: 0 12px; cursor: pointer; }
p { margin: 0; color: var(--color-muted); font-size: 14px; }
</style>
