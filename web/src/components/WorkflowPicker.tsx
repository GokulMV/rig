import type { Workflow } from "../lib/types";

/** Shown only when there is a choice to make. */
export function WorkflowPicker({
  workflows,
  value,
  onChange,
}: {
  workflows: Workflow[] | null;
  value: string | null;
  onChange: (id: string) => void;
}) {
  if (!workflows || workflows.length < 2) return null;
  return (
    <select
      className="select"
      style={{ width: "auto", maxWidth: 220 }}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Choose workflow"
    >
      {workflows.map((w) => (
        <option key={w.id} value={w.id}>
          {w.name}
        </option>
      ))}
    </select>
  );
}
