<template>
  <div class="signed" :class="{ 'signed--row': isStudyRow }">
    <button
      v-if="isStudyRow && canOpen"
      ref="trigger"
      type="button"
      class="study-row"
      :aria-label="`Open in viewer: ${label}`"
      :disabled="busy"
      @click="open"
    >
      <span class="study-row__meta">
        <span v-if="eyebrow" class="study-row__eyebrow">{{ eyebrow }}</span>
        <span class="study-row__title">{{ label }}</span>
      </span>
      <span class="study-row__action">Open in viewer</span>
    </button>
    <button
      v-else-if="!isStudyRow"
      ref="trigger"
      type="button"
      :disabled="busy"
      @click="open"
    >{{ busy ? 'Opening…' : 'Open signed copy' }}</button>
    <p v-if="status" :class="{ error: statusError }" role="status">{{ status }}</p>
    <dialog ref="viewer" class="viewer" @click="onBackdrop" @close="onDialogClose">
      <div class="sheet">
        <header class="sheet__header">
          <h2>{{ label }}</h2>
          <button type="button" @click="close">Close</button>
        </header>
        <div class="sheet__body">
          <img v-if="imageUrl" :src="imageUrl" :alt="label" />
          <iframe v-else-if="pdfUrl" class="frame" :src="pdfUrl" :title="label" />
          <pre v-else-if="text">{{ text }}</pre>
          <a v-else-if="fileUrl" class="file" :href="fileUrl" target="_blank" rel="noopener">View signed file</a>
        </div>
      </div>
    </dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiClient } from '../../services/apiClient';
import { ApiError } from '../../services/http';
import { documentUrl, presentSignedMedia } from '../../services/signedMedia';

const router = useRouter();

const props = withDefaults(defineProps<{
  patientKey: string;
  studyId?: string;
  objectKey?: string;
  label?: string;
  variant?: 'button' | 'thumbnail';
  eyebrow?: string;
}>(), { label: 'Signed imaging', variant: 'button' });

const isStudyRow = computed(() => props.variant === 'thumbnail');
const status = ref('');
const statusError = ref(false);
const busy = ref(false);
const canOpen = ref(true);
const imageUrl = ref('');
const pdfUrl = ref('');
const fileUrl = ref('');
const text = ref('');
const viewer = ref<HTMLDialogElement | null>(null);
const trigger = ref<HTMLButtonElement | null>(null);
let objectUrl = '';
let restoreFocus = false;

function revoke(url: string) {
  if (url.startsWith('blob:')) URL.revokeObjectURL(url);
}

function clearDialogMedia() {
  imageUrl.value = '';
  pdfUrl.value = '';
  fileUrl.value = '';
  text.value = '';
  if (objectUrl) revoke(objectUrl);
  objectUrl = '';
}

function dismissDialog() {
  const dialog = viewer.value;
  if (!dialog) return;
  if (typeof dialog.close === 'function' && dialog.open) {
    dialog.close();
    return;
  }
  if (dialog.hasAttribute('open')) {
    dialog.removeAttribute('open');
    dialog.dispatchEvent(new Event('close'));
  }
}

function clearAll() {
  clearDialogMedia();
  dismissDialog();
}

onBeforeUnmount(clearAll);

function close() {
  restoreFocus = true;
  dismissDialog();
}

function onDialogClose() {
  clearDialogMedia();
  if (restoreFocus) {
    restoreFocus = false;
    nextTick(() => trigger.value?.focus());
  }
}

function onBackdrop(event: MouseEvent) {
  if (event.target === viewer.value) close();
}

async function reveal() {
  await nextTick();
  const dialog = viewer.value;
  if (!dialog) return;
  restoreFocus = true;
  if (typeof dialog.showModal === 'function') {
    if (!dialog.open) dialog.showModal();
    return;
  }
  dialog.setAttribute('open', '');
}

