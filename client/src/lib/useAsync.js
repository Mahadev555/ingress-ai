import { useCallback, useEffect, useState } from "react";

// Minimal data-fetching hook: runs `fn` on mount (and when `deps` change),
// exposing loading / data / error and a manual reload().
export function useAsync(fn, deps = [], { enabled = true } = {}) {
  const [state, setState] = useState({ loading: enabled, data: null, error: null });

  const run = useCallback(() => {
    if (!enabled) {
      setState({ loading: false, data: null, error: null });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => setState({ loading: false, data, error: null }))
      .catch((error) => setState({ loading: false, data: null, error }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    run();
  }, [run]);

  return { ...state, reload: run };
}
