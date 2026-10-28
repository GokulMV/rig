import { ChevronLeft, ChevronRight } from "lucide-react";

/** Handles on the canvas edges that hide or show the side panes, as on syde. */
export function PaneToggles({
  left,
  right,
  onLeft,
  onRight,
  leftName,
  rightName,
}: {
  left: boolean;
  right: boolean;
  onLeft: () => void;
  onRight: () => void;
  leftName: string;
  rightName: string;
}) {
  return (
    <>
      <button
        type="button"
        className="edge-toggle edge-toggle--left"
        onClick={onLeft}
        aria-label={left ? `Show ${leftName}` : `Hide ${leftName}`}
        aria-expanded={!left}
      >
        {left ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
      </button>
      <button
        type="button"
        className="edge-toggle edge-toggle--right"
        onClick={onRight}
        aria-label={right ? `Show ${rightName}` : `Hide ${rightName}`}
        aria-expanded={!right}
      >
        {right ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
      </button>
    </>
  );
}
