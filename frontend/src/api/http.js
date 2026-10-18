export class ApiError extends Error {
  constructor(message, { status = 0, code = 'NETWORK_ERROR', details } = {}) {
    super(message); this.name = 'ApiError'; this.status = status; this.code = code; this.details = details;
  }
}

export async function requestJson(url, { method = 'GET', body, signal, timeout_ms = 15000, content_type = 'application/json' } = {}) {
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener('abort', abort, { once: true });
  let timedOut = false;
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeout_ms);
  try {
    const response = await fetch(url, { method, signal: controller.signal,
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': content_type }) },
      ...(body === undefined ? {} : { body: content_type === 'application/json' ? JSON.stringify(body) : body }),
    });
    const text = await response.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch {
      throw new ApiError('The backend returned invalid JSON.', { status: response.status, code: 'INVALID_RESPONSE' });
    }
    if (!response.ok) throw new ApiError(data?.message ?? data?.detail?.message ?? (typeof data?.detail === 'string' ? data.detail : `The request failed (${response.status}).`),
      { status: response.status, code: data?.error_code ?? data?.detail?.error_code ?? data?.code ?? 'HTTP_ERROR', details: data });
    return data;
  } catch (error) {
    if (timedOut) throw new ApiError('The request timed out. Refresh the run before retrying a change.', { code: 'TIMEOUT' });
    if (error.name === 'AbortError' || error instanceof ApiError) throw error;
    throw new ApiError('Cannot reach the backend. Check the API URL and connection.');
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort); }
}
