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

/** The "tell the AI what to change" side of editing a report (the other side being the
 *  direct Edit button on the report itself). The instruction is sent to the AI, which
 *  re-examines the scan where needed, rewrites the affected parts, and the new version
 *  appears in the report preview — the previous version stays in the version history. */
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
      <h3 className="request-changes__title">Ask AI to revise</h3>
      <p className="request-changes__hint">
        Describe what to correct, add, or rephrase. The AI will re-examine the scan where needed and write the
        revision straight into the report preview as a new version.
      </p>
      <form onSubmit={handleSubmit} className="request-changes__form">
        <TextArea
          label="Instruction for the AI"
          placeholder={
            'e.g. "Re-check the lower left lobe — I think an opacity was missed."\n' +
            'e.g. "Rewrite the impression in two sentences."\n' +
            'e.g. "Add a comparison with the prior study."'
          }
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={disabled || isSubmitting}
          rows={5}
        />
        <Button type="submit" icon={<FiSend size={15} />} isLoading={isSubmitting} disabled={disabled || !note.trim()} fullWidth>
          Revise with AI
        </Button>
      </form>
    </Card>
  );
}
