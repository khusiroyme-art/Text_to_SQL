// Every backend call goes through here, and every one of them resolves to the
// same shape: { sql, result, error, columns, attempts }. `error` is the single
// place to look - the backend puts rejected SQL, a dead API key and an
// exhausted retry budget all in that one field - so no caller branches on
// status codes.

const BASE = "/api";

async function post(path, body) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    // A network failure has no JSON body, so synthesise the standard shape
    // rather than making every caller handle a second error channel.
    return { sql: null, result: null, columns: null, attempts: 0, error: "Cannot reach the backend. Is it running on port 5000?" };
  }
  return response.json();
}

export const askQuestion = (question, dbId) => post("/query", { question, db_id: dbId });

export const runSql = (sql, dbId) => post("/execute", { sql, db_id: dbId });

export async function fetchHealth() {
  const response = await fetch(`${BASE}/health`);
  return response.json();
}

export async function uploadDatabase(file) {
  const form = new FormData();
  form.append("file", file);
  // No Content-Type header: the browser must set the multipart boundary.
  try {
    const response = await fetch(`${BASE}/databases`, { method: "POST", body: form });
    return response.json();
  } catch {
    return { error: "Upload failed - is the backend running on port 5000?" };
  }
}

export async function fetchSchema(dbId) {
  const response = await fetch(`${BASE}/schema/${encodeURIComponent(dbId)}`);
  return response.json();
}
