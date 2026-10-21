// Derivation tests for the Daily Plan top-notch Phase 1 helpers
// (spec v2 §3 stage-aware remaining; v2.1 §B/§C advance state + Pending
// Advance). Run: CI=true npx craco test --watchAll=false
import {DEFAULT_STAGES} from './api';
import {remainingUnitIds, advancedUnitIds, pendingAdvanceUnits, pendingAdvanceGroups,
        gateIndexOf, plannedUnitIdSet, isReadyUnit, lensPass, rtoQueueCounts,
        recentPairs, todayLoadSets, draftLoadCount} from './planTasks';

const unit = (id, stage, extra = {}) => ({
  id, block: '40A', block_id: 'b1', level: 2, number: String(400 + Number(id.slice(1))),
  stage, rto: 'none', points: [], history: [], ...extra,
});
const task = (over = {}) => ({
  id: 't1', kind: 'planned', status: 'in_progress', plan_date: '2026-10-01',
  scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: []},
  completed_unit_ids: [], assignees: [], ...over,
});
const data = (units, extra = {}) => ({
  project: {workflow_stages: DEFAULT_STAGES}, units, defects: [], tests: [], tasks: [], ...extra,
});

test('remainingUnitIds is stage-aware', () => {
  const units = [unit('u1', 3), unit('u2', 3), unit('u3', 4), unit('u4', 3)];
  const t = task({scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u1', 'u2', 'u3', 'u4']},
                  completed_unit_ids: ['u2']});
  // u1: unchecked + at stage -> remaining. u2: checked -> advance flow.
  // u3: unchecked but stage moved -> tracker truth, not remaining. u4: remaining.
  expect(remainingUnitIds(t, data(units))).toEqual(['u1', 'u4']);
});

