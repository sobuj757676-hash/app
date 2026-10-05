import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {label} from '../lib/api';
import {FormModal} from './Common';

export const DEFECT_CATS=['workmanship','material','design-drawing','safety','other'];
export const DEFECT_SEVS=['critical','major','minor'];

// Group units by block, in block order. Returns [{block,options}]; block is '' for block-less units.
export function unitGroups(units,blocks=[]){
 const order=new Map((blocks||[]).map((b,i)=>[b.name??b,i]));
 const groups=new Map();
 (units||[]).forEach(u=>{const k=u.block||'';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(u);});
 return [...groups.entries()]
  .sort((a,b)=>(order.has(a[0])?order.get(a[0]):1e9)-(order.has(b[0])?order.get(b[0]):1e9))
  .map(([block,us])=>({block,options:us.map(u=>({value:u.id,label:label(u)}))}));
}

export function DefectReportModal({onClose}){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();
 const options=[{value:'',label:'—'},...unitGroups(data.units,data.blocks).map(g=>g.block?{optgroup:`${t('blk')} ${g.block}`,options:g.options}:g.options).flat()];
 return <FormModal open title={t('reportDefect')} onClose={onClose}
  initial={{title:'',description:'',category:'workmanship',severity:'major',unit_id:'',due_date:''}}
  fields={[{name:'title',label:t('defectTitle'),maxLength:150},{name:'description',label:t('description'),type:'textarea',wide:true,required:false},{name:'category',label:t('category'),options:DEFECT_CATS.map(c=>({value:c,label:t(c)}))},{name:'severity',label:t('severity'),options:DEFECT_SEVS.map(s=>({value:s,label:t(s)}))},{name:'unit_id',label:t('unit'),required:false,options},{name:'due_date',label:t('dueDate'),type:'date',required:false}]}
  onSubmit={v=>mutate('post',`/projects/${data.project.id}/defects`,{...v,unit_id:v.unit_id||null,due_date:v.due_date||null})}/>;
}
