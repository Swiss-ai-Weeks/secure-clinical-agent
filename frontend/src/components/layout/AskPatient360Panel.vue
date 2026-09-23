<template>
  <aside
    v-if="ui.askPanelOpen"
    class="panel"
    :class="{
      'panel--collapsed': collapsed,
      'panel--dragging': dragging,
      'panel--narrow': narrowViewport
    }"
    :style="panelStyle"
    aria-label="Ask Patient360"
  >
    <button
      type="button"
      class="nudge"
      :aria-label="nudgeLabel"
      :aria-expanded="!collapsed"
      :title="nudgeTitle"
      @pointerdown="onNudgePointerDown"
      @keydown="onNudgeKeydown"
      @click="onNudgeClick"
    >
      <span class="nudge__grip" aria-hidden="true" />
    </button>

    <div v-show="!collapsed" class="panel__body">
      <header class="panel__header">
        <div class="identity">
          <span v-if="chart?.avatarInitials" class="avatar" aria-hidden="true">{{ chart.avatarInitials }}</span>
          <div>
            <p class="eyebrow">Ask Patient360</p>
            <h2>{{ contextTitle }}</h2>
            <p class="lede">{{ contextLede }}</p>
          </div>
        </div>
        <div class="header__actions">
          <button
            v-if="ui.selectedPatientId"
            type="button"
            class="icon-btn"
            aria-label="New chat"
            title="New chat"
            :disabled="!thread.length"
            @click="startNewChat"
          >
            <SquarePen :size="18" aria-hidden="true" />
          </button>
          <button type="button" class="icon-btn" aria-label="Close" @click="ui.closeAskPanel">
            <X :size="20" aria-hidden="true" />
          </button>
        </div>
      </header>

      <nav v-if="resumable.length" class="earlier" aria-label="Earlier chats">
        <h3>Earlier chats</h3>
        <button
          v-for="chat in resumable"
          :key="chat.id"
          type="button"
          class="earlier__chat"
          @click="resumeChat(chat)"
        >
          {{ chat.title }}
        </button>
      </nav>

      <div ref="threadEl" class="thread" role="log" aria-label="Conversation" aria-live="polite">
        <div
          v-if="ui.selectedPatientId && !thread.length && !loading"
          class="empty"
        >
          <p class="empty__title">Ask about this chart</p>
          <p class="empty__lede">Answers cite only authorized records from the open chart.</p>
          <div class="suggestions" role="group" aria-label="Suggested prompts">
            <button
              v-for="prompt in suggestions"
              :key="prompt"
              type="button"
              class="chip"
              :disabled="loading"
              @click="useSuggestion(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
        </div>

        <div v-if="thread.length || loading" class="thread__stream">
        <template v-for="item in thread" :key="item.id">
          <div v-if="item.kind === 'user'" class="turn turn--user">
            <div class="bubble bubble--user">
              <p class="bubble__text" :data-copy-root="item.id">{{ item.text }}</p>
            </div>
            <div class="meta">
              <time v-if="item.at" class="stamp" :datetime="isoStamp(item.at)">{{ formatStamp(item.at) }}</time>
              <button
                type="button"
                class="copy-btn"
                aria-label="Copy message"
                @click="copyMessage(item)"
              >
                <Copy :size="14" aria-hidden="true" />
                <span>{{ copyLabel(item.id) }}</span>
              </button>
            </div>
          </div>

          <div v-else-if="item.kind === 'notice'" class="turn turn--notice">
            <p class="notice" :data-copy-root="item.id">{{ item.text }}</p>
            <div class="meta">
              <time v-if="item.at" class="stamp" :datetime="isoStamp(item.at)">{{ formatStamp(item.at) }}</time>
              <button
                type="button"
                class="copy-btn"
                aria-label="Copy message"
                @click="copyMessage(item)"
              >
                <Copy :size="14" aria-hidden="true" />
                <span>{{ copyLabel(item.id) }}</span>
              </button>
            </div>
          </div>

          <article
            v-else-if="item.answer"
            class="turn turn--assistant"
            :class="{ refused: isRefusal(item.answer) }"
          >
            <div
              class="bubble bubble--assistant"
              :class="{
                'bubble--refused': isRefusal(item.answer),
                'bubble--blocked': isNotAllowed(item.answer)
              }"
            >
            <p v-if="statusEyebrow(item.answer)" class="bubble__status">{{ statusEyebrow(item.answer) }}</p>
            <p v-if="isNotAllowed(item.answer)" class="bubble__title" :data-copy-root="item.id">This is not allowed.</p>
            <p v-else-if="isRuntimeDown(item.answer)" class="bubble__title">The clinical assistant did not complete this turn</p>
            <p v-else-if="isRefusal(item.answer)" class="bubble__title">Nothing authorized for that question</p>
            <div v-if="!isNotAllowed(item.answer)" class="bubble__body" :data-copy-root="item.id">
              <template v-for="(block, index) in blocksFor(item.answer)" :key="index">
                <ul v-if="block.type === 'list'" class="bubble__list">
                  <li v-for="(line, itemIndex) in block.items" :key="itemIndex">
                    <template v-for="(part, partIndex) in line" :key="partIndex">
                      <strong v-if="part.bold">{{ part.text }}</strong>
                      <button v-else-if="part.citeId" type="button" class="cite" :aria-label="`Open ${part.text}`" @click="openCitation(part.citeId, item.answer)">{{ part.text }}</button>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </li>
                </ul>
                <p v-else>
                  <template v-for="(part, partIndex) in block.parts" :key="partIndex">
                    <strong v-if="part.bold">{{ part.text }}</strong>
                    <button v-else-if="part.citeId" type="button" class="cite" :aria-label="`Open ${part.text}`" @click="openCitation(part.citeId, item.answer)">{{ part.text }}</button>
                    <template v-else>{{ part.text }}</template>
                  </template>
                </p>
              </template>
            </div>
            <p v-if="reasonFor(item.answer)" class="reason">{{ reasonFor(item.answer) }}</p>

            <section v-if="citationsFor(item.answer).length" class="sources" aria-label="Sources used">
              <h4>Sources used</h4>
              <p class="sources__hint">Records the answer cited. Select one to highlight it in the chart.</p>
              <div class="citations">
                <SourceCitation
                  v-for="citation in citationsFor(item.answer)"
                  :key="citation.id"
                  :label="citeLabel(citation.id, item.answer.citations)"
                  :source-id="citation.sourceId"
                  :source-type="citation.sourceType"
                  @select="ui.highlightSource"
                />
              </div>
            </section>
            <template v-else>
              <p v-if="isRuntimeDown(item.answer)" class="sources-empty">
                No substitute answer was used, so there are no source chips.
              </p>
              <p v-else-if="isNotAllowed(item.answer)" class="sources-empty">
                This question is not allowed, so the chart was not used.
              </p>
              <p v-else-if="!isRefusal(item.answer)" class="sources-empty">
                The answer did not cite a specific lab, note, medication, or condition.
              </p>
              <p v-else class="sources-empty">
                Authorized records were searched. None applied to this question, so no source chips are shown.
              </p>
            </template>
            <button
              v-if="canRetryTurn(item)"
              type="button"
              class="retry"
              :disabled="loading || uploading"
              @click="retryTurn(item)"
            >
              Retry
            </button>

            <details v-if="stepsFor(item.answer).length" class="trace">
              <summary>How this was retrieved</summary>
              <ol>
                <li v-for="step in stepsFor(item.answer)" :key="step">{{ step }}</li>
              </ol>
            </details>
            </div>
            <div class="meta">
              <time v-if="item.at" class="stamp" :datetime="isoStamp(item.at)">{{ formatStamp(item.at) }}</time>
              <button
                type="button"
                class="copy-btn"
                aria-label="Copy message"
                @click="copyMessage(item)"
              >
                <Copy :size="14" aria-hidden="true" />
                <span>{{ copyLabel(item.id) }}</span>
              </button>
            </div>
          </article>
        </template>

        <div v-if="loading" class="turn turn--assistant" role="status">
          <div class="bubble bubble--assistant bubble--typing">
            <span class="typing" aria-hidden="true"><i /><i /><i /></span>
            <span>Working on a cited answer…</span>
          </div>
        </div>
        </div>

        <p v-if="error" class="error" role="alert">
          <span>{{ error }}</span>
          <button
            v-if="retryableError"
            type="button"
            class="retry"
            :disabled="loading || uploading"
            @click="retryError"
          >
            Retry
          </button>
        </p>
      </div>

      <form class="composer" @submit.prevent="ask">
        <label class="sr-only" for="ask-input">Question</label>
        <div class="composer__bar">
          <label
            v-if="canUpload"
            class="attach-btn"
            :class="{ busy: uploading }"
            :title="uploading ? 'Uploading…' : 'Attach a document'"
          >
            <Paperclip :size="18" aria-hidden="true" />
            <span class="sr-only">{{ uploading ? 'Uploading…' : 'Upload document' }}</span>
            <input aria-label="Upload document" type="file" :disabled="uploading || loading" @change="stageFile" />
          </label>
          <div class="composer__field">
            <textarea
              id="ask-input"
              ref="askInput"
              v-model="question"
              rows="1"
              :disabled="!ui.selectedPatientId || loading"
              placeholder="Message this chart, or type / for a tool"
              role="combobox"
              aria-autocomplete="list"
              aria-controls="ask-tool-mentions"
              :aria-expanded="mentionOpen"
              :aria-activedescendant="mentionActiveId"
              @keydown="onAskKeydown"
              @keyup="syncMention"
              @click="syncMention"
              @input="onComposerInput"
            />
            <ul
              v-if="mentionOpen"
              id="ask-tool-mentions"
              class="mention-menu"
              role="listbox"
              aria-label="Tools"
            >
              <li
                v-for="(item, index) in mentionOptions"
                :id="`ask-tool-${item.token}`"
                :key="item.token"
                role="option"
                :aria-selected="index === mentionIndex"
                :class="{ 'mention-menu__item--active': index === mentionIndex }"
                :aria-label="item.label"
                @mousedown.prevent="selectMention(item)"
              >
                <span class="mention-menu__token">/{{ item.token }}</span>
                <span>{{ item.label }}</span>
              </li>
            </ul>
          </div>
          <button
            type="submit"
            class="ask-submit send"
            aria-label="Ask with sources"
            :disabled="loading || uploading || !ui.selectedPatientId || (!question.trim() && !pendingFile)"
          >
            <Send :size="16" aria-hidden="true" />
            <span>Send</span>
          </button>
        </div>
        <p v-if="pendingFile" class="attach__pending">
          <span class="attach__name">{{ pendingFile.name }}</span>
          <button type="button" class="attach__clear" :disabled="uploading || loading" @click="pendingFile = null">
            Remove
          </button>
        </p>
        <p v-if="!ui.selectedPatientId" class="hint">
          Open a live chart first. Ask searches authorized records for that patient only.
        </p>
      </form>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Copy, Paperclip, Send, SquarePen, X } from 'lucide-vue-next';
