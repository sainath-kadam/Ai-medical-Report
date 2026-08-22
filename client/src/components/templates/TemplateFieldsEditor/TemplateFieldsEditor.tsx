import { useEffect, useState } from 'react';
import { FiArrowDown, FiArrowUp, FiImage, FiPlus, FiTrash2 } from 'react-icons/fi';
import Card from '../../common/Card/Card';
import Button from '../../common/Button/Button';
import Loader from '../../common/Loader/Loader';
import { TextField, TextArea } from '../../common/TextField/TextField';
import Select from '../../ui/Select/Select';
import { templateApi } from '../../../api/template.api';
import { apiErrorMessage } from '../../../api/axiosInstance';
import { TemplateSection } from '../../../types';
import { TemplateFormValues } from '../TemplateForm/TemplateForm';
import './TemplateFieldsEditor.css';

interface TemplateFieldsEditorProps {
  values: TemplateFormValues;
  onChange: (updater: (prev: TemplateFormValues) => TemplateFormValues) => void;
  // A logo already attached to `values.header.logoKey` when the editor first mounts (e.g.
  // editing an existing template) has no URL of its own in TemplateFormValues -- only the
  // storage key -- so the caller passes the signed URL to show as a thumbnail separately.
  initialLogoUrl?: string;
}

const FONT_SIZE_OPTIONS = [
  { value: '9', label: 'Small' },
  { value: '10.5', label: 'Medium' },
  { value: '12', label: 'Large' },
  { value: '14', label: 'Extra large' },
];

/** Every field for customizing a template's look and content -- logo, header/contact,
 *  colors, font size, doctor/signature toggles, sections, footer -- shared by the full
 *  Templates-page editor (TemplateForm, which pairs this with its own live preview) and
 *  NewStudyForm's inline "customize this template" panel (which reuses the surrounding
 *  page's own preview instead of embedding a second one here). */
