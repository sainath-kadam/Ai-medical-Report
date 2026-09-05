import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiArrowLeft, FiGlobe } from 'react-icons/fi';
import { platformApi, CreateOrganizationResult } from '../../api/platform.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import { TextField } from '../../components/common/TextField/TextField';
import TempPasswordBanner from '../../components/common/TempPasswordBanner/TempPasswordBanner';
import './CreateOrganization.css';

const EMPTY_FORM = { organizationName: '', adminName: '', adminEmail: '' };

/** system_admin-only (CONTRACTS.md §2a) — the one page that creates a brand-new
 * organization, along with its first org_admin, rather than working inside one. */
export default function CreateOrganization() {
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [created, setCreated] = useState<CreateOrganizationResult | null>(null);

  function update<K extends keyof typeof EMPTY_FORM>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      const result = await platformApi.createOrganization(form);
      setCreated(result);
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="create-org-page">
      <Link to="/platform/organizations" className="create-org-page__back">
        <FiArrowLeft size={14} /> All organizations
      </Link>
      <div className="create-org-page__header">
        <h1>Create organization</h1>
        <p>Onboard a new clinic or imaging center, and its first org admin, onto the platform.</p>
      </div>

      {created && (
        <Card className="create-org-page__result">
          <p className="create-org-page__result-summary">
            <strong>{created.organization.name}</strong> has been created, with{' '}
            <strong>{created.adminUser.name}</strong> ({created.adminUser.email}) as its first org admin.
          </p>
          <TempPasswordBanner password={created.temporaryPassword} recipientName={created.adminUser.name} />
          <Button variant="outline" onClick={() => setCreated(null)}>
            Create another organization
          </Button>
        </Card>
      )}

      <Card className="create-org-page__card">
        <form onSubmit={handleSubmit} className="create-org-page__form">
          <TextField
            label="Organization name"
            placeholder="e.g. Riverside Imaging Center"
            value={form.organizationName}
            onChange={(e) => update('organizationName', e.target.value)}
            required
          />
          <TextField
            label="First admin's name"
            placeholder="e.g. Dr. Ava Chen"
            value={form.adminName}
            onChange={(e) => update('adminName', e.target.value)}
            required
          />
          <TextField
            label="First admin's email"
            type="email"
            placeholder="ava@riverside-imaging.example"
            value={form.adminEmail}
            onChange={(e) => update('adminEmail', e.target.value)}
            required
          />

          {error && <p className="create-org-page__error">{error}</p>}

          <Button type="submit" size="lg" icon={<FiGlobe size={16} />} isLoading={isSubmitting} fullWidth>
            Create organization
          </Button>
        </form>
      </Card>
    </div>
  );
}
