export interface Concept {
  slug: string;
  title: string;
  summary: string;
  definition: string;
  why_anger: string;
  practice: string;
  reflection: string;
  tags: string[];
  source_notes?: string | null;
  order_index: number;
}

export interface Resource {
  id: number;
  title: string;
  creator?: string | null;
  type: string;
  description?: string | null;
  url?: string | null;
  tags: string[];
  beginner_level: boolean;
  related_concepts: string[];
}

export interface JournalEntry {
  id: number;
  created_at: string;
  first_arrow?: string | null;
  second_arrow?: string | null;
  body_sensation?: string | null;
  chosen_response?: string | null;
  reflection?: string | null;
  concept_slug?: string | null;
}

export type JournalEntryCreate = Omit<JournalEntry, "id" | "created_at">;
