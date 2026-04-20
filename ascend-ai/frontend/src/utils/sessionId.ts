/**
 * ASCEND AI — Session ID utility
 * Generate a UUID on first load and persist it in sessionStorage.
 * The backend uses this to scope conversation history per browser tab.
 */
export function getSessionId(): string {
  let id = sessionStorage.getItem('ascend_session_id')
  if (!id) {
    id = crypto.randomUUID()
    sessionStorage.setItem('ascend_session_id', id)
  }
  return id
}
