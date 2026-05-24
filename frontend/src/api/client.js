const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API error ${res.status}`);
  }
  return res.json();
}

// Chat
export function sendMessage(conversationId, message) {
  return request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });
}

// Admin
export function getConversations() {
  return request('/api/admin/conversations');
}

export function getConversation(id) {
  return request(`/api/admin/conversations/${id}`);
}

export function getStats() {
  return request('/api/admin/stats');
}

export function getEscalations() {
  return request('/api/admin/escalations');
}

export function getDocuments() {
  return request('/api/admin/documents');
}

export async function uploadDocument({ file, title, documentType, organization, language }) {
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  if (documentType) form.append('document_type', documentType);
  if (organization) form.append('organization', organization);
  if (language) form.append('language', language);

  const res = await fetch(`${API_BASE}/api/admin/documents/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Upload failed (${res.status})`);
  }
  return res.json();
}

export async function deleteDocument(docId) {
  const res = await fetch(`${API_BASE}/api/admin/documents/${docId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Delete failed (${res.status})`);
  }
  return res.json();
}

export function updateEscalationStatus(conversationId, status) {
  return request(
    `/api/admin/escalations/${conversationId}/status?status=${status}`,
    { method: 'PATCH' },
  );
}

// Exports
export function exportSummary(fromDate, toDate) {
  window.open(`${API_BASE}/api/admin/export/summary?from_date=${fromDate}&to_date=${toDate}`);
}
