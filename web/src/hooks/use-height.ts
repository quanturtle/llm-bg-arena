"use client";

import { useEffect, useRef, useState } from "react";

/** A ref to put on an element, and that element's current height in px. */
export function useHeight<Element extends HTMLElement>() {
  const ref = useRef<Element>(null);
  const [height, setHeight] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setHeight(entry.borderBoxSize[0]?.blockSize ?? element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, height] as const;
}
