import { Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import { searchItems } from "../lib/librarySearch";
import type { LabSkill } from "../lib/types";

/** Yours first, then each GitHub repository: the order the picker lists them in. */
export function skillGroups(list: LabSkill[]): [string, LabSkill[]][] {
  const groups = new Map<string, LabSkill[]>();
  for (const s of list) {
    const label = s.source === "github" ? `GitHub · ${s.repo}` : "Yours";
    groups.set(label, [...(groups.get(label) ?? []), s]);
  }
  return [...groups].sort(([a], [b]) =>
    a === "Yours" ? -1 : b === "Yours" ? 1 : 0,
  );
}

/**
 * Pick a skill for a step: type to filter by name or description, up/down and Enter to choose
 * (the ARIA combobox pattern, with a grouped listbox). Replaces a native select of ~150 options.
 */
export function SkillPicker({
  id,
  skills,
  chosen,
  why = {},
  onPick,
}: {
  /** The input's id, for the field's <label>. */
  id: string;
  skills: LabSkill[];
  /** Paths already on the step: shown, marked, not picked twice. */
  chosen: string[];
  /** Why each skill on the step was picked (the matcher's reason), by path. */
  why?: Record<string, string>;
  onPick: (s: LabSkill) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  // Grouped; while typing, best match first and the group with the best match first.
  const groups = useMemo(() => {
    if (!q.trim()) return skillGroups(skills);
    const found = searchItems(
      skills.map((s) => ({
        name: s.name,
        description: s.description,
        extra: s.repo ?? "",
        s,
      })),
      q,
    ).map((x) => x.s);
    const m = new Map<string, LabSkill[]>();
    for (const s of found) {
      const label = s.source === "github" ? `GitHub · ${s.repo}` : "Yours";
      m.set(label, [...(m.get(label) ?? []), s]);
    }
    return [...m];
  }, [skills, q]);
  const flat = groups.flatMap(([, l]) => l);
  const optionId = (i: number) => `${listId}-opt-${i}`;
  const free = (k: number) => !chosen.includes(flat[k]?.path);
  // The active option skips skills already on the step (they can't be picked again).
  const at = (() => {
    const start = Math.min(active, Math.max(0, flat.length - 1));
    for (let k = 0; k < flat.length; k++)
      if (free((start + k) % flat.length)) return (start + k) % flat.length;
    return start;
  })();

  const move = (dir: 1 | -1) => {
    const n = flat.length;
    for (let k = 1; k <= n; k++) {
      const i = (((at + dir * k) % n) + n) % n;
      if (free(i)) return setActive(i);
    }
  };
  // Opened near the bottom of a scrolling panel: bring the list into view.
  useEffect(() => {
    if (open) list.current?.scrollIntoView?.({ block: "nearest" });
  }, [open]);
  // Keep the active option in view.
  useEffect(() => {
    if (open)
      list.current
        ?.querySelector(`#${CSS.escape(optionId(at))}`)
        ?.scrollIntoView?.({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at, open]);
  const pick = (s: LabSkill | undefined) => {
    if (!s || chosen.includes(s.path)) return;
    onPick(s);
    setQ("");
    setActive(0);
    setOpen(false);
  };

  const empty = skills.length === 0;
  let i = -1;
  return (
    <div className="skillpick">
      <div className="skillpick__field">
        <Search size={14} aria-hidden="true" />
        <input
          ref={input}
          id={id}
          className="skillpick__input"
          role="combobox"
          aria-expanded={open && !empty}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && flat.length ? optionId(at) : undefined}
          autoComplete="off"
          disabled={empty}
          placeholder={
            empty
              ? "No skills to choose from yet"
              : `Choose from ${skills.length} skill${skills.length === 1 ? "" : "s"}…`
          }
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
              e.preventDefault();
              if (!open) {
                setOpen(true);
                return;
              }
              move(e.key === "ArrowDown" ? 1 : -1);
            } else if (e.key === "Enter") {
              if (open && flat.length) {
                e.preventDefault();
                pick(flat[at]);
              }
            } else if (e.key === "Escape") {
              // Closes the list first, then clears what was typed; nothing else hears it.
              if (open || q) {
                e.preventDefault();
                e.stopPropagation();
                if (open) setOpen(false);
                else setQ("");
              }
            }
          }}
        />
      </div>
      {open && !empty && flat.length === 0 ? (
        <p className="skillpick__none small muted" role="status">
          No skill matches “{q.trim()}”.
        </p>
      ) : null}
      {open && !empty && flat.length ? (
        <div
          ref={list}
          id={listId}
          className="skillpick__list"
          role="listbox"
          aria-label="Skills"
        >
          {groups.map(([label, group], g) => (
            <div
              key={label}
              role="group"
              aria-labelledby={`${listId}-g${g}`}
              className="skillpick__group"
            >
              <div id={`${listId}-g${g}`} className="skillpick__grouplabel">
                {label}
              </div>
              {group.map((s) => {
                i += 1;
                const n = i;
                const added = chosen.includes(s.path);
                return (
                  <div
                    key={s.path}
                    id={optionId(n)}
                    role="option"
                    aria-selected={n === at}
                    aria-disabled={added || undefined}
                    className={`skillpick__option${n === at ? " is-active" : ""}${added ? " is-added" : ""}`}
                    // Keep the focus in the input, so typing goes on working.
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseMove={() => n !== at && !added && setActive(n)}
                    onClick={() => pick(s)}
                  >
                    <span className="skillpick__name">
                      {s.name}
                      {added ? (
                        <span className="skillpick__added">
                          {" "}
                          · on this step
                        </span>
                      ) : null}
                    </span>
                    {added && why[s.path] ? (
                      <span className="skillpick__desc skillpick__why">{why[s.path]}</span>
                    ) : s.description ? (
                      <span className="skillpick__desc">{s.description}</span>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
