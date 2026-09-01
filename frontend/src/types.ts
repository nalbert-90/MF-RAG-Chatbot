export type AskStatus = "answered" | "refused" | "redirected";

export interface AskResponse {
  status: AskStatus;
  answer: string;
  citation_url: string | null;
  last_updated: string | null;
  disclaimer: string;
}

export interface Scheme {
  scheme_id: string;
  name: string;
  category: string;
  groww_url: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AskResponse;
  error?: boolean;
}
