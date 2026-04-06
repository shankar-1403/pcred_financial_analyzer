export const SESSION_TOKEN_KEY = "session_token";

/** Session length for client-side session_token (matches prior Login.jsx behavior). */
export const SESSION_TTL_MS = 2 * 60 * 60 * 1000;

export function createSessionToken() {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function clearSession() {
  localStorage.removeItem("auth");
  localStorage.removeItem("name");
  localStorage.removeItem(SESSION_TOKEN_KEY);
}
