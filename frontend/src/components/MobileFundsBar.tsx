import type { Scheme } from "../types";
import { categoryLabel, splitSchemeName } from "../lib/fundDisplay";

interface MobileFundsBarProps {
  schemes: Scheme[];
  selectedSchemeId: string | null;
  onSelectScheme: (scheme: Scheme) => void;
}

export function MobileFundsBar({
  schemes,
  selectedSchemeId,
  onSelectScheme,
}: MobileFundsBarProps) {
  if (schemes.length === 0) return null;

  return (
    <div className="md:hidden border-b border-border-subtle bg-surface-container-low px-margin-mobile py-3 shrink-0">
      <p className="text-[11px] font-medium uppercase tracking-wider text-text-muted mb-2">
        Funds in scope
      </p>
      <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1">
        {schemes.map((scheme) => {
          const { title } = splitSchemeName(scheme.name);
          const isSelected = scheme.scheme_id === selectedSchemeId;

          return (
            <button
              key={scheme.scheme_id}
              type="button"
              onClick={() => onSelectScheme(scheme)}
              className={`shrink-0 rounded-lg border px-3 py-2 text-left transition-colors ${
                isSelected
                  ? "border-primary/40 bg-primary/5"
                  : "border-border-subtle bg-surface-container-lowest"
              }`}
            >
              <span className="block text-xs font-medium text-on-surface whitespace-nowrap">
                {title.replace("HDFC ", "")}
              </span>
              <span className="block text-[10px] text-text-muted mt-0.5">
                {categoryLabel(scheme.category)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
