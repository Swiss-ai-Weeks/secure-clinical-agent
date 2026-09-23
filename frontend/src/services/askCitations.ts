import type { AiAnswer, AiCitation } from '../types/patient360';

const NO_EVIDENCE = /no authorized evidence/i;

const POLICY_LABELS: Record<string, string> = {
  no_authorized_evidence: 'No authorized records matched this question.',
  identity_claim: 'That question was blocked by an input check.',
  citation_leak: 'The draft answer was blocked because it cited an unauthorized record.',
  empty: 'The model returned an empty answer.',
  nemoclaw_unavailable: 'NemoClaw was unavailable. No substitute answer was used.',
  named_patient_mismatch:
    'That question names someone other than the open chart, so it was blocked.',
  other_patients:
    "Ask answers only this open chart. Other patients on today's schedule are not in these records."
};

const STEP_LABELS: Record<string, string> = {
  'Minted run token': 'Started a scoped search',
  'Searched authorized structured rows': 'Searched authorized labs, conditions, and medications',
  'Searched authorized notes': 'Searched authorized notes',
  'Notes not authorized': 'Notes were not authorized for this session',
  'Read authorized identity banner': 'Read the identity banner for this open chart',
  'Identity banner not authorized': 'The identity banner was not authorized for this session',
  'Searched authorized appointments': 'Searched booked appointments on this chart',
  'Appointments not authorized': 'Appointments were not authorized for this session',
  'OpenShell sandbox turn': 'Wrote a cited summary',
  'Bound OpenShell sandbox': 'Opened a session sandbox',
  'NemoClaw sandbox setup failed': 'Assistant setup failed',
  'NemoClaw unavailable': 'NemoClaw was unavailable',
  'Input rail blocked the question': 'The question was blocked',
  'Question names a different patient': 'The question names a different patient than this chart',
  'Question asks for other patients': "Today's other patients are outside this chart"
};

export function isNoEvidenceAnswer(answer: Pick<AiAnswer, 'answer' | 'refused'>): boolean {
  return Boolean(answer.refused) || NO_EVIDENCE.test(answer.answer);
}

function citedInText(text: string, citation: AiCitation): boolean {
  if (citation.sourceId && text.includes(citation.sourceId)) return true;
  if (citation.id && citation.id !== citation.sourceId && text.includes(citation.id)) return true;
  const hay = text.toLowerCase();
  const label = citation.label.trim();
  if (label.length >= 3 && hay.includes(label.toLowerCase())) return true;
  if (citation.sourceType === 'note') {
    const words = label.toLowerCase().split(/[^a-z0-9]+/).filter(word => word.length >= 4 && word !== 'note');
    if (words.some(word => hay.includes(word))) return true;
    if (/\bnotes?\b/.test(hay)) return true;
  }
  return false;
}

