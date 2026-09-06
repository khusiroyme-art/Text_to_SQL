import { useRef, useState } from "react";
import { uploadDatabase } from "../api.js";

// The picker and the uploader belong together: uploading a database is only
// useful because it becomes selectable, and after a successful upload the new
// database is selected automatically - nobody uploads a file in order to keep
// looking at the previous one.
export default function DatabasePicker({ databases, dbId, onSelect, onUploaded, disabled }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function onFile(event) {
    const file = event.target.files?.[0];
    // Reset immediately so picking the same file twice still fires a change.
    event.target.value = "";
    if (!file) return;

    setBusy(true);
    setError(null);
    const response = await uploadDatabase(file);
    setBusy(false);

    if (response.error) {
      setError(response.error);
      return;
    }
    onUploaded(response.db_id);
  }

  return (
    <div className="db-picker">
      <label>
        Database
        <select
          value={dbId}
          disabled={disabled || busy}
          onChange={(e) => onSelect(e.target.value)}
        >
          {databases.map((db) => (
            <option key={db.db_id} value={db.db_id}>
              {db.label}
              {db.uploaded ? " (uploaded)" : ""}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className="chip"
        disabled={disabled || busy}
        onClick={() => inputRef.current?.click()}
      >
        {busy ? "Uploading..." : "Upload .sqlite"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".sqlite,.sqlite3,.db"
        hidden
        onChange={onFile}
      />

      {error && <span className="picker-error">{error}</span>}
    </div>
  );
}
