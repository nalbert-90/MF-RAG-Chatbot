import type { AskResponse, ChatMessage } from "../types";
import { citationDisplay } from "../lib/fundDisplay";

function AssistantBubble({ response }: { response: AskResponse }) {
  const isAnswered = response.status === "answered";
  const isRedirected = response.status === "redirected";
  const showCitation = Boolean(response.citation_url);

  return (
    <div className="bg-surface-container-lowest border border-border-subtle px-5 py-4 rounded-2xl rounded-tl-sm max-w-[85%] sm:max-w-[70%] shadow-sm flex flex-col gap-3">
      <p className="text-sm text-on-surface whitespace-pre-wrap">{response.answer}</p>

      {showCitation && (
        <div className="flex flex-col gap-2 mt-1">
          <div className="flex flex-col gap-1 p-3 bg-surface rounded-lg border border-border-subtle">
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <span className="material-symbols-outlined text-[14px]">link</span>
              <a
                href={response.citation_url!}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-secondary underline decoration-border-subtle hover:decoration-secondary underline-offset-2 break-all"
              >
                {citationDisplay(response.citation_url!)}
              </a>
            </div>
            {response.last_updated && (
              <div className="flex items-center gap-2 text-xs text-text-muted">
                <span className="material-symbols-outlined text-[14px]">update</span>
                <span>Last updated from sources: {response.last_updated}</span>
              </div>
            )}
          </div>

          {isRedirected && (
            <a
              href={response.citation_url!}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 self-start px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-medium hover:bg-primary-container transition-colors"
            >
              View on Groww
              <span className="material-symbols-outlined text-[16px]">open_in_new</span>
            </a>
          )}
        </div>
      )}

      <div className="flex items-start gap-1.5 text-disclaimer-text bg-disclaimer-bg/50 px-2 py-1.5 rounded text-[11px] leading-tight">
        <span className="material-symbols-outlined text-[14px] shrink-0 mt-0.5">
          {isAnswered ? "verified" : "warning"}
        </span>
        <span>{response.disclaimer}</span>
      </div>
    </div>
  );
}

function ErrorBubble({ content }: { content: string }) {
  return (
    <div className="bg-error/5 border border-error/20 px-5 py-4 rounded-2xl rounded-tl-sm max-w-[85%] sm:max-w-[70%] shadow-sm">
      <p className="text-sm text-error">{content}</p>
    </div>
  );
}

function LoadingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-center gap-3 text-text-muted px-2">
        <div className="flex gap-1">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="w-1.5 h-1.5 bg-outline rounded-full animate-bounce-dot"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
        <span className="text-xs italic">Looking up facts…</span>
      </div>
    </div>
  );
}

interface ChatMessagesProps {
  messages: ChatMessage[];
  isLoading: boolean;
}

export function ChatMessages({ messages, isLoading }: ChatMessagesProps) {
  if (messages.length === 0 && !isLoading) return null;

  return (
    <div className="flex flex-col gap-6">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.id} className="flex justify-end">
            <div className="bg-primary text-on-primary px-5 py-3 rounded-2xl rounded-tr-sm max-w-[85%] sm:max-w-[70%] shadow-sm">
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ) : message.error ? (
          <div key={message.id} className="flex justify-start">
            <ErrorBubble content={message.content} />
          </div>
        ) : message.response ? (
          <div key={message.id} className="flex justify-start">
            <AssistantBubble response={message.response} />
          </div>
        ) : null,
      )}
      {isLoading && <LoadingIndicator />}
    </div>
  );
}
