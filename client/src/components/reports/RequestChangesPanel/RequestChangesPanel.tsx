import { FormEvent, useState } from 'react';
import { FiSend } from 'react-icons/fi';
import Card from '../../common/Card/Card';
import Button from '../../common/Button/Button';
import { TextArea } from '../../common/TextField/TextField';
import './RequestChangesPanel.css';

interface RequestChangesPanelProps {
  onSubmit: (note: string) => Promise<void>;
  disabled?: boolean;
}

export default function RequestChangesPanel({ onSubmit, disabled }: RequestChangesPanelProps) {
  const [note, setNote] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return;
    setIsSubmitting(true);
    try {
      await onSubmit(note.trim());
      setNote('');
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card className="request-changes">
      <h3 className="request-changes__title">Request changes</h3>
      <p className="request-changes__hint">
        Tell the AI what to correct or add. It will re-examine the scan and produce a new version — the
        version you&apos;re looking at now stays in the history above.
      </p>
      <form onSubmit={handleSubmit} className="request-changes__form">
        <TextArea
          placeholder='e.g. "Look again at the lower-left lobe — I think an opacity was missed" or "Shorten the impression to two sentences."'
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={disabled || isSubmitting}
          rows={4}
        />
        <Button type="submit" icon={<FiSend size={15} />} isLoading={isSubmitting} disabled={disabled || !note.trim()}>
          Send to AI for revision
        </Button>
      </form>
    </Card>
  );
}
