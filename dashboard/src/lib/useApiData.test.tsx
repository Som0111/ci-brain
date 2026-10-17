import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./http";
import { useApiData } from "./useApiData";

afterEach(cleanup);

function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useApiData", () => {
  it("1. returns data after a successful fetch (loading first, then data)", async () => {
    const { result } = renderHook(() => useApiData(async () => ({ n: 1 }), []));

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toEqual({ n: 1 });
    expect(result.current.error).toBeNull();
    expect(result.current.errorStatus).toBeNull();
  });

  it("2. sets error state on a failed request, keeps the HTTP status, and reload() retries", async () => {
    let fail = true;
    const fetcher = vi.fn(async () => {
      if (fail) throw new ApiError(503, "503 Service Unavailable: down");
      return "recovered";
    });
    const { result } = renderHook(() => useApiData(fetcher, []));

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("503 Service Unavailable: down");
    expect(result.current.errorStatus).toBe(503);

    fail = false;
    act(() => result.current.reload());
    expect(result.current.loading).toBe(true); // retry shows loading, not the stale error
    await waitFor(() => expect(result.current.data).toBe("recovered"));
    expect(result.current.error).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("2b. a non-ApiError failure has a message and a null status", async () => {
    const { result } = renderHook(() =>
      useApiData(async () => {
        throw new Error("boom");
      }, []),
    );
    await waitFor(() => expect(result.current.error).toBe("boom"));
    expect(result.current.errorStatus).toBeNull();
  });

  it("3. changing the query key triggers a new fetch; re-rendering with the same key does not", async () => {
    const fetcher = vi.fn(async (_signal: AbortSignal, id: number) => `repo-${id}`);
    const { result, rerender } = renderHook(
      ({ id }) => useApiData((signal) => fetcher(signal, id), [id]),
      { initialProps: { id: 1 } },
    );
    await waitFor(() => expect(result.current.data).toBe("repo-1"));
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ id: 1 }); // same key
    expect(fetcher).toHaveBeenCalledTimes(1);

    rerender({ id: 2 });
    await waitFor(() => expect(result.current.data).toBe("repo-2"));
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(fetcher.mock.calls.map((c) => c[1])).toEqual([1, 2]);
  });

  it("4. unmounting aborts the in-flight request and a late result changes nothing", async () => {
    const d = deferred<string>();
    let signal!: AbortSignal;
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result, unmount } = renderHook(() =>
      useApiData((s) => {
        signal = s;
        return d.promise;
      }, []),
    );
    expect(signal.aborted).toBe(false);
    expect(result.current.loading).toBe(true);

    unmount();
    expect(signal.aborted).toBe(true);

    await act(async () => {
      d.resolve("too late");
      await d.promise;
    });
    expect(errors).not.toHaveBeenCalled(); // no "state update on unmounted component" noise
    errors.mockRestore();
  });

  it("5. a fast key change never lets a slow, older response overwrite the newer one", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const signals: AbortSignal[] = [];
    const { result, rerender } = renderHook(
      ({ id }) =>
        useApiData(
          (s) => {
            signals.push(s);
            return id === 1 ? first.promise : second.promise;
          },
          [id],
        ),
      { initialProps: { id: 1 } },
    );

    rerender({ id: 2 }); // user switches repo before repo 1 answered
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);

    await act(async () => {
      second.resolve("repo-2");
      await second.promise;
    });
    await waitFor(() => expect(result.current.data).toBe("repo-2"));

    await act(async () => {
      first.resolve("repo-1 (stale)"); // resolves last, but belongs to the old selection
      await first.promise;
    });
    expect(result.current.data).toBe("repo-2");
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("5b. while the next key is loading, the previous key's data is not shown", async () => {
    const second = deferred<string>();
    const { result, rerender } = renderHook(
      ({ id }) => useApiData(async () => (id === 1 ? "repo-1" : second.promise), [id]),
      { initialProps: { id: 1 } },
    );
    await waitFor(() => expect(result.current.data).toBe("repo-1"));

    rerender({ id: 2 });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull(); // not "repo-1": that belongs to the previous selection

    await act(async () => {
      second.resolve("repo-2");
      await second.promise;
    });
    await waitFor(() => expect(result.current.data).toBe("repo-2"));
  });
});