/** Citations the answer actually used — not every authorized row retrieved for the chart. */
export function citationsUsedInAnswer(answer: AiAnswer): AiCitation[] {
  if (answer.refused || NO_EVIDENCE.test(answer.answer)) return [];
  const text = answer.answer;
  const byToken = answer.citations.filter(
    citation =>
      (citation.sourceId && text.includes(citation.sourceId)) ||
      (citation.id && citation.id !== citation.sourceId && text.includes(citation.id))
  );
  const matched = byToken.length ? byToken : answer.citations.filter(citation => citedInText(text, citation));
  const seen = new Set<string>();
  const unique: AiCitation[] = [];
  for (const citation of matched) {
    const key = `${citation.sourceType}:${citation.label.trim().toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(citation);
  }
  return unique;
}

export function policyReasonLabel(reason: string | null | undefined): string {
  if (!reason) return '';
  return POLICY_LABELS[reason] ?? '';
}

export function friendlyRetrievalSteps(steps: string[]): string[] {
  return steps.map(step => {
    if (STEP_LABELS[step]) return STEP_LABELS[step];
    if (/\/tools\/|\/chat|\/me\b|p_[0-9a-f]|p360-s-|sandbox|patient_key/i.test(step)) {
      return 'Completed an authorized retrieval step';
    }
    return step;
  });
}

export type InlinePart = { text: string; bold?: boolean; citeId?: string };
export type AnswerBlock =
  | { type: 'p'; parts: InlinePart[] }
  | { type: 'list'; items: InlinePart[][] };

const CITE_TOKEN = /\s*(?:\[cite:\s*[a-z]{1,12}_[a-z0-9-]+\]|\[(?:cite_id:\s*)?[a-z]{1,12}_[a-z0-9-]+\]|【[a-z0-9_-]+】|\[[a-z]{1,12}_[a-z0-9-]*\]?|\(cite_id:\s*[^)]+\))/gi;

export function displayAnswerText(text: string): string {
  return text.replace(CITE_TOKEN, '').replace(/[ \t]+\n/g, '\n').replace(/[ \t]{2,}/g, ' ').trim();
}

const OPAQUE_PATIENT_NOTE = /^p_[0-9a-f]{16,}/i;
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
const CITE_MARK = new RegExp(`\\[(?:cite:\\s*)?([A-Za-z][A-Za-z0-9_-]{2,}|${UUID})\\]`, 'gi');
const SOCIAL_SENTENCE = /never smoked|identifies as|socioeconomic|college courses|high school education|comes from a |patient is single|no complaints|\binsurance\b|humana|medicaid|medicare/i;

const JSON_NOTE_LEAD =
  /^(?:the\s+)?json\s+entry\s+is\s+(?:a\s+)?clinical\s+note\s+for\s+patient\s+titled\s+[“"]([^”"]+)[”"]\s*,?\s*documenting\s+/i;

function withoutRetrievalNarration(text: string): string {
  return text.replace(JSON_NOTE_LEAD, (_match, title: string) => {
    const name = title.trim().replace(/[,.\s]+$/, '').replace(/^\w/, letter => letter.toUpperCase());
    const when = /historical/i.test(name) ? ', a past encounter, ' : ' ';
    return `${name}${when}documents `;
  });
}

function withoutSocialPart(part: string): string {
  const trimmed = part.trim();
  if (!trimmed || !SOCIAL_SENTENCE.test(trimmed)) return trimmed;
  return trimmed
    .split(/,\s+|\s+and\s+/i)
    .map(clause => clause.trim())
    .filter(clause => clause && !SOCIAL_SENTENCE.test(clause))
    .join(', ');
}

function withoutSocialSentences(text: string): string {
  return text
    .split(/\n+/)
    .map(paragraph =>
      paragraph
        .split(/(?<=[.!?])\s+/)
        .map(sentence =>
          sentence
            .split(/\s+-\s+/)
            .map(withoutSocialPart)
            .filter(part => part.trim())
            .join(' - ')
        )
        .filter(sentence => sentence.trim())
        .join(' ')
    )
    .filter(paragraph => paragraph.trim())
    .join('\n')
    .trim();
}

function boldParts(text: string): InlinePart[] {
  const parts: InlinePart[] = [];
  const pattern = /\*\*(.+?)\*\*/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > last) parts.push({ text: text.slice(last, index) });
    parts.push({ text: match[1], bold: true });
    last = index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts.filter(part => part.text);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function citeLabel(id: string, citations: AiCitation[] = []): string {
  const match = citations.find(item => item.id === id || item.sourceId === id);
  const raw = match?.label?.trim() ?? '';
  const rawIsId = !raw || raw === id || /^(?:obs|note|cond|med|enc)_|^p\d{2,}/i.test(raw);
  if (!rawIsId) return raw;
  const dated = id.match(/(\d{4})-(\d{2})-(\d{2})/);
  const kind = /admission/i.test(id)
    ? 'Admission note'
    : /^obs_/i.test(id) || match?.sourceType === 'lab'
      ? 'Lab'
      : /^med_/i.test(id) || match?.sourceType === 'medication'
        ? 'Medication'
        : /^cond_/i.test(id) || match?.sourceType === 'condition'
          ? 'Condition'
          : /^enc_/i.test(id) || match?.sourceType === 'encounter'
            ? 'Visit'
            : 'Note';
  if (!dated) return kind;
  const month = MONTHS[Number(dated[2]) - 1] ?? dated[2];
  return `${kind}, ${Number(dated[3])} ${month} ${dated[1]}`;
}

export function inlineParts(text: string, citations: AiCitation[] = []): InlinePart[] {
  const parts: InlinePart[] = [];
  let last = 0;
  for (const match of text.matchAll(CITE_MARK)) {
    const index = match.index ?? 0;
    const citeId = match[1];
    if (index > last) parts.push(...boldParts(text.slice(last, index)));
    if (!OPAQUE_PATIENT_NOTE.test(citeId)) {
      parts.push({ text: citeLabel(citeId, citations), citeId });
    }
    last = index + match[0].length;
  }
  if (last < text.length) parts.push(...boldParts(text.slice(last)));
  return parts.filter(part => part.text);
}

function lineBlocks(text: string, citations: AiCitation[] = []): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let list: InlinePart[][] = [];
  const flush = () => {
    if (!list.length) return;
    blocks.push({ type: 'list', items: list });
    list = [];
  };
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.*)/);
    if (bullet) {
      list.push(inlineParts(bullet[1], citations));
      continue;
    }
    flush();
    blocks.push({ type: 'p', parts: inlineParts(line, citations) });
  }
  flush();
  return blocks;
}

const OPAQUE_INLINE = /\s*(?:【[a-z0-9_-]+】|\(cite_id:\s*[^)]+\)|\[cite_id:\s*[^\]]+\])/gi;

/** Turn model markdown and inline citations into paragraphs, lists, and clickable cite tokens. */
export function answerBlocks(text: string, citations: AiCitation[] = []): AnswerBlock[] {
  const cleaned = withoutSocialSentences(
    withoutRetrievalNarration(text.replace(OPAQUE_INLINE, ''))
      .replace(/[ \t]+\n/g, '\n')
      .replace(/[ \t]{2,}/g, ' ')
      .trim()
  );
  if (!cleaned) return [];
  if (!cleaned.includes('\n') && cleaned.includes(' - ')) {
    const [first, ...rest] = cleaned.split(' - ');
    const blocks: AnswerBlock[] = [];
    if (first.trim()) blocks.push({ type: 'p', parts: inlineParts(first.trim(), citations) });
    if (rest.length) blocks.push({ type: 'list', items: rest.map(item => inlineParts(item.trim(), citations)) });
    return blocks;
  }
  return lineBlocks(cleaned, citations);
}
