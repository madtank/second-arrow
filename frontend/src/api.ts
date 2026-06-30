import type { Concept, JournalEntry, JournalEntryCreate, Resource } from "./types";

// In dev, Vite proxies /api to the backend (see vite.config.ts).
// Override with VITE_API_BASE for other setups.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status}): ${path}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  getConcepts: () => request<Concept[]>("/api/concepts"),
  getConcept: (slug: string) => request<Concept>(`/api/concepts/${slug}`),
  getResources: () => request<Resource[]>("/api/resources"),
  getJournal: () => request<JournalEntry[]>("/api/journal"),
  getJournalEntry: (id: number) => request<JournalEntry>(`/api/journal/${id}`),
  createJournalEntry: (entry: JournalEntryCreate) =>
    request<JournalEntry>("/api/journal", {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  deleteJournalEntry: (id: number) =>
    request<void>(`/api/journal/${id}`, { method: "DELETE" }),
};
