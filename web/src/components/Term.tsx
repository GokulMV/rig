import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { useGlossary } from "../lib/glossary";

/** How long the pointer or focus rests on a (?) before it opens, and how long it may leave it
 * (towards the sentence) before it closes. */
export const TERM_OPEN_MS = 350;
const TERM_CLOSE_MS = 150;

/** A small (?) after a measurement word, at its first appearance on a page: one plain sentence
 * from the glossary skill. It opens on hover and on keyboard focus after a short delay, and on a
 * click or tap; it closes when the pointer or focus leaves, and on Esc. `k` is the glossary key
 * (pts, pair, baseline ...). */
export function Term({ k, label }: { k: string; label?: string }) {
  const g = useGlossary();
  // "hover" and "focus" close when they end; "click" stays until a click away, blur or Esc.
  const [open, setOpen] = useState<null | "hover" | "focus" | "click">(null);
  const id = useId();
  const ref = useRef<HTMLSpanElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const later = (fn: () => void, ms: number) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(fn, ms);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(null);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        window.clearTimeout(timer.current);
        setOpen(null);
      }
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  // Placed in the window, not the pane: a pane's edge (overflow) would cut the sentence off.
  // Below the (?), moved left as far as it must to stay on screen.
  const pop = useRef<HTMLSpanElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    if (!open || !btn.current || !pop.current) return setAt(null);
    const b = btn.current.getBoundingClientRect();
    const w = pop.current.offsetWidth;
    setAt({ top: b.bottom + 6, left: Math.max(8, Math.min(b.left - 8, window.innerWidth - w - 8)) });
  }, [open]);
  // Scrolling moves the (?) away from a sentence placed in the window: a hover or focus one closes.
  useEffect(() => {
    if (!open) return;
    const away = () => setOpen((o) => (o === "click" ? o : null));
    window.addEventListener("scroll", away, true);
    return () => window.removeEventListener("scroll", away, true);
  }, [open]);
  const t = g?.[k];
  const name = t?.term ?? label ?? k;
  return (
    <span
      className="term"
      ref={ref}
      data-no-drag
      // The sentence is part of the area: moving onto it keeps it open (WCAG 1.4.13, hoverable).
      onPointerEnter={(e) => {
        if (e.pointerType === "touch") return; // a tap is a click
        if (open) window.clearTimeout(timer.current);
        else later(() => setOpen((o) => o ?? "hover"), TERM_OPEN_MS);
      }}
      onPointerLeave={(e) => {
        if (e.pointerType === "touch") return;
        if (open === "hover") later(() => setOpen((o) => (o === "hover" ? null : o)), TERM_CLOSE_MS);
        else if (!open) window.clearTimeout(timer.current);
      }}
    >
      <button
        ref={btn}
        type="button"
        className="term__btn"
        aria-label={`What is ${name}?`}
        aria-expanded={Boolean(open)}
        aria-describedby={open ? id : undefined}
        onFocus={() => later(() => setOpen((o) => o ?? "focus"), TERM_OPEN_MS)}
        onBlur={() => {
          window.clearTimeout(timer.current);
          setOpen((o) => (o === "hover" ? o : null));
        }}
        onClick={(e) => {
          e.stopPropagation();
          window.clearTimeout(timer.current);
          setOpen((o) => (o === "click" ? null : "click"));
        }}
      >
        ?
      </button>
      {open ? (
        <span
          id={id}
          ref={pop}
          role="tooltip"
          className="term__pop"
          style={at ? { position: "fixed", top: at.top, left: at.left } : { visibility: "hidden" }}
        >
          <b>{name}</b>: {t?.short ?? "Loading…"}
        </span>
      ) : null}
    </span>
  );
}
