/** Seed-demo SNOMED labels used when the aggregate cell has a code but no display. */
const SEED_CODE_DISPLAY: Record<string, string> = {
  '171057006': 'Pregnancy prevention education',
  '195967001': 'Asthma',
  '233604007': 'Pneumonia',
  '35489007': 'Depressive disorder',
  '38341003': 'Hypertensive disorder',
  '433144002': 'Chronic kidney disease stage 3',
  '44054006': 'Type 2 diabetes mellitus',
  '55822004': 'Hyperlipidemia'
};

function text(value: unknown): string | undefined {
  if (value == null) return undefined;
  const out = String(value).trim();
  return out || undefined;
}

export function aggregateDims(row: Record<string, unknown>): Record<string, unknown> {
  const dims = row.dims;
  if (dims && typeof dims === 'object' && !Array.isArray(dims)) {
    return dims as Record<string, unknown>;
  }
  return row;
}

export function aggregateCellCode(row: Record<string, unknown>): string | undefined {
  const dims = aggregateDims(row);
  return text(dims.code ?? dims.type_code);
}

export function aggregateCellTitle(row: Record<string, unknown>): string {
  const dims = aggregateDims(row);
  const display = text(row.display) || text(dims.display);
  if (display) return display;
  const code = aggregateCellCode(row);
  if (code && SEED_CODE_DISPLAY[code]) return SEED_CODE_DISPLAY[code];
  if (dims.ward != null) return String(dims.ward);
  if (code) return code;
  return JSON.stringify(dims);
}
