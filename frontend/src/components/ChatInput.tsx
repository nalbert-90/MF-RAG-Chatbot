import { useState, type FormEvent, type KeyboardEvent } from "react";

interface ChatInputProps {
  value: string;
  placeholder: string;
  onChange: (value: string) => void;
  onSubmit: (question: string) => void;
  disabled?: boolean;
}

export function ChatInput({
  value,
  placeholder,
  onChange,
  onSubmit,
  disabled = false,
}: ChatInputProps) {
  const [focused, setFocused] = useState(false);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  };

  return (
    <div className="absolute bottom-0 left-0 w-full bg-gradient-to-t from-background via-background to-transparent pt-10 pb-6 px-margin-mobile md:px-gutter">
      <form
        onSubmit={handleSubmit}
        className="max-w-container-max mx-auto flex flex-col gap-2"
      >
        <div
          className={`relative flex items-center bg-surface-container-lowest border rounded-xl shadow-sm transition-all ${
            focused
              ? "border-primary ring-1 ring-primary"
              : "border-border-subtle"
          }`}
        >
          <input
            type="text"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={placeholder}
            className="w-full bg-transparent border-none focus:ring-0 text-sm py-4 pl-4 pr-12 text-on-surface placeholder-text-muted outline-none disabled:opacity-50"
            aria-label="Ask a factual question about an HDFC fund"
          />
          <button
            type="submit"
            disabled={disabled || !value.trim()}
            className="absolute right-2 p-2 bg-primary text-on-primary rounded-lg hover:bg-primary-container transition-colors flex items-center justify-center disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Send question"
          >
            <span className="material-symbols-outlined text-[20px]">arrow_upward</span>
          </button>
        </div>
        <p className="text-center text-xs text-text-muted">
          Do not share PAN, Aadhaar, account numbers, or personal details.
        </p>
      </form>
    </div>
  );
}
