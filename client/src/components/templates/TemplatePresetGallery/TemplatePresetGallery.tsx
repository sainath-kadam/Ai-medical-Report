import { useState } from 'react';
import { FiEdit3 } from 'react-icons/fi';
import Loader from '../../common/Loader/Loader';
import { templateApi } from '../../../api/template.api';
import { generatePlaceholderLogo } from '../../../utils/generatePlaceholderLogo';
import { TEMPLATE_PRESETS, TemplatePreset } from '../../../utils/templatePresets';
import { TemplateFormValues } from '../TemplateForm/TemplateForm';
import './TemplatePresetGallery.css';

interface TemplatePresetGalleryProps {
  onSelectPreset: (values: TemplateFormValues) => void;
  onStartBlank: () => void;
}

/** Shown before the template editor opens for a brand-new template -- pick a ready-made
 *  starting point, or build one from scratch. Every field on a preset stays fully editable
 *  afterward in TemplateForm; this only decides what the form's initial values are.
 *
 *  Picking a preset also generates and uploads its placeholder logo on the spot (a small
 *  generic mark, not any real organization's actual logo) so the editor's live preview
 *  shows a logo immediately -- a shared logo can't be baked into the preset itself since
 *  every logo key is scoped to the org that uploads it. */
export default function TemplatePresetGallery({ onSelectPreset, onStartBlank }: TemplatePresetGalleryProps) {
  const [loadingPresetId, setLoadingPresetId] = useState<string | null>(null);

  async function handleSelect(preset: TemplatePreset) {
    setLoadingPresetId(preset.id);
    try {
      const file = await generatePlaceholderLogo(preset.logoKind, preset.values.accentColor);
      const { logoKey } = await templateApi.uploadLogo(file);
      onSelectPreset({ ...preset.values, header: { ...preset.values.header, logoKey } });
    } catch {
      // The placeholder logo is a nice-to-have -- if generation or upload fails for any
      // reason, still let the user start from this preset's colors and sections.
      onSelectPreset(preset.values);
    } finally {
      setLoadingPresetId(null);
    }
  }

  return (
    <div className="template-preset-gallery">
      {TEMPLATE_PRESETS.map((preset) => (
        <button
          key={preset.id}
          type="button"
          className="template-preset-gallery__card"
          disabled={loadingPresetId !== null}
          onClick={() => handleSelect(preset)}
        >
          {loadingPresetId === preset.id ? (
            <Loader size="sm" />
          ) : (
            <span className="template-preset-gallery__swatch" style={{ background: preset.values.accentColor }} />
          )}
          <span className="template-preset-gallery__name">{preset.name}</span>
          <span className="template-preset-gallery__description">{preset.description}</span>
        </button>
      ))}
      <button
        type="button"
        className="template-preset-gallery__card template-preset-gallery__card--blank"
        disabled={loadingPresetId !== null}
        onClick={onStartBlank}
      >
        <FiEdit3 size={20} />
        <span className="template-preset-gallery__name">Start from blank</span>
        <span className="template-preset-gallery__description">Build every section and color yourself.</span>
      </button>
    </div>
  );
}
