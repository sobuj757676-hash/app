import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { X, Check, Lock, Zap } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../../lib/auth';
import { v2, v2Error, nextStage, STAGE_PIPELINES, STAGE_NAMES, ZONE_CATEGORY_LABELS } from '../../lib/v2api';
import '../../v2.css';

const ADVANCE_ROLES = ['super_admin', 'admin', 'company_admin', 'pm', 'manager', 'engineer', 'supervisor'];
const CATEGORIES = ['ZONE_1_RESIDENTIAL', 'ZONE_2_CORRIDOR', 'ZONE_3_RISER', 'ZONE_4_EXTERNAL'];

function uuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function stageEntry(zone, code) {
  const map = zone?.stage_status_map || {};
  const entry = map[code];
  if (!entry) return {};
  if (typeof entry === 'string') return { status: entry, locked: entry === 'locked' };
  return { status: entry.status || '', locked: !!entry.locked || entry.status === 'locked' };
}

function anyStageLocked(zone) {
  return Object.keys(zone?.stage_status_map || {}).some(code => stageEntry(zone, code).locked);
}

// Law 1: exactly ONE top-right badge, strict priority LIVE > defects > sub-main > locked.
function priorityBadge(zone) {
  if (zone.power_state === 'LIVE_230V' || zone.power_state === 'LIVE_400V') {
    return <span className="vc2-pill vc2-pill-red"><Zap size={11} /> LIVE {zone.power_state.replace('LIVE_', '')}</span>;
  }
  if ((zone.open_defects_count || 0) > 0) {
    return <span className="vc2-pill vc2-pill-red">● {zone.open_defects_count}</span>;
  }
  if (zone.zone_category === 'ZONE_1_RESIDENTIAL' && zone.submain_ready === false) {
    return <span className="vc2-pill vc2-pill-amber">⚠ Sub-main</span>;
  }
  if (anyStageLocked(zone)) {
    return <span className="vc2-pill vc2-pill-green"><Lock size={10} /> Locked</span>;
  }
  return null;
}

