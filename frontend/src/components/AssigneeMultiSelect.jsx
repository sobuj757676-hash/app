import {useLanguage} from '../lib/i18n';
/** Multi-select checkbox list grouped by role (workers first), mobile-friendly.
 *  Props: directory (users), value [userId], onChange(ids), id (testid prefix). */
export function AssigneeMultiSelect({directory,value=[],onChange,id='assignees'}){
 const {t}=useLanguage();
 const workers=directory.filter(u=>u.role==='worker'),others=directory.filter(u=>u.role!=='worker');
 const toggle=uid=>onChange(value.includes(uid)?value.filter(x=>x!==uid):[...value,uid]);
 const row=u=><label key={u.id} className="assignee-row" data-testid={`${id}-row-${u.id}`}><input type="checkbox" checked={value.includes(u.id)} onChange={()=>toggle(u.id)}/><span className="assignee-name">{u.name}<small>{t(u.role)}</small></span></label>;
 return <div className="assignee-multi" data-testid={id}>
  <div className="assignee-group"><div className="assignee-group-head"><strong data-testid={`${id}-workers-head`}>{t('worker')} · {workers.filter(u=>value.includes(u.id)).length}/{workers.length}</strong><span><button type="button" className="text-link" data-testid={`${id}-select-all`} onClick={()=>onChange([...new Set([...value,...workers.map(u=>u.id)])])}>{t('selectAll')}</button><button type="button" className="text-link" data-testid={`${id}-clear`} onClick={()=>onChange(value.filter(x=>!workers.some(u=>u.id===x)))}>{t('clearSelection')}</button></span></div><div className="assignee-list">{workers.map(row)}</div></div>
  {!!others.length&&<div className="assignee-group"><div className="assignee-group-head"><strong>{t('assignTo')}</strong></div><div className="assignee-list">{others.map(row)}</div></div>}
 </div>;
}
