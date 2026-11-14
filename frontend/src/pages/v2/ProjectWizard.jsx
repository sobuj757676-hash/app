import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../lib/auth';
import { v2, v2Error } from '../../lib/v2api';
import '../../v2.css';

// Parses "101:4-Room, 103:4-Room, 105:3-Room" into [{stack, unit_type}].
// An entry without ":type" defaults to 4-Room.
export function parseStacks(text) {
  return String(text || '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
    .map(entry => {
      const [stack, type] = entry.split(':').map(x => (x || '').trim());
      return { stack, unit_type: type || '4-Room' };
    })
    .filter(s => s.stack);
}

const newBlock = () => ({ block: '', floor_from: 1, floor_to: 16, stacksText: '101:4-Room, 103:4-Room, 105:3-Room, 107:2-Room' });

export default function ProjectWizard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isSuperAdmin = user?.role === 'super_admin';
  const [tenants, setTenants] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [form, setForm] = useState({ project_code: '', project_name: '', project_type: 'HDB_BTO', main_contractor_name: '' });
  const [blocks, setBlocks] = useState([{ block: '401A', floor_from: 1, floor_to: 16, stacksText: '101:4-Room, 103:4-Room, 105:3-Room, 107:2-Room' }]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isSuperAdmin) return;
    v2.listTenants()
      .then(list => { setTenants(list); if (list.length) setCompanyId(list[0].id); })
      .catch(e => toast.error(v2Error(e).message));
  }, [isSuperAdmin]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const setBlock = (i, k, v) => setBlocks(bs => bs.map((b, j) => (j === i ? { ...b, [k]: v } : b)));
  const addBlock = () => setBlocks(bs => [...bs, newBlock()]);
  const removeBlock = i => setBlocks(bs => bs.filter((_, j) => j !== i));

  // Live preview — pure client math mirroring the backend spatial generator:
  // per block: residential = floors × stacks, corridor = floors, riser = floors × 2,
  // external = 4 fixed zones. Stage-task estimate weights zones by pipeline length.
  const preview = useMemo(() => {
    const rows = blocks.map(b => {
      const floors = Math.max(0, (Number(b.floor_to) || 0) - (Number(b.floor_from) || 0) + 1);
      const stacks = parseStacks(b.stacksText).length;
      const residential = floors * stacks;
      const corridor = floors;
      const riser = floors * 2;
      const external = 4;
      return {
        block: b.block || '—', floors, stacks, residential, corridor, riser, external,
        zones: residential + corridor + riser + external,
        stageTasks: residential * 6 + corridor * 5 + riser * 5 + external * 5,
      };
    });
    const totals = rows.reduce(
      (a, r) => ({
        residential: a.residential + r.residential, corridor: a.corridor + r.corridor,
        riser: a.riser + r.riser, external: a.external + r.external,
        zones: a.zones + r.zones, stageTasks: a.stageTasks + r.stageTasks,
      }),
      { residential: 0, corridor: 0, riser: 0, external: 0, zones: 0, stageTasks: 0 },
    );
    return { rows, totals };
  }, [blocks]);

  const submit = async e => {
    e.preventDefault();
    const blocksConfig = [];
    for (const b of blocks) {
      const stacks = parseStacks(b.stacksText);
      if (!b.block.trim()) { toast.error('Every block needs a name (e.g. 401A).'); return; }
      if (!stacks.length) { toast.error(`Block ${b.block}: add at least one stack, e.g. "101:4-Room".`); return; }
      if ((Number(b.floor_to) || 0) < (Number(b.floor_from) || 0)) { toast.error(`Block ${b.block}: floor_to must be ≥ floor_from.`); return; }
      blocksConfig.push({
        block: b.block.trim(),
        floor_from: Number(b.floor_from) || 1,
        floor_to: Number(b.floor_to) || 1,
        stacks,
        external_zones: [],
      });
    }
    if (isSuperAdmin && !companyId) { toast.error('Select the tenant company for this project.'); return; }
    const payload = {
      project_code: form.project_code.trim(),
      project_name: form.project_name.trim(),
      project_type: form.project_type,
      main_contractor_name: form.main_contractor_name.trim(),
      blocks_config: blocksConfig,
    };
    if (isSuperAdmin) payload.company_id = companyId;
    setSubmitting(true);
    try {
      const res = await v2.createProject(payload);
      const gen = res.generation || {};
      toast.success(`Project created — ${gen.total_zones ?? preview.totals.zones} work zones generated across 4 zones categories.`);
      navigate(`/projects/${res.project.id}/matrix`);
    } catch (err) { toast.error(v2Error(err).message); }
    setSubmitting(false);
  };

  return (
    <div className="vc2-page">
      <div className="vc2-header">
        <div className="vc2-header-main">
          <h1 className="vc2-title">New Project — 4-Zone Setup Wizard</h1>
          <p className="vc2-subtitle">Define blocks, floors and stacks once — the spatial generator creates every Residential, Corridor, Riser and External work zone with its stage pipeline and the sub-main interlock.</p>
        </div>
        <div className="vc2-header-links">
          <Link className="vc2-btn vc2-btn-ghost" to="/super-admin/tenants">Tenants</Link>
          <Link className="vc2-btn vc2-btn-ghost" to="/projects">Existing Projects</Link>
        </div>
      </div>

      <form onSubmit={submit}>
        <div className="vc2-two-col">
          <div>
            <div className="vc2-card">
              <h2 className="vc2-card-title">Project details</h2>
              <p className="vc2-card-sub">Basic contract information for the Control Tower.</p>
              <div className="vc2-form-grid">
                {isSuperAdmin && (
                  <label className="vc2-field vc2-field-wide">
                    <span className="vc2-label">Tenant company *</span>
                    <select className="vc2-select" value={companyId} onChange={e => setCompanyId(e.target.value)}>
                      {tenants.map(t => <option key={t.id} value={t.id}>{t.company_name}</option>)}
                    </select>
                  </label>
                )}
                <label className="vc2-field"><span className="vc2-label">Project code *</span><input className="vc2-input vc2-mono" required value={form.project_code} onChange={e => set('project_code', e.target.value)} placeholder="Tengah-C12" /></label>
                <label className="vc2-field"><span className="vc2-label">Project name *</span><input className="vc2-input" required value={form.project_name} onChange={e => set('project_name', e.target.value)} placeholder="Tengah BTO C12" /></label>
                <label className="vc2-field">
                  <span className="vc2-label">Project type *</span>
                  <select className="vc2-select" value={form.project_type} onChange={e => set('project_type', e.target.value)}>
                    <option value="HDB_BTO">HDB BTO</option>
                    <option value="HDB_HIP">HDB HIP (Re-wiring)</option>
                    <option value="COMMERCIAL_ME">Commercial M&E</option>
                  </select>
                </label>
                <label className="vc2-field"><span className="vc2-label">Main contractor</span><input className="vc2-input" value={form.main_contractor_name} onChange={e => set('main_contractor_name', e.target.value)} placeholder="Main contractor name" /></label>
              </div>
            </div>

            <div className="vc2-card">
              <h2 className="vc2-card-title">Blocks</h2>
              <p className="vc2-card-sub">Stacks format: <span className="vc2-mono">101:4-Room, 103:4-Room, 105:3-Room</span> — one entry per unit stack on each floor.</p>
              {blocks.map((b, i) => (
                <div className="vc2-block-editor-row" key={i}>
                  <div className="vc2-form-grid">
                    <label className="vc2-field"><span className="vc2-label">Block *</span><input className="vc2-input vc2-mono" required value={b.block} onChange={e => setBlock(i, 'block', e.target.value)} placeholder="401A" /></label>
                    <label className="vc2-field"><span className="vc2-label">Floors (from – to) *</span>
                      <span style={{ display: 'flex', gap: 8 }}>
                        <input className="vc2-input vc2-mono" required type="number" min="1" max="60" value={b.floor_from} onChange={e => setBlock(i, 'floor_from', e.target.value)} />
                        <input className="vc2-input vc2-mono" required type="number" min="1" max="60" value={b.floor_to} onChange={e => setBlock(i, 'floor_to', e.target.value)} />
                      </span>
                    </label>
                    <label className="vc2-field vc2-field-wide"><span className="vc2-label">Unit stacks per floor *</span><input className="vc2-input vc2-mono" required value={b.stacksText} onChange={e => setBlock(i, 'stacksText', e.target.value)} placeholder="101:4-Room, 103:4-Room, 105:3-Room" /></label>
                  </div>
                  {blocks.length > 1 && (
                    <div style={{ marginTop: 10 }}>
                      <button type="button" className="vc2-btn vc2-btn-danger-outline vc2-btn-small" onClick={() => removeBlock(i)}><Trash2 size={13} /> Remove block</button>
                    </div>
                  )}
                </div>
              ))}
              <button type="button" className="vc2-btn vc2-btn-secondary" onClick={addBlock}><Plus size={15} /> Add Block</button>
            </div>

            <button className="vc2-btn" type="submit" disabled={submitting} style={{ minHeight: 48, padding: '0 26px', fontSize: 15 }}>
              {submitting ? 'Generating zones…' : `Create Project & Generate ${preview.totals.zones} Zones`}
            </button>
          </div>

          <div className="vc2-card" style={{ position: 'sticky', top: 12 }}>
            <h2 className="vc2-card-title">Live Generation Preview</h2>
            <p className="vc2-card-sub">Updates as you type — exactly what the spatial generator will create.</p>
            <div className="vc2-table-wrap">
              <table className="vc2-table">
                <thead><tr><th>Block</th><th>Res.</th><th>Corr.</th><th>Riser</th><th>Ext.</th><th>Zones</th></tr></thead>
                <tbody>
                  {preview.rows.map((r, i) => (
                    <tr key={i}>
                      <td><strong className="vc2-mono">{r.block}</strong><br /><span className="vc2-hint">{r.floors} floors × {r.stacks} stacks</span></td>
                      <td className="vc2-mono">{r.residential}</td>
                      <td className="vc2-mono">{r.corridor}</td>
                      <td className="vc2-mono">{r.riser}</td>
                      <td className="vc2-mono">{r.external}</td>
                      <td className="vc2-mono"><strong>{r.zones}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 14 }}>
              <div className="vc2-kv"><span>Total work zones</span><b className="vc2-mono">{preview.totals.zones}</b></div>
              <div className="vc2-kv"><span>Residential (S1–S6)</span><b className="vc2-mono">{preview.totals.residential}</b></div>
              <div className="vc2-kv"><span>Corridor (C1–C5)</span><b className="vc2-mono">{preview.totals.corridor}</b></div>
              <div className="vc2-kv"><span>Risers (R1–R5)</span><b className="vc2-mono">{preview.totals.riser}</b></div>
              <div className="vc2-kv"><span>External (M1–M5)</span><b className="vc2-mono">{preview.totals.external}</b></div>
              <div className="vc2-kv"><span>Estimated stage tasks</span><b className="vc2-mono">{preview.totals.stageTasks}</b></div>
            </div>
            <p className="vc2-hint" style={{ marginTop: 12 }}>Each floor&rsquo;s residential units are interlocked to that floor&rsquo;s Corridor C3 and LV Riser R3 — live testing and handover stay locked until the sub-main is complete.</p>
          </div>
        </div>
      </form>
    </div>
  );
}