import { apiClient } from '../../services/apiClient';
import {
  answerBlocks,
  citationsUsedInAnswer,
  citeLabel,
  displayAnswerText,
  friendlyRetrievalSteps,
  isNoEvidenceAnswer,
  policyReasonLabel,
  type AnswerBlock
} from '../../services/askCitations';
import {
  activeToolMention,
  askToolMentionsFor,
  filterToolMentions,
  insertToolMention,
  type ActiveToolMention,
  type AskToolMention
} from '../../services/askToolMentions';
import { ApiError } from '../../services/http';
import type { AiAnswer, ChatHistoryTurn } from '../../types/patient360';
import { useSessionStore } from '../../stores/useSessionStore';
import { useUiStore } from '../../stores/useUiStore';
import SourceCitation from '../ui/SourceCitation.vue';

const CHAT_INACTIVE = 'This chat is no longer active. Start a new chat to continue.';

interface ThreadItem {
  id: string;
  kind: 'user' | 'assistant' | 'notice';
  text: string;
  answer?: AiAnswer;
  at?: number;
}

interface SavedChat {
  id: string;
  title: string;
  items: ThreadItem[];
  stamp: string;
}

interface SandboxStatus {
  active: boolean;
  stamp?: string;
}

const WIDTH_KEY = 'patient360.askPanelWidth';
const MIN_WIDTH = 320;
const MAX_WIDTH_CAP = 640;
const RAIL_WIDTH = 28;
const WIDTH_STEP = 24;
const COLLAPSE_DRAG_BELOW = 280;
const NARROW_MQ = '(max-width: 640px)';

