/**
 * Pointer-based drag from the skill library onto a canvas. HTML drag-and-drop is avoided on
 * purpose: it does not work with touch and is unreliable under automation. A ghost card follows
 * the pointer; a registered drop target gets the drop in client coordinates.
 */

/** What a drop needs to know beyond the payload: a GitHub repo's category, say. */
export type DragMeta = Record<string, string>;

export interface DropTarget {
  el: () => HTMLElement | null;
  setOver: (over: boolean) => void;
  drop: (path: string, clientX: number, clientY: number, meta?: DragMeta) => void;
}

const targets = new Set<DropTarget>();
let suppressClick = false;

export function registerDropTarget(t: DropTarget): () => void {
  targets.add(t);
  return () => {
    targets.delete(t);
  };
}

function targetAt(x: number, y: number): DropTarget | null {
  for (const t of targets) {
    const el = t.el();
    if (!el) continue;
    const r = el.getBoundingClientRect();
    if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return t;
  }
  return null;
}

/** True once, right after a drag ended, so the click that follows does not also select. */
export function consumeDragClick(): boolean {
  const was = suppressClick;
  suppressClick = false;
  return was;
}

export function startSkillDrag(e: React.PointerEvent<HTMLElement>, path: string, name: string, meta?: DragMeta): void {
  if (e.button !== 0) return;
  const sx = e.clientX;
  const sy = e.clientY;
  let ghost: HTMLDivElement | null = null;
  let over: DropTarget | null = null;

  const move = (ev: PointerEvent) => {
    if (!ghost) {
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
      ghost = document.createElement("div");
      ghost.className = "drag-ghost";
      ghost.setAttribute("aria-hidden", "true");
      ghost.textContent = name;
      document.body.appendChild(ghost);
      document.body.classList.add("is-dragging-skill");
    }
    ghost.style.transform = `translate(${ev.clientX + 12}px, ${ev.clientY + 12}px)`;
    const t = targetAt(ev.clientX, ev.clientY);
    if (t !== over) {
      over?.setOver(false);
      t?.setOver(true);
      over = t;
    }
  };
  const end = (ev: PointerEvent) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", cancel);
    if (!ghost) return;
    ghost.remove();
    document.body.classList.remove("is-dragging-skill");
    // Swallow only the click this very release produces (if it lands on the item itself).
    suppressClick = true;
    setTimeout(() => {
      suppressClick = false;
    }, 0);
    over?.setOver(false);
    over?.drop(path, ev.clientX, ev.clientY, meta);
  };
  const cancel = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", end);
    window.removeEventListener("pointercancel", cancel);
    ghost?.remove();
    document.body.classList.remove("is-dragging-skill");
    over?.setOver(false);
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  window.addEventListener("pointercancel", cancel);
}