async function open() {
  status.value = '';
  statusError.value = false;
  if (props.studyId && !props.objectKey) {
    await router.push({
      name: 'patient-ohif',
      params: { patientId: props.patientKey },
      query: { study: props.studyId }
    });
    return;
  }
  busy.value = true;
  clearDialogMedia();
  try {
    const signed = await apiClient.signMedia({
      patient_key: props.patientKey,
      study_id: props.studyId,
      object_key: props.objectKey
    });
    const body = await apiClient.fetchMedia(signed.url);
    const document = presentSignedMedia(body);
    status.value = `Signed copy ready. Expires in ${signed.expires_in}s.`;
    if (document.kind === 'text') {
      text.value = document.text ?? '';
    } else {
      objectUrl = documentUrl(document.bytes, document.mime);
      if (document.kind === 'image') imageUrl.value = objectUrl;
      else if (document.kind === 'pdf') pdfUrl.value = objectUrl;
      else fileUrl.value = objectUrl;
    }
    await reveal();
  } catch (error) {
    statusError.value = true;
    status.value = error instanceof ApiError && error.notFound
      ? 'No signed file is stored for this document.'
      : (error as Error).message;
    if (isStudyRow.value) canOpen.value = false;
  } finally {
    busy.value = false;
  }
}

defineExpose({ open, close });
</script>

<style scoped>
.signed { display: grid; gap: var(--space-2); margin-top: var(--space-3); max-width: 100%; min-width: 0; }
.signed > button:not(.study-row) {
  justify-self: start;
  border: 0;
  border-radius: var(--radius-control);
  background: var(--color-accent);
  color: white;
  padding: 0 12px;
  cursor: pointer;
  min-height: 36px;
  font-size: var(--text-sm);
  font-weight: 600;
}
.signed > button:not(.study-row):disabled { opacity: 0.7; cursor: wait; }
p { margin: 0; color: var(--color-muted); font-size: var(--text-sm); }
p.error { color: var(--color-danger); font-weight: 600; }

.study-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  width: 100%;
  max-width: 100%;
  min-width: 0;
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--color-line);
  border-radius: 12px;
  background: var(--color-surface-raised);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 140ms ease, background 140ms ease;
}
.study-row:hover {
  border-color: rgb(29 78 216 / 28%);
  background: var(--color-accent-soft);
}
.study-row:disabled { opacity: 0.75; cursor: wait; }
.study-row:focus-visible { box-shadow: var(--focus-ring); }
.study-row__meta { display: grid; gap: 2px; min-width: 0; }
.study-row__eyebrow {
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.study-row__title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--color-ink);
}
.study-row__action {
  flex: 0 0 auto;
  color: var(--color-accent-ink);
  font-size: var(--text-sm);
  font-weight: 600;
}

.viewer {
  border: 0;
  padding: 0;
  background: transparent;
  box-sizing: border-box;
  width: min(960px, calc(100vw - var(--nav-width) - 2.5rem));
  max-width: calc(100vw - 1.5rem);
  max-height: calc(100dvh - 1.5rem);
  margin: auto;
}
.viewer::backdrop { background: rgb(11 20 36 / 52%); }
.sheet {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  width: 100%;
  max-width: 100%;
  max-height: calc(100dvh - 1.5rem);
  overflow: hidden;
  background: var(--color-surface);
  border-radius: var(--radius-panel);
  box-shadow: var(--shadow-card);
}
.sheet__header {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-width: 0;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-line);
}
.sheet__header h2 {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
}
.sheet__header button {
  flex: 0 0 auto;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  min-height: 36px;
  padding: 0 12px;
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 550;
}
.sheet__body {
  display: grid;
  place-items: center;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: var(--space-4) var(--space-5) var(--space-5);
  -webkit-overflow-scrolling: touch;
}
.sheet__body img {
  display: block;
  max-width: 100%;
  max-height: min(70dvh, calc(100dvh - 10rem));
  width: auto;
  height: auto;
  object-fit: contain;
  border-radius: 12px;
  background: #0b1424;
}
.sheet__body pre {
  margin: 0;
  justify-self: stretch;
  max-width: 100%;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  font: inherit;
}
.frame {
  display: block;
  width: 100%;
  max-width: 100%;
  height: min(70dvh, calc(100dvh - 10rem));
  min-height: 240px;
  border: 0;
}
.file { color: var(--color-accent-ink); font-weight: 600; word-break: break-word; }

@media (max-width: 820px) {
  .viewer {
    width: calc(100vw - 1.5rem);
    max-width: calc(100vw - 1.5rem);
  }
}
</style>
