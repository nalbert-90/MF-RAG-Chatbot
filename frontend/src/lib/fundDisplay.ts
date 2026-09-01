import type { Scheme } from "../types";

const CATEGORY_LABELS: Record<string, string> = {
  "Mid Cap": "Mid Cap",
  "Commodity / FoF": "Commodity",
  Index: "Index",
  "Large Cap": "Large Cap",
  ELSS: "ELSS",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function splitSchemeName(name: string): { title: string; subtitle: string } {
  const parts = name.split(" - ");
  if (parts.length >= 2) {
    return {
      title: parts[0],
      subtitle: parts.slice(1).join(" - "),
    };
  }
  return { title: name, subtitle: "Direct Growth" };
}

export function citationDisplay(url: string): string {
  try {
    const parsed = new URL(url);
    return `${parsed.hostname}${parsed.pathname}`;
  } catch {
    return url;
  }
}

export function schemePlaceholder(scheme: Scheme): string {
  return `Ask about ${scheme.name}…`;
}
