/**
 * API client for the LLM Council backend.
 */

const API_BASE = 'http://localhost:8001';

/** Build a full URL for a stored attachment. Accepts backend-relative
 *  ("/attachments/...") or already-absolute (http / data:) URLs. */
export function attachmentUrl(url) {
  if (!url) return '';
  if (url.startsWith('http') || url.startsWith('data:')) return url;
  return `${API_BASE}${url}`;
}

export const api = {
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) throw new Error('Failed to list conversations');
    return response.json();
  },

  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error('Failed to create conversation');
    return response.json();
  },

  async getConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
    if (!response.ok) throw new Error('Failed to get conversation');
    return response.json();
  },

  /** Which council CLIs are installed/logged-in on this machine. */
  async getAgentsStatus() {
    const response = await fetch(`${API_BASE}/api/agents/status`);
    if (!response.ok) throw new Error('Failed to get agents status');
    return response.json();
  },

  /** Dynamic model lists per CLI ({cli: {models, live}}). */
  async getModels() {
    const response = await fetch(`${API_BASE}/api/models`);
    if (!response.ok) throw new Error('Failed to get models');
    return response.json();
  },

  /**
   * Send a message and receive streaming stage updates.
   * @param {string} conversationId
   * @param {string} content
   * @param {object} opts - { attachments?: [{filename, mime, data_base64}], council?: object }
   * @param {function} onEvent - (eventType, event) => void
   */
  async sendMessageStream(conversationId, content, opts, onEvent) {
    const { attachments = [], council = null } = opts || {};
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, attachments, council }),
      }
    );

    if (!response.ok) throw new Error('Failed to send message');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep the trailing partial line for the next chunk

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            onEvent(event.type, event);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
          }
        }
      }
    }
  },
};
