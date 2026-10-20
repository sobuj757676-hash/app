// Derivation tests for the Daily Plan top-notch Phase 1 helpers
// (spec v2 §3 stage-aware remaining; v2.1 §B/§C advance state + Pending
// Advance). Run: CI=true npx craco test --watchAll=false
import {DEFAULT_STAGES} from './api';
import {remainingUnitIds, advancedUnitIds, pendingAdvanceUnits, pendingAdvanceGroups} from './planTasks';

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
