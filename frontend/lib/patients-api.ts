export type PatientSummary = {
  id: string;
  initials: string | null;
  display_name: string | null;
  external_id: string | null;
  created_at: string;
  last_session_at: string | null;
  session_count: number;
  last_procedures: string[];
  status: string;
};

export type PatientSessionSummary = {
  id: string;
  status: string;
  session_type: "clinical_note" | "perio";
  started_at: string | null;
  completed_at: string | null;
  procedures: string[];
};

export type PatientSessions = {
  id: string;
  initials: string | null;
  display_name: string | null;
  external_id: string | null;
  created_at: string;
  sessions: PatientSessionSummary[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const AUTH_HEADERS = {
  "X-Klinia-Clinic-Id": process.env.NEXT_PUBLIC_KLINIA_CLINIC_ID ?? "dev-clinic",
  "X-Klinia-User-Id": process.env.NEXT_PUBLIC_KLINIA_USER_ID ?? "frontend-doctor",
  "X-Klinia-User-Role": process.env.NEXT_PUBLIC_KLINIA_USER_ROLE ?? "dentist",
};

export async function fetchPatients(query: string): Promise<PatientSummary[]> {
  const search = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : "";
  const response = await fetch(`${API_BASE}/patients${search}`, { headers: AUTH_HEADERS, cache: "no-store" });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<PatientSummary[]>;
}

export async function fetchPatientSessions(patientId: string): Promise<PatientSessions> {
  const response = await fetch(`${API_BASE}/patients/${encodeURIComponent(patientId)}/sessions`, {
    headers: AUTH_HEADERS,
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<PatientSessions>;
}

export async function createPatient(input: {
  display_name?: string | null;
  external_id?: string | null;
}): Promise<PatientSummary> {
  const response = await fetch(`${API_BASE}/patients`, {
    method: "POST",
    headers: { ...AUTH_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<PatientSummary>;
}

export async function attachPatientToSession(sessionId: string, patientId: string): Promise<void> {
  const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}/patient`, {
    method: "PATCH",
    headers: { ...AUTH_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId }),
  });
  if (!response.ok) throw new Error(await response.text());
}
