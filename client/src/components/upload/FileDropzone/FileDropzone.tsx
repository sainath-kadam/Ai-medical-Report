import { DragEvent, useEffect, useRef, useState } from 'react';
import { FiUploadCloud, FiFile, FiX } from 'react-icons/fi';
import './FileDropzone.css';

interface FileDropzoneProps {
  file: File | null;
  onSelect: (file: File | null) => void;
  accept?: string;
  disabled?: boolean;
}

export default function FileDropzone({ file, onSelect, accept = 'image/*,.dcm,video/*', disabled = false }: FileDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Object URLs are created once per `file` (not on every render, e.g. every
  // isDragging toggle) and revoked on cleanup so we don't leak a blob URL each time.
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file || !file.type.startsWith('image/')) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) onSelect(dropped);
  }

  return (
    <div
      className={`dropzone ${isDragging ? 'dropzone--dragging' : ''} ${file ? 'dropzone--filled' : ''} ${disabled ? 'dropzone--disabled' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setIsDragging(true);
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      onClick={() => !disabled && !file && inputRef.current?.click()}
      role="button"
      tabIndex={disabled ? -1 : 0}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        disabled={disabled}
        onChange={(e) => onSelect(e.target.files?.[0] ?? null)}
      />

      {!file && (
        <>
          <FiUploadCloud size={36} className="dropzone__icon" />
          <p className="dropzone__title">Drag & drop a scan here, or click to browse</p>
          <p className="dropzone__hint">JPEG, PNG, WEBP, DICOM, or video · up to 1GB</p>
        </>
      )}

      {file && (
        <div className="dropzone__preview" onClick={(e) => e.stopPropagation()}>
          {previewUrl ? (
            <img src={previewUrl} alt="Scan preview" className="dropzone__preview-image" />
          ) : (
            <div className="dropzone__file-icon">
              <FiFile size={28} />
            </div>
          )}
          <div className="dropzone__file-meta">
            <strong>{file.name}</strong>
            <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
          </div>
          <button
            type="button"
            className="dropzone__remove"
            onClick={() => onSelect(null)}
            disabled={disabled}
            aria-label="Remove selected file"
          >
            <FiX size={18} />
          </button>
        </div>
      )}
    </div>
  );
}