export default function TemplateFieldsEditor({ values, onChange, initialLogoUrl }: TemplateFieldsEditorProps) {
  const [logoPreviewUrl, setLogoPreviewUrl] = useState<string | undefined>(initialLogoUrl);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const [logoError, setLogoError] = useState('');

  useEffect(() => setLogoPreviewUrl(initialLogoUrl), [initialLogoUrl]);

  async function handleLogoSelect(file: File | null) {
    if (!file) {
      onChange((p) => ({ ...p, header: { ...p.header, logoKey: null } }));
      setLogoPreviewUrl(undefined);
      return;
    }
    setLogoError('');
    setIsUploadingLogo(true);
    try {
      const result = await templateApi.uploadLogo(file);
      onChange((p) => ({ ...p, header: { ...p.header, logoKey: result.logoKey } }));
      setLogoPreviewUrl(result.logoUrl);
    } catch (err) {
      setLogoError(apiErrorMessage(err));
    } finally {
      setIsUploadingLogo(false);
    }
  }

  function updateSection(index: number, patch: Partial<TemplateSection>) {
    onChange((prev) => ({
      ...prev,
      sections: prev.sections.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    }));
  }

  function moveSection(index: number, direction: -1 | 1) {
    onChange((prev) => {
      const sections = [...prev.sections];
      const target = index + direction;
      if (target < 0 || target >= sections.length) return prev;
      [sections[index], sections[target]] = [sections[target], sections[index]];
      return { ...prev, sections: sections.map((s, i) => ({ ...s, order: i + 1 })) };
    });
  }

  function addSection() {
    onChange((prev) => ({
      ...prev,
      sections: [
        ...prev.sections,
        { key: `custom_${Date.now()}`, title: 'New Section', order: prev.sections.length + 1, enabled: true },
      ],
    }));
  }

  function removeSection(index: number) {
    onChange((prev) => ({ ...prev, sections: prev.sections.filter((_, i) => i !== index) }));
  }

  return (
    <div className="template-fields-editor">
      <Card className="template-form__card">
        <h3 className="template-form__heading">Basics</h3>
        <div className="template-form__grid">
          <TextField
            label="Template name"
            value={values.name}
            onChange={(e) => onChange((p) => ({ ...p, name: e.target.value }))}
            required
          />
          <TextField
            label="Accent color"
            type="color"
            value={values.accentColor}
            onChange={(e) => onChange((p) => ({ ...p, accentColor: e.target.value }))}
          />
        </div>
        <div className="template-form__grid">
          <TextField
            label="Organization name (shown on report header)"
            value={values.header.organizationName}
            onChange={(e) => onChange((p) => ({ ...p, header: { ...p.header, organizationName: e.target.value } }))}
            required
          />
          <TextField
            label="Tagline (optional)"
            value={values.header.tagline}
            onChange={(e) => onChange((p) => ({ ...p, header: { ...p.header, tagline: e.target.value } }))}
          />
        </div>
        <div className="template-form__grid">
          <TextField
            label="Contact number (optional)"
            value={values.header.contactNumber}
            onChange={(e) => onChange((p) => ({ ...p, header: { ...p.header, contactNumber: e.target.value } }))}
          />
          <div>
            <label className="template-form__field-label">Logo (optional)</label>
            {logoPreviewUrl ? (
              <div className="template-form__logo-preview">
                <img src={logoPreviewUrl} alt="Logo preview" />
                <Button type="button" variant="ghost" size="sm" onClick={() => handleLogoSelect(null)}>
                  Remove
                </Button>
              </div>
            ) : (
              <label className="template-form__logo-upload">
                <input type="file" accept="image/*" hidden onChange={(e) => handleLogoSelect(e.target.files?.[0] ?? null)} />
                {isUploadingLogo ? (
                  <Loader size="sm" />
                ) : (
                  <>
                    <FiImage size={18} />
                    <span>Upload logo</span>
                  </>
                )}
              </label>
            )}
            {logoError && <p className="template-form__error">{logoError}</p>}
          </div>
        </div>
      </Card>

      <Card className="template-form__card">
        <h3 className="template-form__heading">Appearance</h3>
        <p className="template-form__hint">Colors and type size used for the report body and header.</p>
        <div className="template-form__grid">
          <TextField
            label="Header text color"
            type="color"
            value={values.style.headerTextColor}
            onChange={(e) => onChange((p) => ({ ...p, style: { ...p.style, headerTextColor: e.target.value } }))}
          />
          <TextField
            label="Background color"
            type="color"
            value={values.style.backgroundColor}
            onChange={(e) => onChange((p) => ({ ...p, style: { ...p.style, backgroundColor: e.target.value } }))}
          />
        </div>
        <div className="template-form__grid">
          <TextField
            label="Body text color"
            type="color"
            value={values.style.contentTextColor}
            onChange={(e) => onChange((p) => ({ ...p, style: { ...p.style, contentTextColor: e.target.value } }))}
          />
          <Select
            label="Font size"
            value={String(values.style.fontSize)}
            onChange={(e) => onChange((p) => ({ ...p, style: { ...p.style, fontSize: Number(e.target.value) } }))}
            options={FONT_SIZE_OPTIONS}
          />
        </div>
      </Card>

      <Card className="template-form__card">
        <h3 className="template-form__heading">Doctor &amp; signature block</h3>
        <div className="template-form__checkboxes">
          <label>
            <input
              type="checkbox"
              checked={values.doctorInfo.showDoctorName}
              onChange={(e) => onChange((p) => ({ ...p, doctorInfo: { ...p.doctorInfo, showDoctorName: e.target.checked } }))}
            />
            Show reviewing doctor&apos;s name
          </label>
          <label>
            <input
              type="checkbox"
              checked={values.doctorInfo.showSignatureLine}
              onChange={(e) => onChange((p) => ({ ...p, doctorInfo: { ...p.doctorInfo, showSignatureLine: e.target.checked } }))}
            />
            Include signature line
          </label>
          <label>
            <input
              type="checkbox"
              checked={values.doctorInfo.showRegistrationNo}
              onChange={(e) => onChange((p) => ({ ...p, doctorInfo: { ...p.doctorInfo, showRegistrationNo: e.target.checked } }))}
            />
            Show medical registration number
          </label>
        </div>
      </Card>

      <Card className="template-form__card">
        <div className="template-form__section-header">
          <h3 className="template-form__heading">Report sections</h3>
          <Button type="button" variant="outline" size="sm" icon={<FiPlus size={14} />} onClick={addSection}>
            Add section
          </Button>
        </div>
        <p className="template-form__hint">
          This is exactly what the AI is instructed to fill in, and the order reports are rendered in.
        </p>
        <div className="template-form__sections">
          {values.sections.map((section, index) => (
            <div key={section.key} className="template-form__section-row">
              <div className="template-form__section-controls">
                <button type="button" onClick={() => moveSection(index, -1)} disabled={index === 0} aria-label="Move up">
                  <FiArrowUp size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => moveSection(index, 1)}
                  disabled={index === values.sections.length - 1}
                  aria-label="Move down"
                >
                  <FiArrowDown size={14} />
                </button>
              </div>
              <label className="template-form__section-enabled">
                <input type="checkbox" checked={section.enabled} onChange={(e) => updateSection(index, { enabled: e.target.checked })} />
              </label>
              <TextField
                value={section.title}
                onChange={(e) => updateSection(index, { title: e.target.value })}
                placeholder="Section title"
              />
              <TextField
                value={section.guidance ?? ''}
                onChange={(e) => updateSection(index, { guidance: e.target.value })}
                placeholder="Guidance for the AI (optional)"
              />
              <button type="button" className="template-form__remove" onClick={() => removeSection(index)} aria-label="Remove section">
                <FiTrash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="template-form__card">
        <h3 className="template-form__heading">Footer &amp; disclaimer</h3>
        <TextArea
          label="Footer text (optional)"
          value={values.footer.text}
          onChange={(e) => onChange((p) => ({ ...p, footer: { ...p.footer, text: e.target.value } }))}
          rows={2}
        />
        <TextArea
          label="Disclaimer"
          value={values.footer.disclaimer}
          onChange={(e) => onChange((p) => ({ ...p, footer: { ...p.footer, disclaimer: e.target.value } }))}
          rows={3}
        />
      </Card>
    </div>
  );
}