const ui = useUiStore();
const session = useSessionStore();
const route = useRoute();
const router = useRouter();
const question = ref('');
const mention = ref<ActiveToolMention | null>(null);
const mentionIndex = ref(0);
let mentionDismissedStart: number | null = null;
const loading = ref(false);
const uploading = ref(false);
const pendingFile = ref<File | null>(null);
const error = ref('');
const chart = ref<{ fullName: string; avatarInitials: string; canUpload: boolean } | null>(null);
const threads = reactive<Record<string, ThreadItem[]>>({});
const threadGeneration = reactive<Record<string, number>>({});
const currentStamp = reactive<Record<string, string>>({});
const previousChats = reactive<Record<string, SavedChat[]>>({});
const sandboxStatus = ref<SandboxStatus>({ active: false });
let nextId = 0;
const suggestions = [
  'What changed since the last visit?',
  'Summarize the latest note',
  'Summarize the latest labs',
  'Which conditions are on this record?'
];

const panelWidth = ref(480);
const collapsed = ref(false);
const dragging = ref(false);
const narrowViewport = ref(false);
const threadEl = ref<HTMLElement | null>(null);
const askInput = ref<HTMLTextAreaElement | null>(null);
const copyStatus = ref<Record<string, 'copied' | 'failed'>>({});
let copyResetTimer: ReturnType<typeof setTimeout> | undefined;
let didDrag = false;
let dragStartX = 0;
let dragStartWidth = 0;
let mediaQuery: MediaQueryList | null = null;

const patientId = computed(() => ui.selectedPatientId || (typeof route.params.patientId === 'string' ? route.params.patientId : ''));
const thread = computed(() => (patientId.value ? threads[patientId.value] ?? [] : []));
const resumable = computed(() => {
  const id = patientId.value;
  const status = sandboxStatus.value;
  if (!id || !status.active || !status.stamp) return [];
  return (previousChats[id] ?? []).filter(chat => chat.stamp === status.stamp);
});
const canUpload = computed(() => chart.value?.canUpload === true);
const contextTitle = computed(() => {
  if (!ui.selectedPatientId) return 'No chart selected';
  return chart.value?.fullName || 'This open chart';
});
const contextLede = computed(() =>
  ui.selectedPatientId
    ? 'Cited answers stay in this chat and use only authorized records from this chart.'
    : 'Open a patient chart to ask with sources.'
);
const mentionCatalog = computed(() => askToolMentionsFor(session.panels));
const mentionOptions = computed(() =>
  mention.value ? filterToolMentions(mentionCatalog.value, mention.value.query) : []
);
const mentionOpen = computed(() => mentionOptions.value.length > 0);
const mentionActiveId = computed(() => {
  if (!mentionOpen.value) return undefined;
  const token = mentionOptions.value[mentionIndex.value]?.token;
  return token ? `ask-tool-${token}` : undefined;
});

function syncMention() {
  const el = askInput.value;
  const caret = el?.selectionStart ?? question.value.length;
  const found = activeToolMention(question.value, caret);
  if (!found) {
    mentionDismissedStart = null;
    mention.value = null;
    mentionIndex.value = 0;
    return;
  }
  if (mentionDismissedStart === found.start) {
    mention.value = null;
    return;
  }
  const same = mention.value?.start === found.start && mention.value.query === found.query;
  mention.value = found;
  if (!same) mentionIndex.value = 0;
}

