import type { AskResponse, Scheme } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? detail;
    } catch {
      // ignore parse errors
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const data = await request<{ status: string }>("/api/v1/health");
    return data.status === "ok";
  } catch {
    return false;
  }
}

export async function fetchSchemes(): Promise<Scheme[]> {
  const data = await request<{ schemes: Scheme[] }>("/api/v1/schemes");
  return data.schemes;
}

export async function fetchExamples(): Promise<string[]> {
  const data = await request<{ questions: string[] }>("/api/v1/examples");
  return data.questions;
}

export async function askQuestion(question: string): Promise<AskResponse> {
  return request<AskResponse>("/api/v1/ask", {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export { ApiError };
