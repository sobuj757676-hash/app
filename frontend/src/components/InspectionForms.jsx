import {useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Loader2,ClipboardCheck,Camera} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {FormModal,Field,TextLink} from './Common';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {useAuth,canDecideRto} from '../lib/auth';
import {today} from '../lib/api';
import {PhotoUpload,PhotoGallery} from './Photos';
import {toast} from 'sonner';

export const InspectionRequest=({unit,onClose})=>{
 const {t}=useLanguage();const {data,mutate}=useWorkspace();const navigate=useNavigate();
 const template=data.project.rto_checklist_template||[];
 const [values,setValues]=useState({inspector:'',date:today(),note:''});
 const [checks,setChecks]=useState(template.map(()=>false));
 const [busy,setBusy]=useState(false);
 const allChecked=checks.length>0&&checks.every(Boolean);
 const fields=[{name:'inspector',label:t('inspector')},{name:'date',label:t('date'),type:'date'},{name:'note',label:t('note'),type:'textarea',wide:true,required:false}];
 const submit=async e=>{
  e.preventDefault();if(!allChecked||busy)return;setBusy(true);
  try{
   await mutate('post',`/units/${unit.id}/inspections`,{...values,checklist:template.map((item,i)=>({item,checked:checks[i]}))});
   toast.success(t('saved'));onClose();
  }catch{/* toasted by mutate */}finally{setBusy(false);}
 };
 return <Dialog open onOpenChange={v=>!v&&onClose()}><DialogContent className="form-modal" data-testid="rto-request-modal"><DialogHeader><DialogTitle data-testid="form-modal-title">{t('requestRto')}</DialogTitle><DialogDescription className="sr-only">{t('requestRto')}</DialogDescription></DialogHeader>
 <form onSubmit={submit} data-testid="rto-request-form">
  <div className="form-fields">{fields.map(f=><label className={f.wide?'wide':''} key={f.name}>{f.label}<Field field={f} value={values[f.name]} onChange={value=>setValues(v=>({...v,[f.name]:value}))}/></label>)}</div>
  <div className="checklist-confirm" data-testid="rto-checklist"><h4><ClipboardCheck size={16}/>{t('rtoChecklist')}</h4>
   {template.length===0?<div className="checklist-empty" data-testid="rto-checklist-empty"><p className="form-hint">{t('rtoTemplateEmpty')}</p><TextLink id="rto-settings-link" onClick={()=>navigate('/settings/rto-checklist')}>{t('openRtoSettings')}</TextLink></div>:
   <>{template.map((item,i)=><label key={i} className="check-item" data-testid={`rto-check-${i}`}><input type="checkbox" checked={checks[i]} onChange={e=>{const n=[...checks];n[i]=e.target.checked;setChecks(n);}}/><span>{item}</span></label>)}
   {!allChecked&&<p className="form-hint" data-testid="rto-checklist-hint">{t('confirmAll')}</p>}</>}
  </div>
  <div className="form-footer"><Button type="button" variant="outline" data-testid="form-cancel" onClick={onClose}>{t('cancel')}</Button><Button type="submit" className="action" disabled={busy||!allChecked} data-testid="form-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('requestRto')}</Button></div>
 </form></DialogContent></Dialog>;
};

export const InspectionDecision=({inspection,onClose})=>{
 const {t}=useLanguage();const {mutate}=useWorkspace();const {user}=useAuth();const [photoTick,setPhotoTick]=useState(0);
 return <FormModal open onClose={onClose} title={`${t('reviewInspection')} · ${inspection.unit_label}`}
  initial={{inspector:inspection.inspector,result:'approved',note:''}}
  fields={[{name:'inspector',label:t('inspector')},{name:'result',label:t('result'),options:[{value:'approved',label:t('approve')},{value:'rework',label:t('requestRework')}]},{name:'note',label:t('inspectionNote'),type:'textarea',wide:true}]}
  onSubmit={v=>mutate('post',`/inspections/${inspection.id}/decision`,v)}>
  {(inspection.checklist?.length>0||inspection.requested_by)&&<div className="inspection-context" data-testid="inspection-context">
   {inspection.requested_by&&<p><strong>{t('requestedBy')}:</strong> {inspection.requested_by.name}</p>}
   {inspection.checklist?.length>0&&<><h4>{t('rtoChecklist')}</h4><ul>{inspection.checklist.map((c,i)=><li key={i} data-testid={`inspection-check-${i}`}><span className="check-done">✓</span>{c.item}<small>{c.checked_by?.name}</small></li>)}</ul></>}
  </div>}
  <div className="inspection-photos" data-testid="inspection-photos"><h4><Camera size={15}/>{t('photos')}</h4>
   <PhotoGallery entityType="inspection" entityId={inspection.id} refreshKey={photoTick} canDelete={canDecideRto(user)} id="inspection-photo-gallery"/>
   {canDecideRto(user)&&<PhotoUpload entityType="inspection" entityId={inspection.id} onUploaded={()=>setPhotoTick(k=>k+1)} id="inspection-photo-upload"/>}
  </div>
 </FormModal>;
};
