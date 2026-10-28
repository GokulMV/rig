import { Keyboard, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** Whether a key press belongs to a field being typed in (shortcuts leave it alone). */
export function typing(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  return Boolean(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)));
}

const MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export interface Shortcut {
  keys: string[];
  does: string;
}

/** The canvas's keyboard shortcuts: "?" opens this sheet (and the button beside Undo); Esc or
 * the close button shuts it and puts the focus back where it was. */
export function ShortcutsSheet({
  items,
  label = "Keyboard Shortcuts",
  button = true,
}: {
  items: Shortcut[];
  label?: string;
  /** False where the toolbar has no room: "?" alone opens it (the Undo button's title says so). */
  button?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const back = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const show = () => {
    back.current = document.activeElement as HTMLElement | null;
    setOpen(true);
  };
  const hide = () => {
    setOpen(false);
    back.current?.focus?.();
  };
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "?" && !typing(e)) {
        e.preventDefault();
        if (open) hide();
        else show();
      } else if (e.key === "Escape" && open) {
        e.preventDefault();
        hide();
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open]);
  return (
    <span className="shortcuts-wrap">
      {button ? (
      <button
        type="button"
        className="btn btn--small btn--quiet"
        aria-label={label}
        title={`${label} (?)`}
        aria-keyshortcuts="?"
        aria-expanded={open}
        onClick={() => (open ? hide() : show())}
      >
        <Keyboard size={14} aria-hidden="true" />
      </button>
      ) : null}
      {open ? (
        <div className="shortcuts" role="dialog" aria-label={label} data-no-drag>
          <div className="row row--between">
            <strong className="small">{label}</strong>
            <button ref={closeRef} type="button" className="btn btn--small btn--quiet" aria-label="Close the shortcuts" onClick={hide}>
              <X size={14} aria-hidden="true" />
            </button>
          </div>
          <dl className="shortcuts__list small">
            {items.map((s) => (
              <div key={s.does} className="shortcuts__row">
                <dt>
                  {s.keys.map((k, n) => (
                    <span key={k}>
                      {n ? " or " : null}
                      <kbd>{k.replace("Mod", MAC ? "⌘" : "Ctrl")}</kbd>
                    </span>
                  ))}
                </dt>
                <dd>{s.does}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </span>
  );
}
