import { useCallback, useEffect, useRef, useState } from "react";
import {
  askQuestion,
  checkHealth,
  fetchExamples,
  fetchSchemes,
  ApiError,
} from "./api/client";
import { ChatHeader } from "./components/ChatHeader";
import { ChatInput } from "./components/ChatInput";
import { ChatMessages } from "./components/ChatMessages";
import { ExampleCards } from "./components/ExampleCards";
import { MobileFundsBar } from "./components/MobileFundsBar";
import { Sidebar } from "./components/Sidebar";
import { WelcomeState } from "./components/WelcomeState";
import { schemePlaceholder } from "./lib/fundDisplay";
import type { ChatMessage, Scheme } from "./types";

function createId(): string {
  return crypto.randomUUID();
}

const DEFAULT_PLACEHOLDER = "Ask a factual question about an HDFC fund…";

export default function App() {
  const [schemes, setSchemes] = useState<Scheme[]>([]);
  const [examples, setExamples] = useState<string[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [selectedScheme, setSelectedScheme] = useState<Scheme | null>(null);
  const [apiConnected, setApiConnected] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const healthy = await checkHealth();
      if (cancelled) return;

      setApiConnected(healthy);
      if (!healthy) {
        setBootstrapError(
          "Cannot reach the API. Start the backend with: uvicorn src.api.main:app --reload",
        );
        return;
      }

      try {
        const [schemeList, exampleList] = await Promise.all([
          fetchSchemes(),
          fetchExamples(),
        ]);
        if (cancelled) return;
        setSchemes(schemeList);
        setExamples(exampleList);
        setBootstrapError(null);
      } catch (error) {
        if (cancelled) return;
        setBootstrapError(
          error instanceof ApiError
            ? error.message
            : "Failed to load schemes and examples.",
        );
      }
    }

    void bootstrap();
    const interval = window.setInterval(async () => {
      const healthy = await checkHealth();
      if (!cancelled) setApiConnected(healthy);
    }, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const submitQuestion = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isLoading) return;

      setInputValue("");
      setMessages((prev) => [
        ...prev,
        { id: createId(), role: "user", content: trimmed },
      ]);
      setIsLoading(true);

      try {
        const response = await askQuestion(trimmed);
        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: "assistant",
            content: response.answer,
            response,
          },
        ]);
      } catch (error) {
        const message =
          error instanceof ApiError
            ? error.message
            : "Unable to reach the assistant. Please try again.";
        setMessages((prev) => [
          ...prev,
          {
            id: createId(),
            role: "assistant",
            content: message,
            error: true,
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading],
  );

  const handleExampleSelect = (question: string) => {
    void submitQuestion(question);
  };

  const handleSchemeSelect = (scheme: Scheme) => {
    setSelectedScheme(scheme);
  };

  const showWelcome = messages.length === 0 && !isLoading;
  const inputPlaceholder = selectedScheme
    ? schemePlaceholder(selectedScheme)
    : DEFAULT_PLACEHOLDER;

  return (
    <div className="bg-background text-on-background h-screen overflow-hidden flex">
      <Sidebar
        schemes={schemes}
        selectedSchemeId={selectedScheme?.scheme_id ?? null}
        onSelectScheme={handleSchemeSelect}
      />

      <main className="flex-1 flex flex-col md:ml-sidebar-width w-full md:max-w-[calc(100%-320px)] relative">
        <div className="md:hidden bg-disclaimer-bg text-disclaimer-text px-4 py-2 flex items-center gap-2 border-b border-[#FDE68A] text-xs font-medium shrink-0">
          <span className="material-symbols-outlined text-[16px]">info</span>
          Facts-only. No investment advice.
        </div>
        <MobileFundsBar
          schemes={schemes}
          selectedSchemeId={selectedScheme?.scheme_id ?? null}
          onSelectScheme={handleSchemeSelect}
        />
        <ChatHeader apiConnected={apiConnected} />

        <div className="flex-1 overflow-y-auto px-margin-mobile md:px-gutter py-6 pb-32 flex flex-col items-center">
          <div className="w-full max-w-container-max flex flex-col gap-8">
            {bootstrapError && (
              <div className="rounded-lg border border-error/20 bg-error/5 px-4 py-3 text-sm text-error">
                {bootstrapError}
              </div>
            )}

            <WelcomeState show={showWelcome} />
            {showWelcome && (
              <ExampleCards
                examples={examples}
                onSelect={handleExampleSelect}
                disabled={isLoading || !apiConnected}
              />
            )}
            <ChatMessages messages={messages} isLoading={isLoading} />
            <div ref={chatEndRef} />
          </div>
        </div>

        <ChatInput
          value={inputValue}
          placeholder={inputPlaceholder}
          onChange={setInputValue}
          onSubmit={(question) => void submitQuestion(question)}
          disabled={isLoading || !apiConnected}
        />
      </main>
    </div>
  );
}
