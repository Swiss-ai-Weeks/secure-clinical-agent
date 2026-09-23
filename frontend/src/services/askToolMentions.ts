import { chartQueryDatasets } from './workspace';

export const ASK_TOOL_TOKENS = [
  'labs',
  'meds',
  'conditions',
  'encounters',
  'allergies',
  'diet',
  'notes',
  'imaging'
] as const;

export type AskToolToken = (typeof ASK_TOOL_TOKENS)[number];

export interface AskToolMention {
  token: AskToolToken;
  label: string;
}

export interface ActiveToolMention {
  start: number;
  query: string;
}

const LABELS: Record<AskToolToken, string> = {
  labs: 'Labs',
  meds: 'Medications',
  conditions: 'Conditions',
  encounters: 'Encounters',
  allergies: 'Allergies',
  diet: 'Diet',
  notes: 'Notes',
  imaging: 'Imaging'
};

const TOKEN_SET = new Set<string>(ASK_TOOL_TOKENS);
const MENTION_RE = /(?<![A-Za-z0-9_])\/(labs|meds|conditions|encounters|allergies|diet|notes|imaging)\b/gi;
const ACTIVE_RE = /(^|[^A-Za-z0-9_])\/([A-Za-z]*)$/;

function mentionFor(token: AskToolToken): AskToolMention {
  return { token, label: LABELS[token] };
}

/** Tools this session may mention. Matches chart datasets plus notes and imaging panels. */
export function askToolMentionsFor(panels: readonly string[]): AskToolMention[] {
  const items: AskToolMention[] = chartQueryDatasets(panels).map(mentionFor);
  if (panels.includes('notes')) items.push(mentionFor('notes'));
  if (panels.includes('imaging') || panels.includes('imaging_metadata')) {
    items.push(mentionFor('imaging'));
  }
  return items;
}

/** `/` mention at the caret, only after a word boundary so `mg/dL` stays text. */
export function activeToolMention(text: string, caret: number): ActiveToolMention | null {
  const end = Math.max(0, Math.min(caret, text.length));
  const head = text.slice(0, end);
  const match = ACTIVE_RE.exec(head);
  if (!match) return null;
  return { start: head.length - match[2].length - 1, query: match[2] };
}

export function filterToolMentions(items: readonly AskToolMention[], query: string): AskToolMention[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...items];
  return items.filter(
    item => item.token.startsWith(needle) || item.label.toLowerCase().startsWith(needle)
  );
}

export function insertToolMention(
  text: string,
  start: number,
  caret: number,
  token: string
): { text: string; caret: number } {
  const tokenText = `/${token}`;
  const after = text[caret] ?? '';
  const inserted = after && /\s/.test(after) ? tokenText : `${tokenText} `;
  return {
    text: text.slice(0, start) + inserted + text.slice(caret),
    caret: start + inserted.length
  };
}

export function parseAskToolMentions(text: string): AskToolToken[] {
  const found: AskToolToken[] = [];
  for (const match of text.matchAll(MENTION_RE)) {
    const token = match[1].toLowerCase();
    if (TOKEN_SET.has(token) && !found.includes(token as AskToolToken)) {
      found.push(token as AskToolToken);
    }
  }
  return found;
}
