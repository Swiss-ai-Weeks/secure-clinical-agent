<template>
  <section class="ohif">
    <header class="ohif__header">
      <RouterLink
        class="back"
        :to="{ name: 'patient-imaging', params: { patientId } }"
      >
        <ArrowLeft aria-hidden="true" />
        Back to imaging
      </RouterLink>
      <h1>Study viewer</h1>
    </header>
    <p v-if="error" class="empty">{{ error }}</p>
    <template v-else-if="!loading && viewerSrc">
      <p class="meta">This study was loaded from its signed media path. Use the right-hand segmentation panel to show or hide the VISTA-3D overlay.</p>
      <iframe class="frame" :src="viewerSrc" title="OHIF study viewer" />
    </template>
  </section>
</template>

<script setup lang="ts">
import { ArrowLeft } from 'lucide-vue-next';
import { computed, onBeforeUnmount, ref } from 'vue';
import { RouterLink, useRoute } from 'vue-router';
import { useLiveLoad } from '../../composables/useLiveLoad';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import {
  DICOMWEB_STORAGE_KEY,
  ohifViewerSrc,
  signedDicomWebRoot,
  signedMediaPath,
  storeDicomWebRoot
} from '../../services/ohifSource';

const route = useRoute();
const patientId = computed(() => String(route.params.patientId));
const studyId = computed(() => String(route.query.study || ''));
const error = ref('');
const viewerSrc = ref('');

onBeforeUnmount(() => {
  sessionStorage.removeItem(DICOMWEB_STORAGE_KEY);
});

const { loading } = useLiveLoad(async () => {
  error.value = '';
  viewerSrc.value = '';
  if (!studyId.value) {
    error.value = 'No study was selected.';
    return;
  }
  try {
    const signed = await apiClient.signMedia({ patient_key: patientId.value, study_id: studyId.value });
    const path = signedMediaPath(signed.url);
    if (!path) {
      error.value = 'The viewer only loads a signed /media study URL.';
      return;
    }
    const root = signedDicomWebRoot(signed.url);
    const src = ohifViewerSrc(signed.study_instance_uid ?? '');
    if (!root || !src) {
      error.value = signed.study_instance_uid
        ? 'The OHIF viewer is not available.'
        : 'No signed DICOM study UID is stored for this study.';
      return;
    }
    const bundle = await fetch('/ohif/index.html', { credentials: 'same-origin' });
    if (!bundle.ok) {
      error.value = 'The OHIF viewer is not available.';
      return;
    }
    if (!storeDicomWebRoot(root)) {
      error.value = 'The viewer only loads a signed /media study URL.';
      return;
    }
    viewerSrc.value = src;
  } catch (err) {
    error.value = err instanceof ApiError && err.notFound
      ? 'No signed file is stored for this study.'
      : (err as Error).message;
  }
});
</script>

<style scoped>
.ohif {
  display: grid;
  grid-template-rows: auto auto minmax(36rem, 1fr);
  gap: 12px;
  max-width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.ohif__header {
  min-width: 0;
  margin-bottom: 0;
}
.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: max-content;
  min-height: 36px;
  margin: 0;
  padding: 0 10px 0 8px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  color: var(--color-ink);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
}
.back:hover {
  border-color: var(--color-line-strong);
  background: var(--color-surface-muted);
}
.back svg {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  stroke-width: 2;
}
.empty, .meta { color: var(--color-muted); margin: 0; }
.frame {
  display: block;
  width: 100%;
  max-width: 100%;
  height: 100%;
  min-height: 36rem;
  border: 0;
  border-radius: 12px;
  background: #0b1424;
}
@media (max-width: 820px) {
  .ohif {
    height: auto;
    min-height: 85dvh;
  }
  .frame {
    min-height: 80dvh;
  }
}
</style>
