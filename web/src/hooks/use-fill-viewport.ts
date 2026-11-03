"use client";

import { useCallback } from "react";

/**
 * A ref callback whose element stretches from where it starts on screen to the bottom of the
 * window, less `gapPx`, while `query` matches; it follows the page as it scrolls until a sticky
 * top holds it. The element may mount after the page does.
 */
export function useFillViewport<Element extends HTMLElement>(query: string, gapPx: number) {
  return useCallback(
    (element: Element | null) => {
      if (!element) return;
      const media = window.matchMedia(query);
      let frame = 0;
      const update = () => {
        frame = 0;
        element.style.height = media.matches ? `${window.innerHeight - element.getBoundingClientRect().top - gapPx}px` : "";
      };
      const schedule = () => {
        if (!frame) frame = requestAnimationFrame(update);
      };
      update();
      window.addEventListener("scroll", schedule, { passive: true });
      window.addEventListener("resize", schedule);
      media.addEventListener("change", schedule);
      return () => {
        cancelAnimationFrame(frame);
        window.removeEventListener("scroll", schedule);
        window.removeEventListener("resize", schedule);
        media.removeEventListener("change", schedule);
      };
    },
    [query, gapPx],
  );
}
