interface ChatHeaderProps {
  apiConnected: boolean;
}

export function ChatHeader({ apiConnected }: ChatHeaderProps) {
  return (
    <header className="flex justify-between items-center w-full h-16 px-gutter bg-surface border-b border-border-subtle z-10 shrink-0">
      <div className="flex items-center gap-4">
        <h2 className="text-base font-semibold text-on-surface">Chat</h2>
      </div>

      <div className="flex items-center gap-4">
        <div
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full border ${
            apiConnected
              ? "bg-success-green/10 border-success-green/20"
              : "bg-error/10 border-error/20"
          }`}
        >
          <span
            className={`w-2 h-2 rounded-full ${
              apiConnected ? "bg-success-green animate-pulse" : "bg-error"
            }`}
          />
          <span
            className={`text-[13px] font-medium ${
              apiConnected ? "text-success-green" : "text-error"
            }`}
          >
            {apiConnected ? "API Connected" : "API Offline"}
          </span>
        </div>

        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container border border-border-subtle text-[13px] font-medium text-on-surface-variant">
          <span className="material-symbols-outlined text-[16px]">verified</span>
          Facts-only · No investment advice
        </div>
      </div>
    </header>
  );
}
