export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.status = status;
    this.body = body;
  }

  get notFound(): boolean {
    return this.status === 404;
  }
}

const base = import.meta.env.VITE_API_BASE ?? '/api';

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData;
  if (init.body && !isForm && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${base}${path}`, { ...init, headers, credentials: 'include' });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, body, issueMessage(body) ?? `Request failed (${response.status})`);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function issueMessage(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const issue = (body as { issue?: Array<{ diagnostics?: string }> }).issue?.[0];
  return issue?.diagnostics;
}
