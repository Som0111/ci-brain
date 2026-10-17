import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, buildUrl, makeRequest } from "./http.ts";

const reply = (body: string | null, init: ResponseInit = {}) => async () => new Response(body, init);

test("buildUrl normalizes slashes", () => {
  assert.equal(buildUrl("http://x:8000/", "/repos"), "http://x:8000/repos");
  assert.equal(buildUrl("http://x:8000///", "repos"), "http://x:8000/repos");
  assert.equal(buildUrl("http://x:8000", "/repos"), "http://x:8000/repos");
});

test("JSON string body gets Content-Type; FormData does not", async () => {
  const seen: Headers[] = [];
  const spy = (async (_u: unknown, init?: RequestInit) => {
    seen.push(new Headers(init?.headers));
    return new Response("{}");
  }) as typeof fetch;
  const request = makeRequest("http://x", spy);
  await request("/a", { method: "POST", body: JSON.stringify({ a: 1 }) });
  await request("/b", { method: "POST", body: new FormData() });
  assert.equal(seen[0].get("Content-Type"), "application/json");
  assert.equal(seen[1].get("Content-Type"), null);
});

test("successful JSON, empty and 204 bodies", async () => {
  assert.deepEqual(await makeRequest("http://x", reply('{"a":1}'))("/p"), { a: 1 });
  assert.equal(await makeRequest("http://x", reply(null, { status: 204 }))("/p"), undefined);
});

test("non-JSON success body is an ApiError, not a SyntaxError", async () => {
  await assert.rejects(makeRequest("http://x", reply("<html>"))("/p"), (e: unknown) => e instanceof ApiError);
});

test("HTTP failure carries status and body", async () => {
  const request = makeRequest("http://x", reply('{"detail":"nope"}', { status: 404, statusText: "Not Found" }));
  await assert.rejects(request("/p"), (e: unknown) => e instanceof ApiError && e.status === 404 && e.message.includes("nope"));
});

test("network failure becomes ApiError status 0", async () => {
  const request = makeRequest("http://x", async () => {
    throw new TypeError("fetch failed");
  });
  await assert.rejects(request("/p"), (e: unknown) => e instanceof ApiError && e.status === 0);
});

test("abort is re-thrown untouched", async () => {
  const request = makeRequest("http://x", async () => {
    throw new DOMException("aborted", "AbortError");
  });
  await assert.rejects(request("/p"), (e: unknown) => e instanceof DOMException && e.name === "AbortError");
});

test("onHeaders exposes response headers (e.g. X-Total-Count)", async () => {
  let total: string | null = null;
  const request = makeRequest("http://x", reply("[]", { headers: { "X-Total-Count": "42" } }));
  await request("/p", {}, (h) => {
    total = h.get("X-Total-Count");
  });
  assert.equal(total, "42");
});