export default function ProjectMatrix() {
  const { id } = useParams();
  const { user } = useAuth();
  const canAdvance = ADVANCE_ROLES.includes(user?.role);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [block, setBlock] = useState('');
  const [selected, setSelected] = useState(() => new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [inspectorId, setInspectorId] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [toggles, setToggles] = useState({ work_verified: false, boxes_labels_checked: false, no_open_blockers: false });
  const [advancing, setAdvancing] = useState(false);
  const [advanceError, setAdvanceError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const res = await v2.getMatrix(id);
      setData(res);
      setBlock(prev => {
        const blocks = [...new Set((res.zones || []).map(z => z.block || 'EXT'))];
        return prev && blocks.includes(prev) ? prev : (blocks[0] || '');
      });
    } catch (e) { setLoadError(v2Error(e).message); }
    setLoading(false);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!inspectorId) { setDetail(null); return; }
    let live = true;
    setDetailLoading(true);
    v2.getZone(inspectorId)
      .then(d => { if (live) { setDetail(d); setDetailLoading(false); } })
      .catch(e => { if (live) { toast.error(v2Error(e).message); setDetailLoading(false); setInspectorId(''); } });
    return () => { live = false; };
  }, [inspectorId]);

  const zones = useMemo(() => data?.zones || [], [data]);
  const blocks = useMemo(() => [...new Set(zones.map(z => z.block || 'EXT'))], [zones]);
  const blockZones = useMemo(() => zones.filter(z => (z.block || 'EXT') === block), [zones, block]);

  const floorGroups = useMemo(() => {
    const map = new Map();
    for (const z of blockZones) {
      const key = z.floor === null || z.floor === undefined ? 'EXT' : z.floor;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(z);
    }
    return [...map.entries()].sort((a, b) => {
      if (a[0] === 'EXT') return 1;
      if (b[0] === 'EXT') return -1;
      return Number(a[0]) - Number(b[0]);
    });
  }, [blockZones]);

  const toggleSelect = zoneId => setSelected(prev => {
    const next = new Set(prev);
    if (next.has(zoneId)) next.delete(zoneId); else next.add(zoneId);
    return next;
  });

  // Group selected zones by (category, current stage) → next stage.
  const advanceGroups = useMemo(() => {
    const groups = new Map();
    let atFinal = 0;
    for (const z of zones) {
      if (!selected.has(z.id)) continue;
      const next = nextStage(z);
      if (!next) { atFinal += 1; continue; }
      const key = `${z.zone_category}|${z.current_stage_code}|${next}`;
      if (!groups.has(key)) groups.set(key, { category: z.zone_category, from: z.current_stage_code, to: next, ids: [] });
      groups.get(key).ids.push(z.id);
    }
    return { groups: [...groups.values()], atFinal };
  }, [zones, selected]);

  const allTogglesOn = toggles.work_verified && toggles.boxes_labels_checked && toggles.no_open_blockers;

  const confirmAdvance = async () => {
    setAdvancing(true);
    setAdvanceError('');
    let firstError = '';
    for (const g of advanceGroups.groups) {
      try {
        await v2.batchAdvance(id, {
          work_zone_ids: g.ids,
          from_stage_code: g.from,
          to_stage_code: g.to,
          lock_completed_stage: true,
          pre_rto_readiness: {
            work_verified: toggles.work_verified,
            boxes_labels_checked: toggles.boxes_labels_checked,
            no_open_blockers: toggles.no_open_blockers,
          },
          idempotency_key: uuid(),
        });
      } catch (e) {
        const err = v2Error(e);
        if (!firstError) firstError = `${err.code ? `${err.code} — ` : ''}${err.message}`;
      }
    }
    setAdvancing(false);
    await load();
    if (firstError) { setAdvanceError(firstError); return; }
    const total = advanceGroups.groups.reduce((n, g) => n + g.ids.length, 0);
    toast.success(`${total} zone(s) advanced and previous stage locked.`);
    setModal(false);
    setSelected(new Set());
    setToggles({ work_verified: false, boxes_labels_checked: false, no_open_blockers: false });
  };

  const renderCell = z => {
    const isSel = selected.has(z.id);
    const badge = priorityBadge(z);
    return (
      <div
        key={z.id}
        className={`vc2-cell${isSel ? ' vc2-cell-selected' : ''}`}
        onClick={() => { if (canAdvance && selectMode) toggleSelect(z.id); else setInspectorId(z.id); }}
        role="button"
        tabIndex={0}
        onKeyDown={e => { if (e.key === 'Enter') { if (canAdvance && selectMode) toggleSelect(z.id); else setInspectorId(z.id); } }}
      >
        <span className="vc2-cell-code">{z.zone_code}</span>
        <span className="vc2-cell-stage">{z.current_stage_code}</span>
        {badge && <span className="vc2-cell-badge">{badge}</span>}
      </div>
    );
  };

  const kpis = data?.kpis || {};
  const byCategory = kpis.by_category || {};

  return (
    <div className="vc2-page">
      <div className="vc2-header">
        <div className="vc2-header-main">
          <h1 className="vc2-title">{data?.project?.project_name || 'Project Matrix'}</h1>
          <p className="vc2-subtitle">
            <span className="vc2-mono">{data?.project?.project_code || ''}</span>
            {data?.project ? ' · 4-Zone Spatial Flight Deck — click any cell for the inspector drawer.' : ' · 4-Zone Spatial Flight Deck'}
          </p>
        </div>
        <div className="vc2-header-links">
          {canAdvance && (
            <button type="button" className={`vc2-btn ${selectMode ? 'vc2-btn-primary' : 'vc2-btn-ghost'}`} onClick={() => setSelectMode(m => !m)}>
              {selectMode ? '✓ Selecting — click cells to select' : 'Batch Advance'}
            </button>
          )}
          <Link className="vc2-btn vc2-btn-ghost" to="/projects/new">+ New Project (v2)</Link>
          <Link className="vc2-btn vc2-btn-ghost" to="/super-admin/tenants">Tenants</Link>
        </div>
      </div>

      {loadError && (
        <div className="vc2-banner-red">
          {loadError}{' '}
          <button className="vc2-btn vc2-btn-secondary vc2-btn-small" onClick={load}>Retry</button>
        </div>
      )}
      {advanceError && !modal && <div className="vc2-banner-red">{advanceError}</div>}

      <div className="vc2-kpi-row">
        {CATEGORIES.map(cat => (
          <div className="vc2-kpi-card" key={cat}>
            <div className="vc2-kpi-label">{ZONE_CATEGORY_LABELS[cat]}</div>
            <div className="vc2-kpi-value">{byCategory[cat]?.pct ?? 0}%</div>
            <div className="vc2-progress"><div className="vc2-progress-fill" style={{ width: `${byCategory[cat]?.pct ?? 0}%` }} /></div>
            <div className="vc2-kpi-sub">{byCategory[cat]?.total ?? 0} zones</div>
          </div>
        ))}
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Open Defects</div><div className="vc2-kpi-value" style={{ color: (kpis.open_defects || 0) > 0 ? '#F87171' : undefined }}>{kpis.open_defects ?? 0}</div></div>
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Live Zones</div><div className="vc2-kpi-value" style={{ color: (kpis.live_zones || 0) > 0 ? '#F87171' : undefined }}>{kpis.live_zones ?? 0}</div></div>
        <div className="vc2-kpi-card"><div className="vc2-kpi-label">Sub-main Pending</div><div className="vc2-kpi-value" style={{ color: (kpis.submain_pending || 0) > 0 ? '#FBBF24' : undefined }}>{kpis.submain_pending ?? 0}</div></div>
      </div>

      {loading ? <div className="vc2-loading">Loading spatial matrix…</div> : (
        <>
          <div className="vc2-block-pills">
            {blocks.map(b => (
              <button key={b} className={`vc2-block-pill${b === block ? ' vc2-block-pill-active' : ''}`} onClick={() => setBlock(b)}>
                {b} · {zones.filter(z => (z.block || 'EXT') === b).length}
              </button>
            ))}
          </div>

          {!blockZones.length && <div className="vc2-empty">No zones generated for this project yet.</div>}

          {floorGroups.map(([floor, fzones]) => {
            const common = fzones.filter(z => z.zone_category === 'ZONE_2_CORRIDOR' || z.zone_category === 'ZONE_3_RISER');
            const residential = fzones.filter(z => z.zone_category === 'ZONE_1_RESIDENTIAL');
            const external = fzones.filter(z => z.zone_category === 'ZONE_4_EXTERNAL');
            return (
              <section key={String(floor)}>
                <div className="vc2-floor-title">{floor === 'EXT' ? 'External & Roof' : `Level ${String(floor).padStart(2, '0')}`}</div>
                {common.length > 0 && (
                  <>
                    <div className="vc2-hint" style={{ marginBottom: 6 }}>Common &amp; Risers</div>
                    <div className="vc2-grid" style={{ marginBottom: 12 }}>{common.map(renderCell)}</div>
                  </>
                )}
                {residential.length > 0 && <div className="vc2-grid" style={{ marginBottom: 12 }}>{residential.map(renderCell)}</div>}
                {external.length > 0 && <div className="vc2-grid" style={{ marginBottom: 12 }}>{external.map(renderCell)}</div>}
              </section>
            );
          })}

          {canAdvance && selected.size > 0 && (
            <div className="vc2-action-bar">
              <strong className="vc2-mono">{selected.size} selected</strong>
              <span className="vc2-hint">Advancing locks the completed stage and enforces the sub-main interlock.</span>
              <span style={{ flex: 1 }} />
              <button className="vc2-btn vc2-btn-ghost" onClick={() => setSelected(new Set())}>Clear</button>
              <button className="vc2-btn" onClick={() => { setAdvanceError(''); setModal(true); }}>Advance to Next Stage →</button>
            </div>
          )}
        </>
      )}

      {inspectorId && (
        <>
          <div className="vc2-backdrop" onClick={() => setInspectorId('')} />
          <aside className="vc2-drawer" role="dialog" aria-label="Zone inspector">
            <div className="vc2-drawer-head">
              <div style={{ flex: 1 }}>
                <h2 className="vc2-drawer-title vc2-mono">{detail?.zone_code || 'Zone'}</h2>
                <div className="vc2-drawer-sub">
                  {detail ? `${ZONE_CATEGORY_LABELS[detail.zone_category] || detail.zone_category} · ${detail.unit_type_or_subtype || ''}` : 'Loading…'}
                </div>
              </div>
              <button className="vc2-icon-btn" onClick={() => setInspectorId('')} aria-label="Close"><X size={16} /></button>
            </div>
            <div className="vc2-drawer-body">
              {detailLoading || !detail ? <div className="vc2-loading">Loading zone…</div> : (
                <>
                  {detail.power_state && detail.power_state !== 'DE_ENERGIZED' && detail.power_state !== 'NONE' && (
                    <div className="vc2-banner-red"><Zap size={13} style={{ verticalAlign: -2 }} /> <strong>DANGER — {detail.power_state.replace('_', ' ')}</strong>: this zone is energized. LOTO controls apply.</div>
                  )}
                  <div className="vc2-kv"><span>Block / Floor</span><b className="vc2-mono">{detail.block || '—'} / {detail.floor ?? '—'}</b></div>
                  <div className="vc2-kv"><span>Current stage</span><b className="vc2-mono">{detail.current_stage_code}</b></div>
                  <div className="vc2-kv"><span>Power state</span><b className="vc2-mono">{detail.power_state || '—'}</b></div>
                  <div className="vc2-kv"><span>Open defects</span><b className="vc2-mono">{detail.open_defects_count ?? 0}</b></div>
                  <div className="vc2-kv"><span>Units depending on this zone</span><b className="vc2-mono">{detail.dependents_count ?? 0}</b></div>

                  <div className="vc2-section-title">Stage Pipeline</div>
                  <div className="vc2-stage-list">
                    {(STAGE_PIPELINES[detail.zone_category] || []).map(code => {
                      const entry = stageEntry(detail, code);
                      const isCurrent = code === detail.current_stage_code;
                      return (
                        <div key={code} className={`vc2-stage-row${isCurrent ? ' vc2-stage-row-current' : ''}`}>
                          <span className="vc2-stage-code">{code}</span>
                          <span style={{ flex: 1 }}>{STAGE_NAMES[code] || code}</span>
                          {entry.locked && <span className="vc2-pill vc2-pill-green"><Lock size={10} /> Locked</span>}
                          {!entry.locked && entry.checked && <span className="vc2-pill vc2-pill-green"><Check size={10} /> Done</span>}
                          {isCurrent && <span className="vc2-pill vc2-pill-blue">Current</span>}
                        </div>
                      );
                    })}
                  </div>

                  <div className="vc2-section-title">Sub-main Interlock</div>
                  {(detail.dependencies || []).length === 0 ? (
                    <p className="vc2-hint">This zone has no upstream dependencies.</p>
                  ) : (
                    <>
                      {(detail.dependencies || []).every(d => d.dependency_completed)
                        ? <div className="vc2-banner-green">Sub-main ready — all upstream dependencies are complete. Live testing &amp; handover unlocked.</div>
                        : <div className="vc2-banner-amber">Sub-main pending — live testing (S5) and handover (S6) stay locked until every dependency below is complete.</div>}
                      {(detail.dependencies || []).map(d => (
                        <div className="vc2-dep-row" key={d.id}>
                          <span>
                            <strong className="vc2-mono">{d.zone_code}</strong><br />
                            <span className="vc2-hint">{ZONE_CATEGORY_LABELS[d.zone_category] || d.zone_category} · needs {d.dependency_stage_code}</span>
                          </span>
                          {d.dependency_completed
                            ? <span className="vc2-pill vc2-pill-green"><Check size={10} /> Completed</span>
                            : <span className="vc2-pill vc2-pill-amber">Pending ({d.current_stage_code})</span>}
                        </div>
                      ))}
                    </>
                  )}
                </>
              )}
            </div>
          </aside>
        </>
      )}

      {modal && (
        <div className="vc2-modal-wrap">
          <div className="vc2-backdrop" onClick={() => !advancing && setModal(false)} />
          <div className="vc2-modal" role="dialog" aria-label="Pre-RTO readiness check">
            <h2 className="vc2-title" style={{ fontSize: 18 }}>Pre-RTO Readiness Check</h2>
            <p className="vc2-subtitle" style={{ marginBottom: 14 }}>
              Confirm all three checks before advancing. The completed stage will be locked and the sub-main interlock is enforced by the server.
            </p>
            {advanceGroups.groups.map(g => (
              <div className="vc2-kv" key={`${g.category}|${g.from}`}>
                <span>{ZONE_CATEGORY_LABELS[g.category] || g.category}</span>
                <b className="vc2-mono">{g.ids.length} zones · {g.from} → {g.to}</b>
              </div>
            ))}
            {advanceGroups.atFinal > 0 && <p className="vc2-hint" style={{ margin: '8px 0' }}>{advanceGroups.atFinal} selected zone(s) are already at the final stage and will be skipped.</p>}
            <div style={{ marginTop: 14 }}>
              {[
                ['work_verified', 'Work physically verified on site'],
                ['boxes_labels_checked', 'Backboxes, conduits & circuit labels checked'],
                ['no_open_blockers', 'No open critical blockers in selected units'],
              ].map(([key, label]) => (
                <div className="vc2-toggle-row" key={key}>
                  <span>{label}</span>
                  <button
                    type="button"
                    aria-pressed={toggles[key]}
                    className={`vc2-switch${toggles[key] ? ' vc2-switch-on' : ''}`}
                    onClick={() => setToggles(t => ({ ...t, [key]: !t[key] }))}
                  />
                </div>
              ))}
            </div>
            {advanceError && <div className="vc2-banner-red" style={{ marginTop: 12 }}>{advanceError}</div>}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="vc2-btn vc2-btn-ghost" disabled={advancing} onClick={() => setModal(false)}>Cancel</button>
              <button className="vc2-btn" disabled={!allTogglesOn || advancing || advanceGroups.groups.length === 0} onClick={confirmAdvance}>
                <Lock size={14} /> {advancing ? 'Advancing…' : 'Confirm & Lock Stage'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
