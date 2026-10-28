import { useRef } from "react";

/** A drag handle on a side pane's inner edge: drag, or use the arrow keys, to change its width. */
export function PaneResizer({
  side,
  width,
  min,
  max,
  label,
  onResize,
  onReset,
}: {
  side: "left" | "right";
  width: number;
  min: number;
  max: number;
  label: string;
  onResize: (w: number) => void;
  onReset: () => void;
}) {
  const start = useRef<{ x: number; w: number } | null>(null);
  return (
    <div
      className={`resizer resizer--${side}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={(e) => {
        e.preventDefault();
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        start.current = { x: e.clientX, w: width };
        document.body.classList.add("is-resizing");
      }}
      onPointerMove={(e) => {
        const s = start.current;
        if (!s) return;
        const dx = e.clientX - s.x;
        onResize(side === "left" ? s.w + dx : s.w - dx);
      }}
      onPointerUp={() => {
        start.current = null;
        document.body.classList.remove("is-resizing");
      }}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 40 : 10;
        const grow = side === "left" ? "ArrowRight" : "ArrowLeft";
        const shrink = side === "left" ? "ArrowLeft" : "ArrowRight";
        if (e.key === grow) onResize(width + step);
        else if (e.key === shrink) onResize(width - step);
        else if (e.key === "Home") onResize(min);
        else if (e.key === "End") onResize(max);
        else return;
        e.preventDefault();
      }}
    />
  );
}
