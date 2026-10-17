import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError } from "./http.ts";
import { startFetch, type Settled } from "./startFetch.ts";

const deferred = <T>() => {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};
const tick = () => new Promise((r) => setTimeout(r, 0));

test("reports data tagged with its key and attempt", async () => {
  const seen: Settled<number>[] = [];
  startFetch(async () => 7, "[1]", 0, (s) => seen.push(s));
  await tick();
  assert.deepEqual(seen, [{ key: "[1]", attempt: 0, data: 7 }]);
});

test("cancel aborts the signal and suppresses a late success", async () => {
  const d = deferred<string>();
  let signal!: AbortSignal;
  const seen: unknown[] = [];
  const cancel = startFetch(
    (s) => {
      signal = s;
      return d.promise;
    },
    "[1]",
    0,
    (s) => seen.push(s),
  );
  cancel();
  assert.equal(signal.aborted, true);
  d.resolve("late"); // old repo's response arriving after the user switched
  await tick();
  assert.deepEqual(seen, []);
});

test("cancel suppresses a late failure, including the AbortError itself", async () => {
  const d = deferred<string>();
  const seen: unknown[] = [];
  const cancel = startFetch(() => d.promise, "[1]", 0, (s) => seen.push(s));
  cancel();
  d.reject(new DOMException("aborted", "AbortError"));
  await tick();
  assert.deepEqual(seen, []);
});

test("only the latest of two overlapping fetches reports (fast repo switch)", async () => {
  const first = deferred<string>();
  const second = deferred<string>();
  const seen: Settled<string>[] = [];
  const cancelFirst = startFetch(() => first.promise, "[1]", 0, (s) => seen.push(s));
  cancelFirst(); // key changed -> effect cleanup
  startFetch(() => second.promise, "[2]", 0, (s) => seen.push(s));
  second.resolve("repo2");
  first.resolve("repo1"); // resolves last, but is stale
  await tick();
  assert.deepEqual(seen, [{ key: "[2]", attempt: 0, data: "repo2" }]);
});

test("failures carry message and HTTP status (null for non-ApiError)", async () => {
  const seen: Settled<never>[] = [];
  startFetch(async () => Promise.reject(new ApiError(503, "down")), "[1]", 0, (s) => seen.push(s));
  startFetch(async () => Promise.reject(new Error("boom")), "[1]", 1, (s) => seen.push(s));
  await tick();
  assert.deepEqual(
    seen.map((s) => s.error),
    [
      { message: "down", status: 503 },
      { message: "boom", status: null },
    ],
  );
});

test("a synchronous throw in the fetcher becomes an error result, not a crash", async () => {
  const seen: Settled<never>[] = [];
  startFetch(
    () => {
      throw new Error("sync");
    },
    "[1]",
    0,
    (s) => seen.push(s),
  );
  await tick();
  assert.equal(seen[0].error?.message, "sync");
});

test("a fetcher that ignores the signal still cannot report after cancel", async () => {
  const seen: unknown[] = [];
  const cancel = startFetch(async () => "ignored-signal", "[1]", 0, (s) => seen.push(s));
  cancel();
  await tick();
  assert.deepEqual(seen, []);
});
