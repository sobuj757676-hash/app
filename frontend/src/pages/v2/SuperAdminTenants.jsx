import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, X, Smartphone, Ban, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../lib/auth';
import { v2, v2Error, TIER_MODULE_COUNTS, TOTAL_MODULES } from '../../lib/v2api';
import '../../v2.css';

const EMPTY_TENANT = {
  company_name: '', uen_number: '', bca_grade: '', subscription_tier: 'STARTER',
  max_projects: 2, max_users: 30, office_address: '', contact_phone: '',
  admin_full_name: '', admin_phone: '', admin_temp_password: '',
};
const EMPTY_APK = {
  version_code: '', version_name: '', min_required_version_code: '',
  apk_download_url: '', sha256_checksum: '', release_notes_en: '',
};

function statusPill(status) {
  if (status === 'ACTIVE') return 'vc2-pill vc2-pill-green';
  if (status === 'SUSPENDED') return 'vc2-pill vc2-pill-red';
  return 'vc2-pill vc2-pill-amber';
}

export default function SuperAdminTenants() {
  const { user } = useAuth();
  const allowed = ['super_admin', 'admin'].includes(user?.role);
  const [tenants, setTenants] = useState([]);
  const [release, setRelease] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState(false);
  const [form, setForm] = useState(EMPTY_TENANT);
  const [submitting, setSubmitting] = useState(false);
  const [apk, setApk] = useState(EMPTY_APK);
  const [apkSubmitting, setApkSubmitting] = useState(false);
  const [busyId, setBusyId] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try { setTenants(await v2.listTenants()); }
    catch (e) { toast.error(v2Error(e).message); }
    try { setRelease(await v2.getAppRelease()); } catch { setRelease(null); }
    setLoading(false);
  }, []);

  useEffect(() => { if (allowed) load(); }, [allowed, load]);

  if (!allowed) {
    return (
      <div className="vc2-page">
        <h1 className="vc2-title">Super Admin — Tenants</h1>
        <p className="vc2-subtitle">This area is restricted to platform administrators. Your role ({user?.role || 'unknown'}) does not have access.</p>
      </div>
    );
  }

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setApkField = (k, v) => setApk(f => ({ ...f, [k]: v }));

  const submitTenant = async e => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const res = await v2.createTenant({
        ...form,
        max_projects: Number(form.max_projects) || 0,
        max_users: Number(form.max_users) || 0,
      });
      toast.success(`Tenant provisioned — admin account created (${res.status}).`);
      setDrawer(false);
      setForm(EMPTY_TENANT);
      await load();
    } catch (err) { toast.error(v2Error(err).message); }
    setSubmitting(false);
  };

  const toggleStatus = async t => {
    const next = t.status === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE';
    setBusyId(t.id);
    try {
      await v2.patchTenant(t.id, { status: next });
      toast.success(next === 'ACTIVE' ? `${t.company_name} reactivated.` : `${t.company_name} suspended.`);
      await load();
    } catch (err) { toast.error(v2Error(err).message); }
    setBusyId('');
  };

  const submitApk = async e => {
    e.preventDefault();
    setApkSubmitting(true);
    try {
      await v2.publishApkRelease({
        ...apk,
        version_code: Number(apk.version_code) || 0,
        min_required_version_code: Number(apk.min_required_version_code) || 0,
      });
      toast.success(`APK release v${apk.version_name} published — mobile apps will prompt to update.`);
      setApk(EMPTY_APK);
      try { setRelease(await v2.getAppRelease()); } catch { setRelease(null); }
    } catch (err) { toast.error(v2Error(err).message); }
    setApkSubmitting(false);
  };

  const activeCount = tenants.filter(t => t.status === 'ACTIVE').length;
  const totalProjects = tenants.reduce((n, t) => n + (t.project_count || 0), 0);

  return (
    <div className="vc2-page">
      <div className="vc2-header">
        <div className="vc2-header-main">
          <h1 className="vc2-title">Super Admin — Tenants</h1>
          <p className="vc2-subtitle">1-click tenant provisioning, feature-flag tiers and the global APK release channel. Every tenant is isolated by company_id.</p>
        </div>
        <div className="vc2-header-links">
          <Link className="vc2-btn vc2-btn-ghost" to="/projects/new">+ New Project (v2)</Link>
          <button className="vc2-btn" onClick={() => setDrawer(true)}><Plus size={16} /> Provision New Tenant</button>
        </div>
      </div>

      <div className="vc2-kpi-row">
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Total Tenants</div><div className="vc2-kpi-value">{tenants.length}</div></div>
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Active Tenants</div><div className="vc2-kpi-value">{activeCount}</div></div>
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Total Projects</div><div className="vc2-kpi-value">{totalProjects}</div></div>
        <div className="vc2-kpi-card">
          <div className="vc2-kpi-label">Latest APK</div>
          <div className="vc2-kpi-value" style={{ fontSize: 20 }}>{release ? `v${release.version_name}` : '—'}</div>
          <div className="vc2-kpi-sub">{release ? `code ${release.version_code} · min ${release.min_required_version_code}` : 'No release published yet'}</div>
        </div>
      </div>

      {loading ? <div className="vc2-loading">Loading tenants…</div> : (
        <div className="vc2-table-wrap" style={{ marginBottom: 18 }}>
          <table className="vc2-table">
            <thead><tr><th>Company</th><th>UEN / BCA</th><th>Tier</th><th>Modules</th><th>Projects</th><th>Users</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>
              {tenants.map(t => (
                <tr key={t.id}>
                  <td><strong>{t.company_name}</strong></td>
                  <td><span className="vc2-mono">{t.uen_number || '—'}</span><br /><span className="vc2-hint">{t.bca_grade || ''}</span></td>
                  <td><span className="vc2-pill vc2-pill-blue">{t.subscription_tier}</span></td>
                  <td><span className="vc2-mono">{(t.enabled_modules || []).length}/{TOTAL_MODULES}</span></td>
                  <td><span className="vc2-mono">{t.project_count || 0} / {t.max_projects}</span></td>
                  <td><span className="vc2-mono">{t.user_count || 0} / {t.max_users}</span></td>
                  <td><span className={statusPill(t.status)}>{t.status}</span></td>
                  <td>
                    {t.status === 'ACTIVE'
                      ? <button className="vc2-btn vc2-btn-danger-outline vc2-btn-small" disabled={busyId === t.id} onClick={() => toggleStatus(t)}><Ban size={13} /> Suspend</button>
                      : <button className="vc2-btn vc2-btn-secondary vc2-btn-small" disabled={busyId === t.id} onClick={() => toggleStatus(t)}><CheckCircle2 size={13} /> Reactivate</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!tenants.length && <div className="vc2-empty">No tenants yet — provision the first company to get started.</div>}
        </div>
      )}

      <div className="vc2-card">
        <h2 className="vc2-card-title"><Smartphone size={16} style={{ verticalAlign: -2 }} /> APK Release Publisher</h2>
        <p className="vc2-card-sub">
          Current live release:{' '}
          {release
            ? <span className="vc2-mono">v{release.version_name} (code {release.version_code}, min required {release.min_required_version_code}){release.apk_download_url ? <> · <a href={release.apk_download_url} target="_blank" rel="noreferrer" style={{ color: '#38BDF8' }}>download</a></> : ''}</span>
            : 'none published yet (apps use built-in fallback values).'}
          {release?.release_notes_en ? <><br />{release.release_notes_en}</> : null}
        </p>
        <form onSubmit={submitApk}>
          <div className="vc2-form-grid">
            <label className="vc2-field"><span className="vc2-label">Version code *</span><input className="vc2-input vc2-mono" required type="number" min="1" value={apk.version_code} onChange={e => setApkField('version_code', e.target.value)} placeholder="204" /></label>
            <label className="vc2-field"><span className="vc2-label">Version name *</span><input className="vc2-input vc2-mono" required value={apk.version_name} onChange={e => setApkField('version_name', e.target.value)} placeholder="2.0.4" /></label>
            <label className="vc2-field"><span className="vc2-label">Min required version code *</span><input className="vc2-input vc2-mono" required type="number" min="1" value={apk.min_required_version_code} onChange={e => setApkField('min_required_version_code', e.target.value)} placeholder="200" /></label>
            <label className="vc2-field"><span className="vc2-label">APK download URL *</span><input className="vc2-input" required value={apk.apk_download_url} onChange={e => setApkField('apk_download_url', e.target.value)} placeholder="https://…/voltcraft-site.apk" /></label>
            <label className="vc2-field vc2-field-wide"><span className="vc2-label">SHA-256 checksum</span><input className="vc2-input vc2-mono" value={apk.sha256_checksum} onChange={e => setApkField('sha256_checksum', e.target.value)} placeholder="e3b0c442…" /></label>
            <label className="vc2-field vc2-field-wide"><span className="vc2-label">Release notes (EN)</span><textarea className="vc2-textarea" value={apk.release_notes_en} onChange={e => setApkField('release_notes_en', e.target.value)} placeholder="Faster riser matrix, offline fixes…" /></label>
          </div>
          <div style={{ marginTop: 14 }}>
            <button className="vc2-btn" type="submit" disabled={apkSubmitting}>{apkSubmitting ? 'Publishing…' : 'Publish Release'}</button>
          </div>
        </form>
      </div>

      {drawer && (
        <>
          <div className="vc2-backdrop" onClick={() => setDrawer(false)} />
          <aside className="vc2-drawer" role="dialog" aria-label="Provision new tenant">
            <div className="vc2-drawer-head">
              <div style={{ flex: 1 }}>
                <h2 className="vc2-drawer-title">Provision New Tenant</h2>
                <div className="vc2-drawer-sub">Creates the company, applies its tier feature flags and creates the first company-admin login.</div>
              </div>
              <button className="vc2-icon-btn" onClick={() => setDrawer(false)} aria-label="Close"><X size={16} /></button>
            </div>
            <form onSubmit={submitTenant} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
              <div className="vc2-drawer-body">
                <div className="vc2-form-grid">
                  <label className="vc2-field vc2-field-wide"><span className="vc2-label">Company legal name *</span><input className="vc2-input" required value={form.company_name} onChange={e => set('company_name', e.target.value)} placeholder="Prospect Electrical Engineering Pte Ltd" /></label>
                  <label className="vc2-field"><span className="vc2-label">UEN number *</span><input className="vc2-input vc2-mono" required value={form.uen_number} onChange={e => set('uen_number', e.target.value)} placeholder="201912345K" /></label>
                  <label className="vc2-field"><span className="vc2-label">BCA grade *</span><input className="vc2-input" required value={form.bca_grade} onChange={e => set('bca_grade', e.target.value)} placeholder="ME05 L3" /></label>
                  <label className="vc2-field">
                    <span className="vc2-label">Subscription tier *</span>
                    <select className="vc2-select" value={form.subscription_tier} onChange={e => set('subscription_tier', e.target.value)}>
                      <option value="STARTER">STARTER — Site Starter</option>
                      <option value="PRO">PRO — Site Pro</option>
                      <option value="ENTERPRISE">ENTERPRISE — Enterprise ERP</option>
                    </select>
                    <span className="vc2-hint">Enables {TIER_MODULE_COUNTS[form.subscription_tier]} of {TOTAL_MODULES} modules.</span>
                  </label>
                  <label className="vc2-field"><span className="vc2-label">Max projects *</span><input className="vc2-input vc2-mono" required type="number" min="1" value={form.max_projects} onChange={e => set('max_projects', e.target.value)} /></label>
                  <label className="vc2-field"><span className="vc2-label">Max users *</span><input className="vc2-input vc2-mono" required type="number" min="1" value={form.max_users} onChange={e => set('max_users', e.target.value)} /></label>
                  <label className="vc2-field"><span className="vc2-label">Contact phone</span><input className="vc2-input" value={form.contact_phone} onChange={e => set('contact_phone', e.target.value)} placeholder="+65 …" /></label>
                  <label className="vc2-field vc2-field-wide"><span className="vc2-label">Office address</span><input className="vc2-input" value={form.office_address} onChange={e => set('office_address', e.target.value)} placeholder="Blk …, Singapore" /></label>
                </div>
                <div className="vc2-section-title">First company admin</div>
                <div className="vc2-form-grid">
                  <label className="vc2-field"><span className="vc2-label">Admin full name *</span><input className="vc2-input" required value={form.admin_full_name} onChange={e => set('admin_full_name', e.target.value)} /></label>
                  <label className="vc2-field"><span className="vc2-label">Admin phone (login) *</span><input className="vc2-input vc2-mono" required value={form.admin_phone} onChange={e => set('admin_phone', e.target.value)} placeholder="81234567" /></label>
                  <label className="vc2-field vc2-field-wide"><span className="vc2-label">Temporary password *</span><input className="vc2-input" required type="password" autoComplete="new-password" value={form.admin_temp_password} onChange={e => set('admin_temp_password', e.target.value)} placeholder="Admin must change on first login" /></label>
                </div>
              </div>
              <div className="vc2-drawer-foot">
                <button type="button" className="vc2-btn vc2-btn-ghost" onClick={() => setDrawer(false)}>Cancel</button>
                <button type="submit" className="vc2-btn" disabled={submitting}>{submitting ? 'Provisioning…' : 'Provision Tenant'}</button>
              </div>
            </form>
          </aside>
        </>
      )}
    </div>
  );
}
