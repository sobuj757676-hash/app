import {walkFloors, pendingInspectionByUnit, proposedUnitIds, applyFloorPass, gateIndexOf} from './rtoWalk';

const stages = [
 {id: 's0', name: 'Start', requires_rto: false},
 {id: 's1', name: 'Gate stage', requires_rto: true},
 {id: 's2', name: 'After', requires_rto: false},
];
const unit = (id, block, level, number, stage, rto = 'none') => ({id, block, level, number, stage, rto});
const data = {
 project: {workflow_stages: stages},
 blocks: [{name: '35A'}, {name: '45B'}],
 units: [
  unit('a', '35A', 3, '403', 1), unit('b', '35A', 3, '401', 1, 'pending'),
  unit('c', '35A', 8, '407', 1, 'rework'), unit('d', '35A', 3, '405', 0),
  unit('e', '45B', 3, '401', 1), unit('f', '35A', 8, '409', 2),
 ],
 inspections: [
  {id: 'i1', unit_id: 'b', status: 'pending', proposed_result: 'approved', proposed_by: {id: 'u1', name: 'Sup'}},
  {id: 'i2', unit_id: 'c', status: 'pending'},
  {id: 'i3', unit_id: 'f', status: 'approved', proposed_result: 'approved'},
 ],
};

test('gate index derives from stage config', () => {
 expect(gateIndexOf(data)).toBe(1);
});

test('walkFloors groups gate-stage units of one block by level, sorted', () => {
 const floors = walkFloors(data, '35A');
 expect(floors.map(f => f.level)).toEqual([3, 8]);
 expect(floors[0].units.map(u => u.id)).toEqual(['b', 'a']); // by number: 401, 403
 expect(floors[1].units.map(u => u.id)).toEqual(['c']);
});

test('pending map and proposed set read server state only', () => {
 const pending = pendingInspectionByUnit(data);
 expect([...pending.keys()].sort()).toEqual(['b', 'c']);
 expect(proposedUnitIds(data)).toEqual(new Set(['b']));
});

test('floor pass marks non-failed units, skips proposed-locked ones', () => {
 const floor = walkFloors(data, '35A')[0]; // units b (proposed), a
 const next = applyFloorPass({a: 'fail'}, floor, new Set(['b']));
 expect(next).toEqual({a: 'fail'}); // fail preserved; b locked, untouched
 const next2 = applyFloorPass({}, floor, new Set());
 expect(next2).toEqual({b: 'pass', a: 'pass'});
});
