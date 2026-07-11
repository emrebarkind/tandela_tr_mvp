"use client";

import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

type HeaderState = {
  title?: string;
  subtitle?: string;
  badge?: ReactNode;
  actions?: ReactNode;
};

type HeaderContextValue = {
  header: HeaderState;
  setHeader: (header: HeaderState) => void;
  clearHeader: () => void;
};

const HeaderContext = createContext<HeaderContextValue | null>(null);

export function HeaderProvider({ children }: { children: ReactNode }) {
  const [header, setHeader] = useState<HeaderState>({});
  const clearHeader = useCallback(() => setHeader({}), []);
  const value = useMemo(
    () => ({
      header,
      setHeader,
      clearHeader,
    }),
    [clearHeader, header],
  );

  return <HeaderContext.Provider value={value}>{children}</HeaderContext.Provider>;
}

export function useHeader() {
  const value = useContext(HeaderContext);
  if (!value) {
    throw new Error("useHeader must be used within HeaderProvider");
  }
  return value;
}
