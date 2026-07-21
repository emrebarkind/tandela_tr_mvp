"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

const Spline = dynamic(() => import("@splinetool/react-spline"), {
  ssr: false,
  loading: () => null,
});

const SCENE_URL = "https://prod.spline.design/pRiQP0AFEEekuqx5/scene.splinecode";
const FALLBACK_AFTER_MS = 1800;
const LIGHTWEIGHT_AFTER_MS = 5200;

type AnalysisLoadingToothProps = {
  message?: string;
};

export function AnalysisLoadingTooth({ message = "Taslak hazırlanıyor..." }: AnalysisLoadingToothProps) {
  const [isSplineLoaded, setIsSplineLoaded] = useState(false);
  const [useFallback, setUseFallback] = useState(false);
  const [isLongWait, setIsLongWait] = useState(false);
  const forceFallback = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("spline_fallback") === "1";
  }, []);

  useEffect(() => {
    setIsSplineLoaded(false);
    setIsLongWait(false);
    setUseFallback(forceFallback);
    if (forceFallback) return undefined;

    const fallbackTimer = window.setTimeout(() => {
      setUseFallback(true);
    }, FALLBACK_AFTER_MS);
    const lightweightTimer = window.setTimeout(() => {
      setUseFallback(true);
      setIsLongWait(true);
    }, LIGHTWEIGHT_AFTER_MS);
    return () => {
      window.clearTimeout(fallbackTimer);
      window.clearTimeout(lightweightTimer);
    };
  }, [forceFallback]);

  const statusMessage = isLongWait ? "Analiz devam ediyor..." : message;
  const helperMessage = isLongWait
    ? "Klinik çıkarım aşamaları çalışıyor. Ekran kilitli değil; sonuç hazır olunca otomatik açılacak."
    : "Görüşme metni klinik not, diş şeması ve TDB kod taslağına dönüştürülüyor.";

  return (
    <div className="pointer-events-auto fixed inset-0 z-50 grid place-items-center bg-background/60 px-6 backdrop-blur-sm">
      <div className={`w-full rounded-[32px] border border-border bg-card/88 p-6 text-center shadow-panel backdrop-blur-md transition-all ${isLongWait ? "max-w-sm" : "max-w-md"}`}>
        <div className={`relative mx-auto grid aspect-square w-full place-items-center overflow-hidden rounded-[28px] border border-border bg-secondary/45 transition-all ${isLongWait ? "max-w-[168px]" : "max-w-[280px]"}`}>
          {!useFallback && !isLongWait ? (
            <Spline
              scene={SCENE_URL}
              onLoad={() => {
                setIsSplineLoaded(true);
                setUseFallback(false);
              }}
              onError={() => setUseFallback(true)}
              className={`absolute inset-0 size-full transition-opacity duration-300 ${isSplineLoaded ? "opacity-100" : "opacity-0"}`}
            />
          ) : null}

          {useFallback || !isSplineLoaded ? <FallbackToothAnimation /> : null}
        </div>

        <p className="mt-5 text-base font-semibold text-foreground">{statusMessage}</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{helperMessage}</p>
      </div>
    </div>
  );
}

function FallbackToothAnimation() {
  return (
    <div className="grid place-items-center">
      <div className="relative grid size-28 place-items-center rounded-full border border-ring/25 bg-card/70 shadow-card">
        <span className="klinia-pulse-ring absolute inset-0 rounded-full border border-ring/30" aria-hidden="true" />
        <svg
          className="klinia-slow-rotate relative size-14 text-primary"
          viewBox="0 0 64 64"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M20.5 8.5c4.2-1.2 7.2 1.3 10.1 1.3 3 0 5.9-2.5 10.2-1.3 7.6 2.1 10.5 10.4 8 18.7-1.1 3.7-3.1 6.7-4.2 11.2-1.7 6.7-2.7 15.8-8 15.8-3.6 0-3.4-8.8-6-8.8s-2.4 8.8-6 8.8c-5.3 0-6.3-9.1-8-15.8-1.1-4.5-3.1-7.5-4.2-11.2-2.5-8.3.4-16.6 8.1-18.7Z"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2.2"
          />
          <path
            d="M24 18.5c2.4 1.4 4.7 2.1 6.8 2.1s4.2-.7 6.7-2.1"
            stroke="currentColor"
            strokeLinecap="round"
            strokeWidth="1.7"
            opacity="0.42"
          />
        </svg>
      </div>
      <svg className="mt-6 h-10 w-44 text-primary" viewBox="0 0 176 40" role="img" aria-label="Analiz ilerliyor">
        <path
          className="klinia-wave-line"
          d="M2 20 C18 8, 30 8, 46 20 S74 32, 90 20 S118 8, 134 20 S160 32, 174 20"
          fill="none"
          stroke="currentColor"
          strokeLinecap="round"
          strokeWidth="1.5"
        />
      </svg>
    </div>
  );
}
