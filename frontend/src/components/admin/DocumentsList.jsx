import './DocumentsList.css';

function DocumentsList({ documents, loading }) {
  if (loading) {
    return <div className="docs-loading">Loading corpus…</div>;
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="docs-empty">
        <h3>No documents ingested yet.</h3>
        <p>
          Run <code>python -m backend.documents.ingest</code> from the host to populate the corpus
          from <code>corpus/manifest.json</code>.
        </p>
      </div>
    );
  }

  return (
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
                {d.source_url ? (
                  <a href={d.source_url} target="_blank" rel="noopener noreferrer">link</a>
                ) : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default DocumentsList;
