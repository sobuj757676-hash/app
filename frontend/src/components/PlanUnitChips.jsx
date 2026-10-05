import {AlertTriangle} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {label} from '../lib/api';
import {staleUnits,plannedUnitIds,completedUnitIds,resolveStage} from '../lib/planTasks';

// Unit chips as 44px checkboxes. `checked` = current completed_unit_ids list;
// `onToggle(id)` patches the full replacement list on the parent.
// `busy` = task id currently syncing (disables while a PATCH is in flight).
export function UnitCheckboxes({task,data,checked,onToggle,busy,testPrefix}){
 const ids=plannedUnitIds(task);
 return <div className="unit-chips" role="group" aria-label={String(task.id)}>
  {ids.map(id=>{
   const u=data.units.find(x=>x.id===id);
   const isC=checked.includes(id);
   return <label key={id} className={`unit-chip${isC?' checked':''}`} data-testid={`${testPrefix}-chip-${id}`}>
    <input type="checkbox" checked={isC} disabled={busy===task.id} onChange={()=>onToggle(id)} aria-label={u?label(u):id}/>
    <span>{u?label(u):id.slice(0,6)}</span>
   </label>;
  })}
 </div>;
}

// Client-side staleness flag: any scope unit whose live stage differs from the
// planned stage_index, or that is in RTO rework. Lists the moved units.
export function StaleFlag({task,data,testPrefix}){
 const {t}=useLanguage();
 const items=staleUnits(task,data);
 if(!items.length)return null;
 const parts=items.map(u=>{
  const l=label(u);
  return u.rto==='rework'?`${l} · ${t('rework')}`:`${l} → ${resolveStage(data,u.stage,t)}`;
 });
 return <div className="stale-flag" data-testid={testPrefix} role="alert">
  <AlertTriangle size={15}/>
  <span><b>{t('staleStage')}</b>{parts.length?`: ${parts.join('; ')}`:''}</span>
 </div>;
}

// "2/4 done" — execution progress for a planned task.
export function PlanProgress({task,testId}){
 const {t}=useLanguage();
 const done=completedUnitIds(task).length,total=plannedUnitIds(task).length;
 return <span className="mono plan-progress" data-testid={testId}>{t('unitProgress').replace('{done}',String(done)).replace('{total}',String(total))}</span>;
}
