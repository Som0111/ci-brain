import assert from "node:assert/strict";
import { test } from "node:test";

import { formatCount, formatDuration, formatPct, formatPercent, formatTimestamp } from "./format.ts";

test("percent helpers", () => {
  assert.equal(formatPercent(0.1234), "12%");
  assert.equal(formatPercent(0.1234, 1), "12.3%");
  assert.equal(formatPct(58.24), "58.2%");
});

test("duration picks a sensible unit and rejects bad input", () => {
  assert.equal(formatDuration(0.25), "250 ms");
  assert.equal(formatDuration(12.345), "12.35 s");
  assert.equal(formatDuration(125), "2 m 5 s");
  assert.equal(formatDuration(-1), "—");
  assert.equal(formatDuration(Number.NaN), "—");
});

test("count and timestamp", () => {
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatTimestamp(null), "—");
  assert.equal(formatTimestamp("not a date"), "—");
  assert.notEqual(formatTimestamp("2026-10-17T06:00:00Z"), "—");
});
