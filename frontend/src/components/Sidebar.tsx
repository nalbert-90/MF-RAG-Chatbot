import type { Scheme } from "../types";
import {
  categoryLabel,
  schemePlaceholder,
  splitSchemeName,
} from "../lib/fundDisplay";

interface SidebarProps {
  schemes: Scheme[];
  selectedSchemeId: string | null;
  onSelectScheme: (scheme: Scheme) => void;
}

const TOPICS = [
  "Expense ratio",
  "Exit load",
  "SIP minimum",
  "Lock-in",
  "Benchmark",
] as const;

export function Sidebar({
  schemes,
  selectedSchemeId,
  onSelectScheme,
}: SidebarProps) {
  return (
    <aside className="hidden md:flex flex-col h-screen p-4 gap-4 bg-surface-container border-r border-border-subtle fixed left-0 top-0 w-sidebar-width z-20">
      <div className="flex flex-col gap-1 mb-2">
        <h1 className="text-xl font-extrabold text-primary">HDFC Fund Facts</h1>
        <p className="text-[13px] font-medium text-text-muted">
          Facts-only FAQ · Groww-curated sources
        </p>
      </div>

      <div className="bg-disclaimer-bg text-disclaimer-text p-3 rounded-lg flex items-start gap-2 border border-[#FDE68A] shrink-0">
        <span className="material-symbols-outlined text-[18px]">info</span>
        <p className="text-sm font-medium">Facts-only. No investment advice.</p>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide py-2 flex flex-col gap-6">
        <div className="flex flex-col gap-2">
          <h3 className="text-[13px] font-medium text-text-muted uppercase tracking-wider px-2">
            Funds in scope
          </h3>
          {schemes.map((scheme) => {
            const { title, subtitle } = splitSchemeName(scheme.name);
            const isSelected = scheme.scheme_id === selectedSchemeId;

            return (
              <button
                key={scheme.scheme_id}
                type="button"
                onClick={() => onSelectScheme(scheme)}
                title={schemePlaceholder(scheme)}
                className={`flex items-center justify-between text-left transition-colors duration-200 px-4 py-3 rounded-lg border ${
                  isSelected
                    ? "bg-surface-container-highest border-primary/30"
                    : "border-transparent hover:bg-surface-container-highest hover:border-border-subtle"
                }`}
              >
                <div className="flex flex-col gap-1 min-w-0 pr-2">
                  <span className="text-sm font-medium text-on-background truncate">
                    {title}
                  </span>
                  <span className="text-xs text-text-muted">{subtitle}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="bg-surface-dim text-on-surface text-[10px] font-medium px-2 py-0.5 rounded-sm">
                    {categoryLabel(scheme.category)}
                  </span>
                  <a
                    href={scheme.groww_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(event) => event.stopPropagation()}
                    className="text-outline hover:text-primary"
                    aria-label={`Open ${scheme.name} on Groww`}
                  >
                    <span className="material-symbols-outlined text-[16px]">
                      open_in_new
                    </span>
                  </a>
                </div>
              </button>
            );
          })}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-[13px] font-medium text-text-muted uppercase tracking-wider px-2">
            What you can ask
          </h3>
          <ul className="text-sm text-on-surface-variant space-y-1.5 px-4">
            {TOPICS.map((topic) => (
              <li key={topic} className="flex items-center gap-2">
                <span className="w-1 h-1 bg-outline rounded-full" />
                {topic}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-auto pt-4 border-t border-border-subtle flex items-center justify-between text-xs text-text-muted px-2">
        <div className="flex items-center gap-1">
          <span className="material-symbols-outlined text-[14px]">bolt</span>
          <span>Powered by Groww</span>
        </div>
        <span>No PII collected</span>
      </div>
    </aside>
  );
}
