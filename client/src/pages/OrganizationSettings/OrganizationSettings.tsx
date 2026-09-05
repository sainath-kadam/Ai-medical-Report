import { FormEvent, useEffect, useState } from 'react';
import { FiCpu, FiSave } from 'react-icons/fi';
import { organizationApi } from '../../api/organization.api';
import { Organization } from '../../types';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import { TextField } from '../../components/common/TextField/TextField';
import Loader from '../../components/common/Loader/Loader';
import { apiErrorMessage } from '../../api/axiosInstance';
import './OrganizationSettings.css';

// Team management now lives on its own page (see pages/Users) — this page is scoped to
// the organization's own profile/branding/AI-mode settings only (spec §29), reached only
// by org_admin (gated at the route level by RoleRoute in routes/AppRoutes.tsx).
export default function OrganizationSettings() {
  const [org, setOrg] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    organizationApi
      .getMine()
      .then((data) => setOrg(data.organization))
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    if (!org) return;
    setIsSaving(true);
    setError('');
    setMessage('');
    try {
      const updated = await organizationApi.update({
        name: org.name,
        address: org.address,
        contactEmail: org.contactEmail,
        contactPhone: org.contactPhone,
        website: org.website,
        logoUrl: org.logoUrl,
        primaryColor: org.primaryColor,
        reportHeader: org.reportHeader,
        reportFooter: org.reportFooter,
        highAccuracyMode: org.highAccuracyMode,
      });
      setOrg(updated);
      setMessage('Organization settings saved');
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading || !org) {
    return (
      <div className="org-settings__loading">
        <Loader size="lg" />
      </div>
    );
  }

  return (
    <div className="org-settings">
      <div className="org-settings__header">
        <h1>Organization settings</h1>
        <p>Manage your organization&apos;s profile, branding, and AI report-generation mode.</p>
      </div>

      {message && <div className="org-settings__success">{message}</div>}
      {error && <div className="org-settings__error">{error}</div>}

      <form onSubmit={handleSave}>
        <Card className="org-settings__card">
          <h3>Profile</h3>
          <div className="org-settings__grid">
            <TextField label="Organization name" value={org.name} onChange={(e) => setOrg({ ...org, name: e.target.value })} />
            <TextField
              label="Contact email"
              value={org.contactEmail ?? ''}
              onChange={(e) => setOrg({ ...org, contactEmail: e.target.value })}
            />
            <TextField
              label="Contact phone"
              value={org.contactPhone ?? ''}
              onChange={(e) => setOrg({ ...org, contactPhone: e.target.value })}
            />
            <TextField label="Website" value={org.website ?? ''} onChange={(e) => setOrg({ ...org, website: e.target.value })} />
            <TextField label="Address" value={org.address ?? ''} onChange={(e) => setOrg({ ...org, address: e.target.value })} />
          </div>
        </Card>

        <Card className="org-settings__card">
          <h3>Report branding</h3>
          <p className="org-settings__hint">Shown on every AI-drafted and finalized PDF report your organization generates.</p>
          <div className="org-settings__grid">
            <TextField label="Logo URL" value={org.logoUrl ?? ''} onChange={(e) => setOrg({ ...org, logoUrl: e.target.value })} />
            <TextField
              label="Accent color"
              type="color"
              value={org.primaryColor ?? '#0E7C86'}
              onChange={(e) => setOrg({ ...org, primaryColor: e.target.value })}
            />
          </div>
          <TextField
            label="Report header text"
            value={org.reportHeader ?? ''}
            onChange={(e) => setOrg({ ...org, reportHeader: e.target.value })}
          />
          <TextField
            label="Report footer text"
            value={org.reportFooter ?? ''}
            onChange={(e) => setOrg({ ...org, reportFooter: e.target.value })}
          />
        </Card>

        <Card className="org-settings__card">
          <h3>
            <FiCpu size={16} /> AI report generation
          </h3>
          <p className="org-settings__hint">
            Standard mode balances cost and turnaround time for most studies. Enable High-Accuracy Mode to
            escalate image interpretation and the clinical summary of every AI-assisted analysis to a
            higher-capability model (Gemini Pro or Claude Opus, depending on the configured provider) for
            organizations handling more complex or high-stakes imaging. Gemini Pro requires a paid Gemini
            plan; on a free key, analyses fall back to the standard model.
          </p>
          <label className="org-settings__toggle">
            <input
              type="checkbox"
              checked={org.highAccuracyMode}
              onChange={(e) => setOrg({ ...org, highAccuracyMode: e.target.checked })}
            />
            Enable High-Accuracy Mode for all future studies
          </label>
          <p className="org-settings__disclaimer">
            Every AI-drafted report — on any tier — is a preliminary draft only. A licensed physician must
            review and approve it before it is considered final.
          </p>
        </Card>

        <Button type="submit" icon={<FiSave size={16} />} isLoading={isSaving}>
          Save changes
        </Button>
      </form>
    </div>
  );
}
