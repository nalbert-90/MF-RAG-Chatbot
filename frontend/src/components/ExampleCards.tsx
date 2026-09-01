interface ExampleCardsProps {
  examples: string[];
  onSelect: (question: string) => void;
  disabled?: boolean;
}

export function ExampleCards({
  examples,
  onSelect,
  disabled = false,
}: ExampleCardsProps) {
  if (examples.length === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
      {examples.map((question) => (
        <button
          key={question}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(question)}
          className="text-left bg-surface-container-lowest border border-border-subtle p-4 rounded-xl hover:shadow-[0px_4px_12px_rgba(0,0,0,0.05)] hover:border-primary/30 transition-all group disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <span className="material-symbols-outlined text-primary mb-2 opacity-70 group-hover:opacity-100">
            forum
          </span>
          <p className="text-sm text-on-surface">&ldquo;{question}&rdquo;</p>
        </button>
      ))}
    </div>
  );
}
