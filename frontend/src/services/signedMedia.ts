import type { MediaFetchOut } from '../types/api';

export type SignedMediaKind = 'image' | 'pdf' | 'text' | 'file';

export interface SignedDocument {
  kind: SignedMediaKind;
  mime: string;
  bytes: Uint8Array;
  text?: string;
}

/** The media route labels the payload `bytes_b64` but sends one Latin-1 character per byte. */
export function bytesFromSignedMedia(payload: Pick<MediaFetchOut, 'bytes_b64' | 'length'>): Uint8Array {
  const raw = payload.bytes_b64 ?? '';
  if (raw.length === payload.length) {
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i) & 0xff;
    return out;
  }
  const binary = atob(raw);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

export function presentSignedMedia(payload: Pick<MediaFetchOut, 'bytes_b64' | 'length'>): SignedDocument {
  const bytes = bytesFromSignedMedia(payload);
  const sniffed = sniff(bytes);
  if (sniffed.kind === 'text') {
    return { ...sniffed, bytes, text: new TextDecoder('utf-8', { fatal: false }).decode(bytes) };
  }
  return { ...sniffed, bytes };
}

export function documentUrl(bytes: Uint8Array, mime: string): string {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  const blob = new Blob([copy], { type: mime });
  if (typeof URL !== 'undefined' && typeof URL.createObjectURL === 'function') {
    return URL.createObjectURL(blob);
  }
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return `data:${mime};base64,${btoa(binary)}`;
}

function sniff(bytes: Uint8Array): { kind: SignedMediaKind; mime: string } {
  if (startsWith(bytes, [0x89, 0x50, 0x4e, 0x47])) return { kind: 'image', mime: 'image/png' };
  if (startsWith(bytes, [0xff, 0xd8, 0xff])) return { kind: 'image', mime: 'image/jpeg' };
  if (asciiAt(bytes, 0, 5) === '%PDF-') return { kind: 'pdf', mime: 'application/pdf' };
  if (asciiAt(bytes, 128, 4) === 'DICM') return { kind: 'file', mime: 'application/dicom' };
  if (isText(bytes)) return { kind: 'text', mime: 'text/plain' };
  return { kind: 'file', mime: 'application/octet-stream' };
}

function startsWith(bytes: Uint8Array, magic: number[]): boolean {
  if (bytes.length < magic.length) return false;
  return magic.every((value, index) => bytes[index] === value);
}

function asciiAt(bytes: Uint8Array, offset: number, length: number): string {
  if (bytes.length < offset + length) return '';
  return String.fromCharCode(...bytes.slice(offset, offset + length));
}

function isText(bytes: Uint8Array): boolean {
  if (!bytes.length) return false;
  let odd = 0;
  for (const byte of bytes) {
    if (byte === 0) return false;
    if (byte < 9 || (byte > 13 && byte < 32)) odd += 1;
  }
  return odd / bytes.length < 0.05;
}
