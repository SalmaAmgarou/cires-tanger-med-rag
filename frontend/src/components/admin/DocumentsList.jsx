import { useRef, useState } from 'react';
import { uploadDocument, deleteDocument } from '../../api/client';
import './DocumentsList.css';

function UploadForm({ onUploaded }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState('');
  const [organization, setOrganization] = useState('user_uploaded');
  const [documentType, setDocumentType] = useState('uploaded');
  const [language, setLanguage] = useState('');
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState(null);

  const reset = () => {
    setFile(null);
    setTitle('');
    setStatus(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file || uploading) return;
    setUploading(true);
    setStatus({ kind: 'pending', msg: `Uploading & indexing ${file.name}…` });
    try {
      const data = await uploadDocument({
        file,
        title,
        documentType,
        organization,
        language: language || undefined,
      });
      setStatus({
        kind: 'success',
        msg: `Indexed "${data.title}" — ${data.chunk_count} chunks across ${data.total_pages || '?'} pages in ${(data.duration_ms / 1000).toFixed(1)}s.`,
      });
      reset();
      onUploaded?.();
    } catch (err) {
      setStatus({ kind: 'error', msg: err.message || 'Upload failed' });
    } finally {
      setUploading(false);
    }
  };

  return (
    <form className="docs-upload" onSubmit={handleSubmit}>
      <div className="docs-upload-row">
        <label className="docs-upload-file">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            onChange={e => setFile(e.target.files?.[0] || null)}
            disabled={uploading}
          />
          <span>{file ? file.name : 'Choose PDF…'}</span>
        </label>
        <input
          className="docs-upload-input"
          type="text"
          placeholder="Title (optional)"
          value={title}
          onChange={e => setTitle(e.target.value)}
          disabled={uploading}
        />
        <input
          className="docs-upload-input"
          type="text"
          placeholder="Organization"
          value={organization}
          onChange={e => setOrganization(e.target.value)}
          disabled={uploading}
        />
        <input
          className="docs-upload-input"
          type="text"
          placeholder="Type"
          value={documentType}
          onChange={e => setDocumentType(e.target.value)}
          disabled={uploading}
        />
        <select
          className="docs-upload-input"
          value={language}
          onChange={e => setLanguage(e.target.value)}
          disabled={uploading}
        >
          <option value="">Auto-detect</option>
          <option value="fr">FR</option>
          <option value="en">EN</option>
        </select>
        <button
          className="docs-upload-btn"
          type="submit"
          disabled={!file || uploading}
        >
          {uploading ? 'Indexing…' : 'Upload & Index'}
        </button>
      </div>
      {status && (
        <div className={`docs-upload-status docs-upload-status--${status.kind}`}>
          {status.msg}
        </div>
      )}
    </form>
  );
}

function DocumentsList({ documents, loading, onChange }) {
  const [pendingDelete, setPendingDelete] = useState(null);
  const [error, setError] = useState(null);

  const handleDelete = async (docId) => {
    setPendingDelete(docId);
    setError(null);
    try {
      await deleteDocument(docId);
      onChange?.();
    } catch (err) {
      setError(err.message || 'Delete failed');
    } finally {
      setPendingDelete(null);
    }
  };

  return (
    <div className="docs-wrapper">
      <UploadForm onUploaded={onChange} />

      {loading && !documents?.length ? (
        <div className="docs-loading">Loading corpus…</div>
      ) : !documents || documents.length === 0 ? (
        <div className="docs-empty">
          <h3>No documents indexed yet.</h3>
          <p>
            Upload a PDF above, or run <code>docker compose --profile cli run --rm ingest</code> to
            populate the corpus from <code>corpus/manifest.json</code>.
          </p>
        </div>
      ) : (
        <div className="docs-list">
          <div className="docs-header">
            <span>{documents.length} document{documents.length === 1 ? '' : 's'} indexed</span>
          </div>
          <table className="docs-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Org</th>
                <th>Lang</th>
                <th>Pages</th>
                <th>Chunks</th>
                <th>Date</th>
                <th>Source</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {documents.map(d => (
                <tr key={d.id}>
                  <td className="docs-title">{d.title || '—'}</td>
                  <td><span className="docs-tag">{d.document_type || '—'}</span></td>
                  <td>{d.organization || '—'}</td>
                  <td>{(d.language || '—').toUpperCase()}</td>
                  <td>{d.total_pages ?? '—'}</td>
                  <td>{d.chunk_count}</td>
                  <td>{d.publish_date || '—'}</td>
                  <td>
                    {d.source_url && !d.source_url.startsWith('upload://') ? (
                      <a href={d.source_url} target="_blank" rel="noopener noreferrer">link</a>
                    ) : d.source_url?.startsWith('upload://') ? 'uploaded' : '—'}
                  </td>
                  <td>
                    <button
                      className="docs-delete"
                      onClick={() => handleDelete(d.id)}
                      disabled={pendingDelete === d.id}
                      title="Delete document"
                    >
                      {pendingDelete === d.id ? '…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <div className="docs-upload-status docs-upload-status--error">{error}</div>}
    </div>
  );
}

export default DocumentsList;