test('advancedUnitIds requires this task\'s own plan_advance history event', () => {
  const mine = unit('u1', 4, {history: [{stage: 3, to_stage: 4, source: 'plan_advance', task_id: 't1'}]});
  const other = unit('u2', 4, {history: [{stage: 3, to_stage: 4, note: 'Bulk advance', by: 'Mgr'}]});
  const t = task({completed_unit_ids: ['u1', 'u2'],
                  scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u1', 'u2']}});
  expect(advancedUnitIds(t, data([mine, other]))).toEqual(['u1']);
});

test('pendingAdvanceUnits classifies ready / rto / defect / tests / conflict', () => {
  const ready = unit('u1', 3);
  const conflict = unit('u2', 4, {history: [{stage: 3, to_stage: 4, note: 'Bulk advance'}]});
  const t = task({completed_unit_ids: ['u1', 'u2'],
                  scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u1', 'u2']}});
  const got = pendingAdvanceUnits(t, data([ready, conflict]));
  expect(got.map(g => [g.unit.id, g.reason])).toEqual([['u1', 'ready'], ['u2', 'conflict']]);

  const gate = unit('u3', 5);
  const tRto = task({id: 't2', completed_unit_ids: ['u3'],
                     scope: {block_id: 'b1', level: 2, stage_index: 5, unit_ids: ['u3']}});
  expect(pendingAdvanceUnits(tRto, data([gate]))[0].reason).toBe('rto');

  const du = unit('u4', 3);
  const defects = [{unit_id: 'u4', severity: 'critical', status: 'open', title: 'Live conductor'}];
  const tDef = task({id: 't3', completed_unit_ids: ['u4'],
                     scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u4']}});
  const gotDef = pendingAdvanceUnits(tDef, data([du], {defects}));
  expect(gotDef[0].reason).toBe('defect');
  expect(gotDef[0].detail).toBe('Live conductor');

  const fin = unit('u5', 8, {points: [{id: 'p1'}]});
  const tFin = task({id: 't4', completed_unit_ids: ['u5'],
                     scope: {block_id: 'b1', level: 2, stage_index: 8, unit_ids: ['u5']}});
  expect(pendingAdvanceUnits(tFin, data([fin]))[0].reason).toBe('tests');
});

test('pendingAdvanceUnits excludes own-advanced units and cancelled tasks', () => {
  const adv = unit('u1', 4, {history: [{stage: 3, to_stage: 4, source: 'plan_advance', task_id: 't1'}]});
  const t = task({completed_unit_ids: ['u1'],
                  scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u1']}});
  expect(pendingAdvanceUnits(t, data([adv]))).toEqual([]);
  const cancelled = task({status: 'cancelled', completed_unit_ids: ['u1'],
                          scope: {block_id: 'b1', level: 2, stage_index: 3, unit_ids: ['u1']}});
  expect(pendingAdvanceUnits(cancelled, data([unit('u1', 3)]))).toEqual([]);
});

// REGRESSION (spec v2.1 addendum, mandated 2026-10-21): a task marked done
// while a checked unit remains blocked must keep that unit visible in
// Pending Advance after the plan date passes. 'done' never strands work.
// ---- Top-notch Phase 2: lenses / Recent Pairs / load counts ----
// Custom stage list with the RTO gate at index 1 (default is 5): every
// predicate must follow THIS configuration, never a hardcoded number.
const CUSTOM_STAGES = [
  {id: 'a', name: 'Alpha', requires_rto: false},
  {id: 'b', name: 'Gate stage', requires_rto: true},
  {id: 'c', name: 'Gamma', requires_rto: false},
];
const dataC = (units, extra = {}) => ({
  project: {workflow_stages: CUSTOM_STAGES}, units, defects: [], tests: [], tasks: [], ...extra,
});

test('gateIndexOf follows the project stage configuration', () => {
  expect(gateIndexOf(dataC([]))).toBe(1);
  expect(gateIndexOf(data([]))).toBe(5);
  expect(gateIndexOf({project: {workflow_stages: [{id: 'x', name: 'X'}]}})).toBe(-1);
});

test('isReadyUnit excludes complete / gate / rto-pending / planned / critical-defect units', () => {
  const planned = plannedUnitIdSet([task({plan_date: '2026-10-21', scope: {unit_ids: ['u6']}})], '2026-10-21');
  const D = '2026-10-21';
  expect(isReadyUnit(dataC([unit('u1', 0)]), unit('u1', 0), D, planned)).toBe(true);
  expect(isReadyUnit(dataC([unit('u2', 1)]), unit('u2', 1), D, planned)).toBe(false); // at the gate
  expect(isReadyUnit(dataC([unit('u3', 2)]), unit('u3', 2, {rto: 'pending'}), D, planned)).toBe(false);
  expect(isReadyUnit(dataC([unit('u4', 2)]), unit('u4', 2, {rto: 'rework'}), D, planned)).toBe(true);
  expect(isReadyUnit(dataC([unit('u5', 3)]), unit('u5', 3), D, planned)).toBe(false); // complete
  expect(isReadyUnit(dataC([unit('u6', 0)]), unit('u6', 0), D, planned)).toBe(false); // planned today
  const crit = [{unit_id: 'u7', severity: 'critical', status: 'open', title: 'x'}];
  expect(isReadyUnit(dataC([unit('u7', 0)], {defects: crit}), unit('u7', 0), D, planned)).toBe(false);
  const verified = [{unit_id: 'u7', severity: 'critical', status: 'verified', title: 'x'}];
  expect(isReadyUnit(dataC([unit('u7', 0)], {defects: verified}), unit('u7', 0), D, planned)).toBe(true);
  const major = [{unit_id: 'u7', severity: 'major', status: 'open', title: 'x'}];
  expect(isReadyUnit(dataC([unit('u7', 0)], {defects: major}), unit('u7', 0), D, planned)).toBe(true);
});

test('lensPass rto follows the configured gate, not the default index', () => {
  const empty = new Set();
  expect(lensPass(dataC([]), unit('u1', 1), 'rto', '2026-10-21', empty)).toBe(true);
  expect(lensPass(dataC([]), unit('u2', 2), 'rto', '2026-10-21', empty)).toBe(false);
  expect(lensPass(dataC([]), unit('u3', 0), 'all', '2026-10-21', empty)).toBe(true);
});

test('rtoQueueCounts counts only gate-stage units, split by sub-state', () => {
  const units = [unit('u1', 1), unit('u2', 1), unit('u3', 1, {rto: 'pending'}),
                 unit('u4', 1, {rto: 'rework'}), unit('u5', 0), unit('u6', 2, {rto: 'pending'})];
  expect(rtoQueueCounts(dataC(units))).toEqual({total: 4, none: 2, pending: 1, rework: 1, approved: 0});
});

test('plannedUnitIdSet includes done tasks, excludes cancelled and other dates', () => {
  const tasks = [
    task({id: 'a', status: 'done', plan_date: '2026-10-21', scope: {unit_ids: ['u1']}}),
    task({id: 'b', status: 'cancelled', plan_date: '2026-10-21', scope: {unit_ids: ['u2']}}),
    task({id: 'c', status: 'todo', plan_date: '2026-10-20', scope: {unit_ids: ['u3']}}),
    task({id: 'd', status: 'todo', plan_date: '2026-10-21', scope: {unit_ids: ['u4', 'u1']}}),
  ];
  expect([...plannedUnitIdSet(tasks, '2026-10-21')].sort()).toEqual(['u1', 'u4']);
});

test('recentPairs ranks by frequency then recency, 7-day window, set-order insensitive', () => {
  const pt = (id, date, assignees, names) => task({id, plan_date: date, assignees, assignee_names: names});
  const tasks = [
    pt('a', '2026-10-20', ['w1', 'w2'], ['Ann', 'Bob']),
    pt('b', '2026-10-19', ['w2', 'w1'], ['Bob', 'Ann']),
    pt('c', '2026-10-15', ['w1', 'w2'], ['Ann', 'Bob']),
    pt('d', '2026-10-21', ['w3'], ['Cid']),
    pt('e', '2026-10-16', ['w5'], ['Eli']),
    pt('f', '2026-10-13', ['w4'], ['Dee']),            // 8 days before -> outside window
    pt('g', '2026-10-20', [], []),                      // no assignees -> ignored
    task({id: 'h', kind: 'adhoc', plan_date: null, assignees: ['w9']}), // not planned -> ignored
  ];
  const pairs = recentPairs(tasks, '2026-10-21');
  expect(pairs).toHaveLength(3);
  expect(pairs[0].ids.sort()).toEqual(['w1', 'w2']);
  expect(pairs[0].count).toBe(3);
  expect(pairs[0].last).toBe('2026-10-20');
  expect(pairs[1].ids).toEqual(['w3']); // count tie with w5, more recent first
  expect(pairs[2].ids).toEqual(['w5']);
});

test('todayLoadSets is a per-worker set union (overlap counts once)', () => {
  const tasks = [
    task({id: 'a', plan_date: '2026-10-21', assignees: ['w1'], scope: {unit_ids: ['u1', 'u2']}}),
    task({id: 'b', plan_date: '2026-10-21', assignees: ['w1', 'w2'], scope: {unit_ids: ['u2', 'u3']}}),
    task({id: 'c', plan_date: '2026-10-21', status: 'cancelled', assignees: ['w1'], scope: {unit_ids: ['u9']}}),
    task({id: 'd', plan_date: '2026-10-20', assignees: ['w1'], scope: {unit_ids: ['u8']}}),
  ];
  const sets = todayLoadSets(tasks, '2026-10-21');
  expect([...sets.get('w1')].sort()).toEqual(['u1', 'u2', 'u3']);
  expect([...sets.get('w2')]).toEqual(['u2', 'u3']);
});

test('draftLoadCount adds other draft groups but not the group being edited', () => {
  const loadSets = todayLoadSets(
    [task({id: 'a', plan_date: '2026-10-21', assignees: ['w1'], scope: {unit_ids: ['u1', 'u2']}})],
    '2026-10-21');
  const groups = [{key: 'g1', units: [unit('u3', 0), unit('u4', 0)]},
                  {key: 'g2', units: [unit('u4', 0), unit('u5', 0)]}];
  const cfg = {g1: {assignees: ['w1']}, g2: {assignees: ['w1']}};
  // editing g1: persisted {u1,u2} + g2's {u4,u5} = 4 (g1's own units excluded)
  expect(draftLoadCount(loadSets, groups, cfg, 'w1', 'g1')).toBe(4);
  expect(draftLoadCount(loadSets, groups, cfg, 'w9', 'g1')).toBe(0);
});

test('done task with a blocked checked unit stays in Pending Advance', () => {
  const gate = unit('u1', 5); // sitting at the RTO gate stage, cannot advance
  const doneTask = task({status: 'done', plan_date: '2026-10-01', // plan date long past
                         completed_unit_ids: ['u1'],
                         scope: {block_id: 'b1', level: 2, stage_index: 5, unit_ids: ['u1']}});
  const groups = pendingAdvanceGroups([doneTask], data([gate]));
  expect(groups).toHaveLength(1);
  expect(groups[0].task.id).toBe('t1');
  expect(groups[0].items).toHaveLength(1);
  expect(groups[0].items[0].reason).toBe('rto');
  // And the unit must NOT be counted as remaining work or as advanced:
  expect(remainingUnitIds(doneTask, data([gate]))).toEqual([]);
  expect(advancedUnitIds(doneTask, data([gate]))).toEqual([]);
});
