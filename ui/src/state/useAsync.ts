/** A one-shot fetch with abort-on-unmount, for the views that load their own slice. */

import { useCallback, useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

export function useAsync<T>(run: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    run(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setData(value);
          setError(null);
        }
        return value;
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // `run` is recreated every render by callers; the caller-declared deps are
    // the real inputs, which is why they are spread here instead.
    // oxlint-disable-next-line exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
