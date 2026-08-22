import { FormEvent, useEffect, useState } from 'react';
import Button from '../../common/Button/Button';
import TemplateFieldsEditor from '../TemplateFieldsEditor/TemplateFieldsEditor';
import TemplatePreviewFrame from '../TemplatePreviewFrame/TemplatePreviewFrame';
import { ReportTemplate, TemplateSection } from '../../../types';
import './TemplateForm.css';

export interface TemplateFormValues {
  name: string;
  header: { organizationName: string; logoKey: string | null; tagline: string; contactNumber: string };
  doctorInfo: { showDoctorName: boolean; showSignatureLine: boolean; showRegistrationNo: boolean };
  sections: TemplateSection[];
  footer: { text: string; disclaimer: string };
  accentColor: string;
  style: { headerTextColor: string; backgroundColor: string; contentTextColor: string; fontSize: number };
}

interface TemplateFormProps {
  initial?: ReportTemplate;
  // Seeds a brand-new template's starting values from a starter preset (see
  // utils/templatePresets.ts) -- distinct from `initial`, which is an already-saved
  // template being edited.
  initialValues?: TemplateFormValues;
  onSubmit: (values: TemplateFormValues) => Promise<void>;
  submitLabel?: string;
}

export function defaultValues(): TemplateFormValues {
  return {
    name: 'New Template',
    header: { organizationName: '', logoKey: null, tagline: '', contactNumber: '' },
    doctorInfo: { showDoctorName: true, showSignatureLine: true, showRegistrationNo: false },
    // Deliberately excludes "impression"/"recommendations" -- those are dedicated fields
    // on every report version, always rendered as their own block after these sections
    // (see ReportViewer.tsx and the backend's pdf_service.py). Adding them here too would
    // duplicate that block on every report using this template.
    sections: [
      { key: 'clinical_history', title: 'Clinical Indication', order: 1, enabled: true },
      { key: 'technique', title: 'Technique', order: 2, enabled: true },
      {
        key: 'comparison',
        title: 'Comparison',
        order: 3,
        enabled: true,
        guidance: 'State prior imaging reviewed, with study dates and modalities, or note none was available.',
      },
      { key: 'findings', title: 'Findings', order: 4, enabled: true },
    ],
    footer: {
      text: '',
      disclaimer:
        'This report was drafted with AI assistance and has been reviewed and approved by a licensed physician.',
    },
    accentColor: '#0E7C86',
    style: { headerTextColor: '#0E7C86', backgroundColor: '#FFFFFF', contentTextColor: '#101828', fontSize: 10.5 },
  };
}

/** Maps an already-saved template to the editable form shape -- shared by this form's own
 *  "load for editing" effect and by NewStudyForm's inline "customize this template" panel,
 *  so the two surfaces can't drift on how a template's fields get seeded into a draft. */
export function templateToFormValues(template: ReportTemplate): TemplateFormValues {
  return {
    name: template.name,
    header: {
      organizationName: template.header.organizationName || '',
      logoKey: template.header.logoKey ?? null,
      tagline: template.header.tagline || '',
      contactNumber: template.header.contactNumber || '',
    },
    doctorInfo: template.doctorInfo,
    sections: template.sections,
    footer: template.footer,
    accentColor: template.accentColor,
    style: {
      headerTextColor: template.style?.headerTextColor || template.accentColor,
      backgroundColor: template.style?.backgroundColor || '#FFFFFF',
      contentTextColor: template.style?.contentTextColor || '#101828',
      fontSize: template.style?.fontSize || 10.5,
    },
  };
}

export default function TemplateForm({ initial, initialValues, onSubmit, submitLabel = 'Save template' }: TemplateFormProps) {
  const [values, setValues] = useState<TemplateFormValues>(initialValues ?? defaultValues());
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (initial) setValues(templateToFormValues(initial));
  }, [initial]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit(values);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="template-form">
      <div className="template-form__layout">
        <div className="template-form__controls">
          <TemplateFieldsEditor values={values} onChange={setValues} initialLogoUrl={initial?.header.logoUrl} />
          <Button type="submit" isLoading={isSubmitting} size="lg">
            {submitLabel}
          </Button>
        </div>

        <div className="template-form__preview">
          <p className="template-form__preview-label">Live preview</p>
          <TemplatePreviewFrame payload={values} debounceMs={600} height={560} />
        </div>
      </div>
    </form>
  );
}
