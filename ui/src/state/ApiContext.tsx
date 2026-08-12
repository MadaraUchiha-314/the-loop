/** The one place the transport is chosen, so no view ever constructs a client. */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { HttpApi, type TheLoopApi } from "../api/client.ts";
import { DemoApi } from "../demo/client.ts";
import { loadSettings, saveSettings, type Settings } from "./settings.ts";

interface ApiContextValue {
  api: TheLoopApi;
  settings: Settings;
  updateSettings: (patch: Partial<Settings>) => void;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function ApiProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() => loadSettings());

  const updateSettings = useCallback((patch: Partial<Settings>) => {
    setSettings((current) => {
      const next = { ...current, ...patch };
      saveSettings(next);
      return next;
    });
  }, []);

  // Re-created only when the transport identity changes, so the board's polling
  // effect (keyed on `api`) restarts on a target change and on nothing else.
  const api = useMemo<TheLoopApi>(
    () => (settings.mode === "demo" ? new DemoApi() : new HttpApi(settings.baseUrl)),
    [settings.mode, settings.baseUrl],
  );

  const value = useMemo(() => ({ api, settings, updateSettings }), [api, settings, updateSettings]);
  return <ApiContext value={value}>{children}</ApiContext>;
}

export function useApi(): ApiContextValue {
  const value = useContext(ApiContext);
  if (!value) throw new Error("useApi must be used inside <ApiProvider>");
  return value;
}
