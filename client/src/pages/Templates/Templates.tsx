import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FiCheckCircle, FiEdit2, FiPlus, FiStar, FiTrash2 } from 'react-icons/fi';
import { templateApi } from '../../api/template.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useTemplatesList } from '../../hooks/queries/useTemplates';
import { queryKeys } from '../../lib/queryKeys';
import { ReportTemplate } from '../../types';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Modal from '../../components/common/Modal/Modal';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import TemplateForm, { TemplateFormValues } from '../../components/templates/TemplateForm/TemplateForm';
import TemplatePresetGallery from '../../components/templates/TemplatePresetGallery/TemplatePresetGallery';
import { useAuth } from '../../hooks/useAuth';
import './Templates.css';

export default function Templates() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canManage = user?.role === 'org_admin';

  // Shared with NewStudyForm's template picker (same query key) -- customizing a
  // template here and then starting a new study elsewhere never shows a stale list.
  const { data: templates = [], isLoading, isError, error: loadErrorObj, refetch } = useTemplatesList();
  const [modalMode, setModalMode] = useState<'choose-preset' | 'create' | 'edit' | null>(null);
  const [activeTemplate, setActiveTemplate] = useState<ReportTemplate | null>(null);
  const [draftValues, setDraftValues] = useState<TemplateFormValues | undefined>(undefined);
  const [error, setError] = useState('');

  function invalidateTemplates() {
    queryClient.invalidateQueries({ queryKey: queryKeys.templates.all });
  }

  async function handleCreate(values: TemplateFormValues) {
    try {
      await templateApi.create(values);
      setModalMode(null);
      invalidateTemplates();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleUpdate(values: TemplateFormValues) {
    if (!activeTemplate) return;
    try {
      await templateApi.update(activeTemplate.id, values);
      setModalMode(null);
      setActiveTemplate(null);
      invalidateTemplates();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function handleSetDefault(id: string) {
    await templateApi.setDefault(id);
    invalidateTemplates();
  }

  async function handleDelete(id: string) {
    if (!confirm('Delete this template? This cannot be undone.')) return;
    try {
      await templateApi.remove(id);
      invalidateTemplates();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  const loadError = isError ? apiErrorMessage(loadErrorObj) : '';

  return (
    <div className="templates-page">
      <div className="templates-page__header">
        <div>
          <h1>Report templates</h1>
          <p>Configure your organization&apos;s branding, sections, and disclaimer — the AI drafts into this format.</p>
        </div>
        {canManage && (
          <Button icon={<FiPlus size={16} />} onClick={() => setModalMode('choose-preset')}>
            New template
          </Button>
        )}
      </div>

      {(error || loadError) && <div className="templates-page__error">{error || loadError}</div>}

      {isLoading ? (
        <div className="templates-page__loading">
          <Loader size="lg" />
        </div>
      ) : loadError ? (
        <Button variant="outline" onClick={() => refetch()}>
          Try again
        </Button>
      ) : templates.length === 0 ? (
        <EmptyState title="No templates yet" description="Create a template to control how AI-drafted reports look." />
      ) : (
        <div className="templates-page__grid">
          {templates.map((template) => (
            <Card key={template.id} className="template-card">
              <div className="template-card__accent" style={{ background: template.accentColor }} />
              <div className="template-card__body">
                <div className="template-card__top">
                  <h3>{template.name}</h3>
                  {template.isDefault && (
                    <span className="template-card__default-badge">
                      <FiStar size={12} /> Default
                    </span>
                  )}
                </div>
                <p className="template-card__meta">{template.sections.filter((s) => s.enabled).length} sections enabled</p>
                {canManage && (
                  <div className="template-card__actions">
                    <Button
                      size="sm"
                      variant="outline"
                      icon={<FiEdit2 size={13} />}
                      onClick={() => {
                        setActiveTemplate(template);
                        setModalMode('edit');
                      }}
                    >
                      Customize
                    </Button>
                    {!template.isDefault && (
                      <>
                        <Button size="sm" variant="ghost" icon={<FiCheckCircle size={13} />} onClick={() => handleSetDefault(template.id)}>
                          Set default
                        </Button>
                        <Button size="sm" variant="ghost" icon={<FiTrash2 size={13} />} onClick={() => handleDelete(template.id)}>
                          Delete
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={modalMode === 'choose-preset'} onClose={() => setModalMode(null)} title="New report template" size="lg">
        <TemplatePresetGallery
          onSelectPreset={(values) => {
            setDraftValues(values);
            setModalMode('create');
          }}
          onStartBlank={() => {
            setDraftValues(undefined);
            setModalMode('create');
          }}
        />
      </Modal>

      <Modal
        isOpen={modalMode === 'create'}
        onClose={() => {
          setModalMode(null);
          setDraftValues(undefined);
        }}
        title="Create report template"
        size="xl"
      >
        <TemplateForm initialValues={draftValues} onSubmit={handleCreate} submitLabel="Create template" />
      </Modal>

      <Modal
        isOpen={modalMode === 'edit'}
        onClose={() => {
          setModalMode(null);
          setActiveTemplate(null);
        }}
        title={`Customize ${activeTemplate?.name ?? 'template'}`}
        size="xl"
      >
        {activeTemplate && <TemplateForm initial={activeTemplate} onSubmit={handleUpdate} submitLabel="Save changes" />}
      </Modal>
    </div>
  );
}
