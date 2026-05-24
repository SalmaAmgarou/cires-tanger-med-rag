import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import StatsBar from '../components/admin/StatsBar';
import ConversationList from '../components/admin/ConversationList';
import ConversationDetail from '../components/admin/ConversationDetail';
import EscalationQueue from '../components/admin/EscalationQueue';
import DocumentsList from '../components/admin/DocumentsList';
import {
  getConversations, getConversation, getStats, getEscalations,
  getDocuments, updateEscalationStatus,
} from '../api/client';
import './AdminPage.css';

const REFRESH_INTERVAL = 10_000;

const NAV_ITEMS = [
  { key: 'conversations', label: 'Conversations', icon: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )},
  { key: 'escalations', label: 'Escalations', icon: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )},
  { key: 'documents', label: 'Corpus', icon: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
    </svg>
  )},
];

function AdminPage({ theme, toggleTheme }) {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [stats, setStats] = useState(null);
  const [escalations, setEscalations] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [tab, setTab] = useState('conversations');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [search, setSearch] = useState('');

  const fetchAll = useCallback(async () => {
    try {
      const [convos, st, esc, docs] = await Promise.all([
        getConversations().catch(() => []),
        getStats().catch(() => null),
        getEscalations().catch(() => []),
        getDocuments().catch(() => []),
      ]);
      setConversations(convos);
      setStats(st);
      setEscalations(esc);
      setDocuments(docs);
      setError(null);
    } catch {
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchAll]);

  const handleSelect = useCallback(async (id) => {
    setSelected(id);
    try {
      const data = await getConversation(id);
      setDetail(data);
    } catch {
      setDetail(null);
    }
  }, []);

  const handleEscalationStatusChange = useCallback(async (conversationId, status) => {
    try {
      await updateEscalationStatus(conversationId, status);
      fetchAll();
    } catch {
      // ignore
    }
  }, [fetchAll]);

  const filteredConvos = search
    ? conversations.filter(c =>
        (c.user_id || '').toLowerCase().includes(search.toLowerCase()) ||
        (c.last_message || '').toLowerCase().includes(search.toLowerCase()) ||
        (c.id || '').toLowerCase().includes(search.toLowerCase())
      )
    : conversations;

  const counts = {
    conversations: conversations.length,
    escalations: escalations.length,
    documents: documents.length,
  };

  return (
    <div className="admin">
      {/* Sidebar */}
      <aside className={`admin-sidebar ${sidebarOpen ? 'admin-sidebar--open' : ''}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-logo">TM</div>
          <div>
            <div className="sidebar-brand-name">RAG Admin</div>
            <div className="sidebar-brand-sub">Tanger Med · CIRES</div>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map(item => (
            <button
              key={item.key}
              className={`sidebar-nav-item ${tab === item.key ? 'sidebar-nav-item--active' : ''}`}
              onClick={() => { setTab(item.key); setSidebarOpen(false); }}
            >
              <span className="sidebar-nav-icon">{item.icon}</span>
              <span className="sidebar-nav-label">{item.label}</span>
              {counts[item.key] > 0 && (
                <span className="sidebar-nav-badge">{counts[item.key]}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button className="sidebar-footer-btn" onClick={toggleTheme}>
            {theme === 'light' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="5" /><line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" /><line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" /><line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" /><line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" /></svg>
            )}
            <span>{theme === 'light' ? 'Dark mode' : 'Light mode'}</span>
          </button>
          <button className="sidebar-footer-btn" onClick={() => navigate('/')}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            <span>Back to Chat</span>
          </button>
        </div>
      </aside>
      {sidebarOpen && <div className="admin-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* Main */}
      <main className="admin-main">
        <header className="admin-header">
          <button className="admin-hamburger" onClick={() => setSidebarOpen(true)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="21" y2="12" /><line x1="3" y1="18" x2="21" y2="18" /></svg>
          </button>
          <h1 className="admin-title">
            {NAV_ITEMS.find(i => i.key === tab)?.label || 'Dashboard'}
          </h1>
          {tab === 'conversations' && (
            <div className="admin-search">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></svg>
              <input
                type="text"
                placeholder="Search…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          )}
          <span className="admin-refresh-badge">
            Auto-refresh: {REFRESH_INTERVAL / 1000}s
          </span>
        </header>

        <StatsBar stats={stats} loading={loading} />

        {error && <div className="admin-error">{error}</div>}

        <div className="admin-body">
          {tab === 'conversations' && (
            <div className="admin-split">
              <ConversationList
                conversations={filteredConvos}
                selected={selected}
                onSelect={handleSelect}
                loading={loading}
              />
              <ConversationDetail detail={detail} />
            </div>
          )}
          {tab === 'escalations' && (
            <EscalationQueue
              escalations={escalations}
              loading={loading}
              onStatusChange={handleEscalationStatusChange}
            />
          )}
          {tab === 'documents' && (
            <DocumentsList documents={documents} loading={loading} onChange={fetchAll} />
          )}
        </div>
      </main>
    </div>
  );
}

export default AdminPage;