function resizeComposer() {
  const el = askInput.value;
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${Math.min(Math.max(el.scrollHeight, 40), 128)}px`;
}

function onComposerInput() {
  syncMention();
  resizeComposer();
}

function selectMention(item: AskToolMention) {
  const el = askInput.value;
  const caret = el?.selectionStart ?? question.value.length;
  const active = mention.value ?? activeToolMention(question.value, caret);
  if (!active) return;
  const next = insertToolMention(question.value, active.start, caret, item.token);
  question.value = next.text;
  mention.value = null;
  mentionDismissedStart = null;
  mentionIndex.value = 0;
  void nextTick(() => {
    el?.focus();
    el?.setSelectionRange(next.caret, next.caret);
    resizeComposer();
  });
}

function onAskKeydown(event: KeyboardEvent) {
  if (mentionOpen.value) {
    const count = mentionOptions.value.length;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      mentionIndex.value = (mentionIndex.value + 1) % count;
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      mentionIndex.value = (mentionIndex.value - 1 + count) % count;
      return;
    }
    if ((event.key === 'Enter' || event.key === 'Tab') && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey) {
      event.preventDefault();
      const item = mentionOptions.value[mentionIndex.value];
      if (item) selectMention(item);
      return;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      mentionDismissedStart = mention.value?.start ?? null;
      mention.value = null;
      return;
    }
  }
  if (event.key === 'Enter' && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    void ask();
  }
}

const nudgeLabel = computed(() => {
  if (collapsed.value) return 'Expand chat';
  if (narrowViewport.value) return 'Collapse chat';
  return 'Resize chat';
});
const nudgeTitle = computed(() => {
  if (collapsed.value) return 'Expand chat';
  if (narrowViewport.value) return 'Click to collapse chat';
  return 'Drag to resize · Click to collapse';
});
const panelStyle = computed(() => {
  if (collapsed.value) {
    return { width: `${RAIL_WIDTH}px`, left: 'auto', right: '0' };
  }
  if (narrowViewport.value) {
    return { width: '100%', left: '0', right: '0' };
  }
  return { width: `${panelWidth.value}px`, left: 'auto', right: '0' };
});

function maxWidthForViewport() {
  if (typeof window === 'undefined') return MAX_WIDTH_CAP;
  return Math.min(MAX_WIDTH_CAP, Math.floor(window.innerWidth * 0.5));
}

function defaultWidth() {
  if (typeof window === 'undefined') return 480;
  const content = Math.max(0, window.innerWidth - 256);
  return clampWidth(Math.min(500, Math.max(420, Math.round(0.4 * content))));
}

function clampWidth(width: number) {
  return Math.min(maxWidthForViewport(), Math.max(MIN_WIDTH, Math.round(width)));
}

function readStoredWidth() {
  try {
    const raw = localStorage.getItem(WIDTH_KEY);
    if (!raw) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? clampWidth(value) : null;
  } catch {
    return null;
  }
}

function persistWidth(width: number) {
  try {
    localStorage.setItem(WIDTH_KEY, String(width));
  } catch {
    /* ignore storage failures */
  }
}

function setWidth(width: number, { persist = true } = {}) {
  const next = clampWidth(width);
  panelWidth.value = next;
  if (persist) persistWidth(next);
}

function toggleCollapse() {
  collapsed.value = !collapsed.value;
}

function onNudgeClick() {
  if (didDrag) {
    didDrag = false;
    return;
  }
  toggleCollapse();
}

function onNudgePointerDown(event: PointerEvent) {
  if (event.button !== 0) return;
  if (narrowViewport.value || collapsed.value) return;
  didDrag = false;
  dragging.value = true;
  dragStartX = event.clientX;
  dragStartWidth = panelWidth.value;
  const target = event.currentTarget as HTMLElement;
  target.setPointerCapture(event.pointerId);
  window.addEventListener('pointermove', onNudgePointerMove);
  window.addEventListener('pointerup', onNudgePointerUp);
  window.addEventListener('pointercancel', onNudgePointerUp);
}

function onNudgePointerMove(event: PointerEvent) {
  if (!dragging.value) return;
  const delta = dragStartX - event.clientX;
  if (Math.abs(delta) > 3) didDrag = true;
  const next = dragStartWidth + delta;
  if (next < COLLAPSE_DRAG_BELOW) {
    panelWidth.value = Math.max(RAIL_WIDTH, Math.round(next));
    return;
  }
  setWidth(next, { persist: false });
}

function onNudgePointerUp() {
  if (!dragging.value) return;
  dragging.value = false;
  window.removeEventListener('pointermove', onNudgePointerMove);
  window.removeEventListener('pointerup', onNudgePointerUp);
  window.removeEventListener('pointercancel', onNudgePointerUp);
  if (panelWidth.value < COLLAPSE_DRAG_BELOW) {
    collapsed.value = true;
    panelWidth.value = readStoredWidth() ?? defaultWidth();
    return;
  }
  setWidth(panelWidth.value);
}

function onNudgeKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleCollapse();
    return;
  }
  if (narrowViewport.value) return;
  if (event.key === 'ArrowLeft') {
    event.preventDefault();
    if (collapsed.value) {
      collapsed.value = false;
      return;
    }
    setWidth(panelWidth.value + WIDTH_STEP);
  } else if (event.key === 'ArrowRight') {
    event.preventDefault();
    if (collapsed.value) return;
    if (panelWidth.value - WIDTH_STEP < MIN_WIDTH) {
      collapsed.value = true;
      return;
    }
    setWidth(panelWidth.value - WIDTH_STEP);
  }
}

function syncNarrow(event?: MediaQueryListEvent | MediaQueryList) {
  const matches = event && 'matches' in event ? event.matches : mediaQuery?.matches;
  narrowViewport.value = !!matches;
  if (!narrowViewport.value) {
    setWidth(panelWidth.value);
  }
}

onMounted(() => {
  panelWidth.value = readStoredWidth() ?? defaultWidth();
  if (typeof window.matchMedia !== 'function') return;
  mediaQuery = window.matchMedia(NARROW_MQ);
  syncNarrow(mediaQuery);
  mediaQuery.addEventListener('change', syncNarrow);
});

onBeforeUnmount(() => {
  mediaQuery?.removeEventListener('change', syncNarrow);
  window.removeEventListener('pointermove', onNudgePointerMove);
  window.removeEventListener('pointerup', onNudgePointerUp);
  window.removeEventListener('pointercancel', onNudgePointerUp);
  if (copyResetTimer) clearTimeout(copyResetTimer);
});

function isRuntimeDown(answer: AiAnswer) {
  return answer.policy_reason === 'nemoclaw_unavailable';
}
function isNotAllowed(answer: AiAnswer) {
  return answer.policy_reason === 'content_safety';
}
function isRefusal(answer: AiAnswer) {
  return isNoEvidenceAnswer(answer) && !isRuntimeDown(answer);
}
function eyebrowFor(answer: AiAnswer) {
  if (isNotAllowed(answer)) return 'Not allowed';
  if (isRuntimeDown(answer)) return 'Assistant unavailable';
  if (isRefusal(answer)) return 'No matching evidence';
  return 'Answer';
}
function statusEyebrow(answer: AiAnswer) {
  const label = eyebrowFor(answer);
  return label === 'Answer' ? '' : label;
}
function formatStamp(at: number) {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(at));
}
function isoStamp(at: number) {
  return new Date(at).toISOString();
}
function blocksFor(answer: AiAnswer) {
  return answerBlocks(answer.answer, answer.citations);
}
function citationsFor(answer: AiAnswer) {
  return citationsUsedInAnswer(answer);
}
function stepsFor(answer: AiAnswer) {
  return friendlyRetrievalSteps(answer.retrievalSteps);
}
function reasonFor(answer: AiAnswer) {
  const label = policyReasonLabel(answer.policy_reason);
  if (!label || label === answer.answer.trim()) return '';
  return label;
}

function plainFromBlocks(blocks: AnswerBlock[]): string {
  const lines: string[] = [];
  for (const block of blocks) {
    if (block.type === 'list') {
      for (const item of block.items) {
        lines.push(`• ${item.map(part => part.text).join('')}`);
      }
    } else {
      lines.push(block.parts.map(part => part.text).join(''));
    }
  }
  return lines.join('\n').trim();
}

function copyTextFor(item: ThreadItem): string {
  if (item.kind === 'user' || item.kind === 'notice') return item.text;
  const answer = item.answer;
  if (!answer) return item.text;
  if (isNotAllowed(answer)) return 'This is not allowed.';
  const parts: string[] = [];
  if (isRuntimeDown(answer)) parts.push('The clinical assistant did not complete this turn');
  else if (isRefusal(answer)) parts.push('Nothing authorized for that question');
  const body = plainFromBlocks(blocksFor(answer));
  if (body) parts.push(body);
  else {
    const cleaned = displayAnswerText(answer.answer);
    if (cleaned) parts.push(cleaned);
  }
  const reason = reasonFor(answer);
  if (reason) parts.push(reason);
  return parts.join('\n\n').trim();
}

function copyLabel(id: string) {
  const status = copyStatus.value[id];
  if (status === 'copied') return 'Copied';
  if (status === 'failed') return 'Copy failed';
  return 'Copy';
}

function selectCopyRoot(id: string): boolean {
  const root = threadEl.value?.querySelector(`[data-copy-root="${id}"]`) as HTMLElement | null;
  if (!root) return false;
  const range = document.createRange();
  range.selectNodeContents(root);
  const selection = window.getSelection();
  if (!selection) return false;
  selection.removeAllRanges();
  selection.addRange(range);
  return true;
}

function scheduleCopyReset(id: string) {
  if (copyResetTimer) clearTimeout(copyResetTimer);
  copyResetTimer = setTimeout(() => {
    const next = { ...copyStatus.value };
    delete next[id];
    copyStatus.value = next;
  }, 2000);
}

async function copyMessage(item: ThreadItem) {
  const text = copyTextFor(item);
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
    await navigator.clipboard.writeText(text);
    copyStatus.value = { ...copyStatus.value, [item.id]: 'copied' };
  } catch {
    const selected = selectCopyRoot(item.id);
    let copied = false;
    if (selected) {
      try {
        copied = document.execCommand('copy');
      } catch {
        copied = false;
      }
    }
    copyStatus.value = { ...copyStatus.value, [item.id]: copied ? 'copied' : 'failed' };
  }
  scheduleCopyReset(item.id);
}

function scrollThreadToEnd() {
  void nextTick(() => {
    const el = threadEl.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function focusComposer() {
  void nextTick(() => {
    askInput.value?.focus();
  });
}

function useSuggestion(prompt: string) {
  if (loading.value || uploading.value) return;
  if (!ui.selectedPatientId) {
    error.value = 'Open a patient chart before asking. Without a patient, there is no authorized evidence.';
    return;
  }
  question.value = prompt;
  void ask();
}

function pushItem(id: string, item: ThreadItem) {
  if (!threads[id]) threads[id] = [];
  threads[id].push({ at: Date.now(), ...item });
  scrollThreadToEnd();
}

function copyItems(items: ThreadItem[]) {
  return items.map(item => ({ ...item }));
}

async function loadSandbox() {
  try {
    const status = await apiClient.chatSandbox();
    sandboxStatus.value = status.active && status.stamp ? { active: true, stamp: status.stamp } : { active: false };
  } catch {
    sandboxStatus.value = { active: false };
  }
}

function archiveCurrent(id: string) {
  const items = threads[id];
  const stamp = currentStamp[id];
  if (!items?.length || !stamp) return;
  const title = items.find(item => item.kind === 'user')?.text.trim() || 'Earlier chat';
  const saved: SavedChat = {
    id: `c${nextId++}`,
    title: title.slice(0, 80),
    items: copyItems(items),
    stamp
  };
  previousChats[id] = [saved, ...(previousChats[id] ?? [])].slice(0, 8);
}

function startNewChat() {
  const id = patientId.value;
  if (!id || !threads[id]?.length) return;
  archiveCurrent(id);
  threadGeneration[id] = (threadGeneration[id] ?? 0) + 1;
  threads[id] = [];
  delete currentStamp[id];
  error.value = '';
  loading.value = false;
  void loadSandbox();
}

async function resumeChat(chat: SavedChat) {
  const id = patientId.value;
  if (!id) return;
  await loadSandbox();
  if (!sandboxStatus.value.active || sandboxStatus.value.stamp !== chat.stamp) {
    error.value = CHAT_INACTIVE;
    return;
  }
  archiveCurrent(id);
  threadGeneration[id] = (threadGeneration[id] ?? 0) + 1;
  threads[id] = copyItems(chat.items);
  currentStamp[id] = chat.stamp;
  previousChats[id] = (previousChats[id] ?? []).filter(item => item.id !== chat.id);
  error.value = '';
  loading.value = false;
  question.value = '';
}

async function sandboxStillOwns(id: string) {
  const stamp = currentStamp[id];
  if (!stamp) return true;
  await loadSandbox();
  return sandboxStatus.value.active && sandboxStatus.value.stamp === stamp;
}

function historyFrom(items: ThreadItem[]): ChatHistoryTurn[] {
  const messages: ChatHistoryTurn[] = [];
  for (const item of items) {
    if (item.kind === 'user' || item.kind === 'notice') messages.push({ role: 'user', content: item.text });
    else if (item.answer && !isRuntimeDown(item.answer)) messages.push({ role: 'assistant', content: item.answer.answer });
  }
  return messages.slice(-8);
}

function priorHistory(id: string): ChatHistoryTurn[] {
  return historyFrom(threads[id] ?? []);
}

function canRetryTurn(item: ThreadItem) {
  if (loading.value || uploading.value || !item.answer || !isRuntimeDown(item.answer)) return false;
  const items = thread.value;
  return items[items.length - 1]?.id === item.id;
}

const retryableError = computed(() => {
  if (!error.value || loading.value || uploading.value) return false;
  if (error.value === CHAT_INACTIVE || error.value.startsWith('Open a patient chart')) return false;
  const last = thread.value.at(-1);
  return last?.kind === 'user' || pendingFile.value !== null;
});

function openCitation(citeId: string, answer?: AiAnswer) {
  const match = answer?.citations.find(item => item.id === citeId || item.sourceId === citeId);
  const sourceId = match?.sourceId || citeId;
  ui.highlightSource(sourceId);
  const id = patientId.value;
  if (!id) return;
  const kind = match?.sourceType;
  const note = kind === 'note' || kind === 'document' || /admission|^note_/i.test(citeId);
  const section = note
    ? 'notes'
    : kind === 'lab'
      ? 'labs'
      : kind === 'medication'
        ? 'medications'
        : kind === 'condition'
          ? 'overview'
          : kind === 'encounter'
            ? 'timeline'
            : 'notes';
  void router.push(`/patients/${id}/${section}`);
}

watch(
  () => ui.askPanelOpen,
  open => {
    if (!open) {
      collapsed.value = false;
      return;
    }
    void loadSandbox();
  }
);

watch(
  () => ui.askExpandToken,
  () => {
    if (!ui.askPanelOpen) return;
    collapsed.value = false;
    const draft = ui.consumeAskDraft();
    if (draft) {
      question.value = draft;
      error.value = '';
      void nextTick(resizeComposer);
    }
    focusComposer();
    scrollThreadToEnd();
  }
);

watch(question, () => {
  void nextTick(resizeComposer);
});

watch(loading, busy => {
  if (busy) scrollThreadToEnd();
});

watch(
  patientId,
  async (id, previous) => {
    if (previous && previous !== id) {
      question.value = '';
      error.value = '';
      pendingFile.value = null;
    }
    chart.value = null;
    if (!id) return;
    void loadSandbox();
    try {
      const patient = await apiClient.getPatient(id);
      if (patientId.value !== id) return;
      chart.value = {
        fullName: patient.fullName,
        avatarInitials: patient.avatarInitials,
        canUpload: patient.canUpload === true
      };
    } catch {
      if (patientId.value === id) chart.value = null;
    }
  },
  { immediate: true }
);

function stageFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file || !canUpload.value) return;
  pendingFile.value = file;
  error.value = '';
}

async function sendAttachment(id: string, file: File): Promise<boolean> {
  const generation = threadGeneration[id] ?? 0;
  uploading.value = true;
  error.value = '';
  pendingFile.value = null;
  try {
    const result = await apiClient.uploadDocument(id, file);
    if ((threadGeneration[id] ?? 0) !== generation) return false;
    pushItem(id, { id: `m${nextId++}`, kind: 'notice', text: uploadNotice(file.name, result) });
    return true;
  } catch (err) {
    if ((threadGeneration[id] ?? 0) !== generation) return false;
    pendingFile.value = file;
    error.value = err instanceof ApiError ? err.message : 'Upload failed';
    return false;
  } finally {
    if ((threadGeneration[id] ?? 0) === generation) uploading.value = false;
  }
}

async function ask() {
  const id = ui.selectedPatientId;
  const text = question.value.trim();
  const file = pendingFile.value;
  if (!id) {
    error.value = 'Open a patient chart before asking. Without a patient, there is no authorized evidence.';
    return;
  }
  if ((!text && !file) || loading.value || uploading.value) return;
  if (!(await sandboxStillOwns(id))) {
    error.value = CHAT_INACTIVE;
    return;
  }
  if (file) {
    const uploaded = await sendAttachment(id, file);
    if (!uploaded) return;
  }
  if (!text) return;
  const history = priorHistory(id);
  const generation = threadGeneration[id] ?? 0;
  pushItem(id, { id: `m${nextId++}`, kind: 'user', text });
  question.value = '';
  mention.value = null;
  mentionDismissedStart = null;
  void nextTick(resizeComposer);
  await completeAsk(id, text, history, generation);
}

async function retryTurn(item: ThreadItem) {
  const id = patientId.value;
  if (!id || !canRetryTurn(item)) return;
  const items = threads[id] ?? [];
  const index = items.findIndex(entry => entry.id === item.id);
  const text = [...items.slice(0, index)].reverse().find(entry => entry.kind === 'user')?.text;
  if (!text) return;
  question.value = text;
  await ask();
}

async function retryError() {
  const id = ui.selectedPatientId;
  if (!id || !retryableError.value) return;
  const last = (threads[id] ?? []).at(-1);
  if (last?.kind === 'user' && !pendingFile.value) {
    if (!(await sandboxStillOwns(id))) {
      error.value = CHAT_INACTIVE;
      return;
    }
    const history = historyFrom((threads[id] ?? []).slice(0, -1));
    await completeAsk(id, last.text, history, threadGeneration[id] ?? 0);
    return;
  }
  await ask();
}

async function completeAsk(id: string, text: string, history: ChatHistoryTurn[], generation: number) {
  loading.value = true;
  error.value = '';
  try {
    const answer = await apiClient.askPatient360({
      scope: 'patient',
      patientId: id,
      question: text,
      history
    });
    if ((threadGeneration[id] ?? 0) !== generation) return;
    pushItem(id, { id: `m${nextId++}`, kind: 'assistant', text: answer.answer, answer });
    if (answer.sandboxStamp && !currentStamp[id]) currentStamp[id] = answer.sandboxStamp;
  } catch (err) {
    if ((threadGeneration[id] ?? 0) !== generation) return;
    error.value = err instanceof ApiError ? err.message : 'Ask failed';
  } finally {
    if ((threadGeneration[id] ?? 0) === generation) {
      loading.value = false;
      focusComposer();
      scrollThreadToEnd();
    }
  }
}

function uploadNotice(name: string, result: { status: string; reason?: string }) {
  if (result.status === 'processed') return `${name} is on this chart.`;
  if (result.reason === 'content_safety' || result.reason === 'content_safety_unavailable') {
    return `${name} was blocked and was not added to the chart.`;
  }
  return `${name} stayed in quarantine.`;
}

</script>

<style scoped>
.panel {
  position: fixed;
  z-index: 10;
  top: 0;
  right: 0;
  display: flex;
  flex-direction: column;
  height: 100dvh;
  max-width: 100vw;
  overflow: hidden;
  border-left: 1px solid var(--color-line);
  background: var(--color-bg);
  box-shadow: var(--shadow-panel);
  box-sizing: border-box;
}
.panel__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
  min-height: 0;
  padding: var(--space-5) var(--space-5) var(--space-4) calc(var(--space-5) + 16px);
}
.panel--collapsed {
  padding: 0;
  background: var(--color-surface);
}
.panel--collapsed .panel__body {
  display: none;
}
.panel--dragging {
  user-select: none;
  transition: none;
}
.nudge {
  position: absolute;
  z-index: 2;
  top: 0;
  left: 0;
  bottom: 0;
  display: grid;
  place-items: center;
  width: 20px;
  min-height: 0;
  min-width: 0;
  margin: 0;
  border: 0;
  border-right: 1px solid var(--color-line);
  border-radius: 0;
  background: var(--color-surface);
  color: var(--color-muted);
  cursor: ew-resize;
  padding: 0;
  box-shadow: none;
  pointer-events: auto;
}
.nudge:hover,
.nudge:focus-visible {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}
.nudge:focus-visible {
  outline: none;
  box-shadow: inset 0 0 0 2px var(--color-accent-ring);
}
.nudge__grip {
  width: 3px;
  height: 36px;
  border-radius: 999px;
  background:
    linear-gradient(
      to bottom,
      transparent 0 2px,
      currentColor 2px 4px,
      transparent 4px 6px,
      currentColor 6px 8px,
      transparent 8px 10px,
      currentColor 10px 12px,
      transparent 12px 14px,
      currentColor 14px 16px,
      transparent 16px 18px,
      currentColor 18px 20px,
      transparent 20px 22px,
      currentColor 22px 24px,
      transparent 24px 26px,
      currentColor 26px 28px,
      transparent 28px 30px,
      currentColor 30px 32px,
      transparent 32px
    );
  opacity: 0.85;
}
.panel--collapsed .nudge {
  width: 100%;
  cursor: pointer;
  border-right: 0;
  background: var(--color-bg);
}
.panel--collapsed .nudge__grip {
  height: 48px;
  color: var(--color-accent);
}
.panel--narrow:not(.panel--collapsed) .nudge {
  cursor: pointer;
}
.panel__header {
  display: flex;
  flex: 0 0 auto;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-3);
}
.header__actions {
  display: flex;
  flex: 0 0 auto;
  gap: var(--space-2);
}
.identity {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  min-width: 0;
}
.avatar {
  display: grid;
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  place-items: center;
  border-radius: 12px;
  background: var(--color-accent-soft);
  color: var(--color-accent-ink);
  font-size: var(--text-sm);
  font-weight: 600;
}
.eyebrow {
  margin: 0 0 2px;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.panel h2 {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: var(--text-xl);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  line-height: var(--leading-tight);
}
.lede {
  margin: var(--space-1) 0 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
.earlier {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-2);
}
.earlier h3 {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.earlier__chat {
  width: 100%;
  min-height: 36px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  padding: 0 var(--space-3);
  overflow: hidden;
  color: var(--color-ink);
  font-size: var(--text-sm);
  font-weight: 550;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}
.earlier__chat:hover,
.earlier__chat:focus-visible {
  background: var(--color-accent-soft);
}
.thread {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
}
.thread__stream {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: var(--space-4);
  width: 100%;
  min-width: 0;
  margin-top: auto;
  padding: var(--space-1) 0 var(--space-2);
}
.empty {
  display: grid;
  gap: var(--space-3);
  margin: auto 0;
  padding: var(--space-2) 0;
}
.empty__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
  color: var(--color-ink);
}
.empty__lede {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
.turn {
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 100%;
  min-width: 0;
}
.turn--user {
  align-items: flex-end;
}
.turn--assistant {
  align-items: flex-start;
}
.turn--notice {
  align-items: flex-start;
}
.bubble {
  display: grid;
  gap: var(--space-2);
  max-width: min(86%, 36rem);
  min-width: 0;
}
.bubble--user {
  border-radius: 16px 16px 4px 16px;
  background: var(--color-accent);
  color: #fff;
  padding: 10px 14px;
}
.bubble--assistant {
  border: 1px solid var(--color-line);
  border-radius: 4px 16px 16px 16px;
  background: var(--color-surface);
  padding: 10px 14px;
}
.bubble--refused,
.bubble--blocked {
  background: var(--color-danger-soft);
  border-color: rgb(180 35 24 / 20%);
}
.bubble--typing {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.bubble__status {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-meta);
  text-transform: uppercase;
}
.bubble__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
  letter-spacing: var(--tracking-tight);
}
.bubble__text,
.bubble__body {
  margin: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  line-height: var(--leading-snug);
  user-select: text;
}
.bubble__body {
  display: grid;
  gap: var(--space-3);
}
.bubble__body p {
  margin: 0;
  line-height: 1.65;
}
.bubble__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: 1.15rem;
  line-height: 1.55;
}
.meta {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.turn--user .meta {
  justify-content: flex-end;
}
.stamp {
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  line-height: 1;
  white-space: nowrap;
}
.typing {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.typing i {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--color-accent);
  opacity: 0.35;
  animation: typing 1.05s ease-in-out infinite;
}
.typing i:nth-child(2) { animation-delay: 0.15s; }
.typing i:nth-child(3) { animation-delay: 0.3s; }
@keyframes typing {
  0%, 80%, 100% { opacity: 0.28; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}
.notice {
  margin: 0;
  max-width: min(92%, 36rem);
  overflow-wrap: anywhere;
  word-break: break-word;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
  user-select: text;
}
.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  align-self: flex-start;
  min-height: 24px;
  margin: 0;
  border: 0;
  border-radius: var(--radius-control);
  background: transparent;
  padding: 0 4px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.copy-btn:hover,
.copy-btn:focus-visible {
  color: var(--color-accent-ink);
  background: var(--color-accent-soft);
}
.copy-btn:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}
.icon-btn {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  min-height: 40px;
  border: 1px solid var(--color-line);
  border-radius: 10px;
  background: var(--color-surface);
  cursor: pointer;
}
.icon-btn:disabled {
  opacity: 0.45;
  cursor: default;
}
.composer {
  display: grid;
  flex: 0 0 auto;
  gap: var(--space-2);
  padding: var(--space-3) 0 0;
  border: 0;
  border-top: 1px solid var(--color-line);
  border-radius: 0;
  background: transparent;
}
.composer__bar {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  min-width: 0;
}
.composer__field {
  position: relative;
  flex: 1;
  min-width: 0;
}
.composer textarea {
  display: block;
  width: 100%;
  min-height: 40px;
  max-height: 128px;
  border: 1px solid var(--color-line);
  border-radius: 20px;
  background: var(--color-surface);
  padding: 9px 14px;
  resize: none;
  overflow-x: hidden;
  overflow-y: auto;
  font-size: var(--text-sm);
  line-height: var(--leading-body);
}
.mention-menu {
  position: absolute;
  right: 0;
  bottom: calc(100% + 4px);
  left: 0;
  z-index: 2;
  display: grid;
  gap: 2px;
  margin: 0;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  padding: var(--space-2);
  max-height: 220px;
  overflow-x: hidden;
  overflow-y: auto;
  list-style: none;
  box-shadow: 0 8px 24px rgb(15 23 42 / 10%);
}
.mention-menu li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 36px;
  border-radius: 6px;
  padding: 0 var(--space-3);
  color: var(--color-ink);
  font-size: var(--text-sm);
  cursor: pointer;
}
.mention-menu__item--active,
.mention-menu li:hover {
  background: var(--color-accent-soft);
}
.mention-menu__token {
  color: var(--color-accent-ink);
  font-weight: 650;
}
.composer textarea:disabled {
  opacity: 0.7;
}
.attach-btn {
  position: relative;
  display: grid;
  flex: 0 0 40px;
  place-items: center;
  width: 40px;
  height: 40px;
  min-height: 40px;
  border: 1px solid var(--color-line);
  border-radius: 999px;
  background: var(--color-surface);
  color: var(--color-muted);
  cursor: pointer;
}
.attach-btn:hover,
.attach-btn:focus-within {
  color: var(--color-accent);
  background: var(--color-accent-soft);
}
.attach-btn.busy { opacity: 0.7; cursor: wait; }
.attach-btn input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}
.attach__pending {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
  min-width: 0;
}
.attach__name {
  overflow: hidden;
  color: var(--color-ink);
  font-size: var(--text-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attach__clear {
  border: 0;
  background: transparent;
  padding: 0;
  font-size: var(--text-xs);
  color: var(--color-muted);
  cursor: pointer;
}
.send {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0 14px;
}
.hint, .sources__hint, .sources-empty {
  margin: 0;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: var(--leading-snug);
}
.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.chip {
  position: relative;
  z-index: 1;
  width: max-content;
  max-width: 100%;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  background: var(--color-surface);
  padding: 0 12px;
  min-height: 32px;
  font-size: var(--text-sm);
  font-weight: 550;
  cursor: pointer;
  pointer-events: auto;
}
.chip:hover,
.chip:focus-visible {
  border-color: rgb(29 78 216 / 28%);
  background: var(--color-accent-soft);
}
.chip:disabled {
  opacity: 0.6;
  cursor: default;
}
.trace ol {
  margin: 0;
  padding-left: 20px;
  color: var(--color-muted);
  font-size: var(--text-sm);
  line-height: 1.6;
}
.sources h4 {
  margin: 0;
  font-size: var(--text-xs);
  font-weight: 600;
}
.cite {
  display: inline-flex;
  align-items: center;
  margin: 0 3px;
  padding: 1px 8px;
  border: 1px solid rgb(29 78 216 / 22%);
  border-radius: var(--radius-pill);
  background: var(--color-accent-soft);
  color: var(--color-accent-ink);
  font: inherit;
  font-size: 0.92em;
  font-weight: 600;
  cursor: pointer;
}
.cite:hover,
.cite:focus-visible {
  background: #dbeafe;
}
.answer__list {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding-left: 1.15rem;
  line-height: 1.55;
}
.reason, .error {
  color: var(--color-danger);
}
.error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  margin: 0;
}
.retry {
  min-height: 32px;
  border: 1px solid var(--color-line);
  border-radius: var(--radius-control);
  background: var(--color-surface);
  padding: 0 12px;
  color: var(--color-ink);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
}
.retry:disabled {
  opacity: 0.6;
  cursor: default;
}
.sources {
  display: grid;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-line);
}
.citations {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}
.trace {
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.trace summary {
  cursor: pointer;
  font-weight: 600;
}

@media (max-width: 640px) {
  .panel:not(.panel--collapsed) {
    left: 0;
    right: 0;
    border-left: 0;
  }
  .panel:not(.panel--collapsed) .panel__body {
    padding-left: var(--space-5);
  }
}
</style>
