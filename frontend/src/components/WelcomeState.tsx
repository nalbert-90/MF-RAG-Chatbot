interface WelcomeStateProps {
  show: boolean;
}

export function WelcomeState({ show }: WelcomeStateProps) {
  if (!show) return null;

  return (
    <div className="flex flex-col items-center text-center mt-8 mb-4">
      <div className="w-16 h-16 bg-primary-container rounded-2xl flex items-center justify-center mb-6 shadow-sm border border-border-subtle">
        <span className="material-symbols-outlined text-3xl text-white">
          analytics
        </span>
      </div>
      <h1 className="text-2xl font-semibold text-primary mb-3 tracking-tight">
        Ask factual questions about HDFC funds
      </h1>
      <p className="text-base text-on-surface-variant max-w-2xl mx-auto">
        I answer objective scheme facts from curated Groww pages — expense ratio,
        exit load, SIP minimum, lock-in, and benchmark. I do not provide
        investment advice or return calculations.
      </p>
    </div>
  );
}
