// Pure request helper (no Vite globals) so it can be unit-tested with `node --test`.

export class ApiError extends Error {
  status: number;

  // status 0 = the request never got an HTTP response (network down, CORS, bad base URL).
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Join base + path with exactly one slash, tolerating trailing slashes on base. */
export function buildUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

export function makeRequest(base: string, fetchImpl: typeof fetch = (...a) => fetch(...a)) {
  return async function request<T>(
    path: string,
    init: RequestInit = {},
    onHeaders?: (headers: Headers) => void, // lets callers read response headers (e.g. X-Total-Count)
  ): Promise<T> {
    // JSON string bodies get a JSON content type; FormData/Blob/etc. must be left
    // alone so the browser can set the multipart boundary itself.
    const headers = new Headers(init.headers);
    if (typeof init.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    let resp: Response;
    try {
      resp = await fetchImpl(buildUrl(base, path), { ...init, headers });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") throw e; // caller cancelled; not an error to show
      throw new ApiError(0, `Cannot reach the API at ${base} (${e instanceof Error ? e.message : String(e)})`);
    }

    const text = await resp.text();
    if (!resp.ok) {
      throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${text}`);
    }
    onHeaders?.(resp.headers);
    if (text === "") return undefined as T; // e.g. 204 No Content
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError(resp.status, `API returned a non-JSON response (HTTP ${resp.status})`);
    }
  };
}
