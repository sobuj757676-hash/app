import {useState} from 'react';
import {Plus,Download,ArrowUpRight,Loader2} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {Input} from './ui/input';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {download,errorText} from '../lib/api';
import {toast} from 'sonner';

export const Action=({children,onClick,secondary=false,icon:Icon=Plus,id,disabled=false,type='button'})=><Button type={type} data-testid={id} disabled={disabled} className={`action ${secondary?'secondary':''}`} onClick={onClick}><Icon size={16}/>{children}</Button>;
export const ExportButton=({kind='units'})=>{const {pid}=useWorkspace();const {t}=useLanguage();const [busy,setBusy]=useState(false);return <Action id={`export-${kind}`} secondary icon={busy?Loader2:Download} disabled={busy} onClick={async()=>{setBusy(true);try{await download(pid,kind);}catch(e){toast.error(errorText(e));}finally{setBusy(false);}}}>{t('export')}</Action>;};
export const PageTitle=({title,subtitle,children})=><div className="page-title"><div><h1 data-testid="page-title">{title}</h1>{subtitle&&<p data-testid="page-subtitle">{subtitle}</p>}</div><div className="title-actions">{children}</div></div>;
export const SectionTitle=({title,sub,children})=><div className="section-title"><div><h2 data-testid={`section-${String(title).replace(/\s/g,'-')}`}>{title}</h2>{sub&&<p>{sub}</p>}</div>{children}</div>;
export const StatusBadge=({value,id})=>{const {t}=useLanguage();return <span data-testid={id} className={`status-badge ${value}`}><i/>{t(value)}</span>;};
export const ProgressBar=({value,id})=><div className="progress-track" data-testid={id} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{width:`${Math.min(100,value)}%`}}/></div>;
export const Metric=({title,value,sub,icon:Icon,tone='blue',id,children})=><article className="metric" data-testid={id}><div className="metric-top"><span>{title}</span><span className={`metric-icon ${tone}`}><Icon size={19}/></span></div><div className="metric-value">{value}{children}</div><div className="metric-sub">{sub}</div></article>;
export const Empty=({text})=><div className="empty" data-testid="empty-state">{text}</div>;
export const TextLink=({children,onClick,id})=><button className="text-link" onClick={onClick} data-testid={id}>{children}<ArrowUpRight size={15}/></button>;

export function FormModal({open,onClose,title,fields,initial={},onSubmit,submitLabel}) {
 const {t}=useLanguage();const [values,setValues]=useState(initial),[busy,setBusy]=useState(false);
 return <Dialog open={open} onOpenChange={v=>!v&&onClose()}><DialogContent className="form-modal" data-testid="form-modal"><DialogHeader><DialogTitle data-testid="form-modal-title">{title}</DialogTitle><DialogDescription className="sr-only">{title}</DialogDescription></DialogHeader><form onSubmit={async e=>{e.preventDefault();setBusy(true);try{await onSubmit(values);toast.success(t('saved'));onClose();}catch{}finally{setBusy(false);}}} data-testid="modal-form"><div className="form-fields">{fields.map(f=><label className={f.wide?'wide':''} key={f.name}>{f.label}<Field field={f} value={values[f.name]??f.default??''} onChange={value=>setValues(v=>({...v,[f.name]:value}))}/></label>)}</div><div className="form-footer"><Button type="button" variant="outline" data-testid="form-cancel" onClick={onClose}>{t('cancel')}</Button><Button type="submit" className="action" disabled={busy} data-testid="form-submit">{busy&&<Loader2 className="spin" size={15}/>} {submitLabel||t('save')}</Button></div></form></DialogContent></Dialog>;
}
export function Field({field:f,value,onChange}) {const props={'data-testid':`field-${f.name}`,id:`field-${f.name}`,required:f.required!==false,disabled:f.disabled,value,onChange:e=>onChange(f.type==='number'?(e.target.value===''?'':Number(e.target.value)):e.target.value)};if(f.options)return <select {...props}>{!value&&<option value="">—</option>}{f.options.map(o=><option key={typeof o==='string'?o:o.value} value={typeof o==='string'?o:o.value}>{typeof o==='string'?o:o.label}</option>)}</select>;if(f.type==='textarea')return <textarea {...props} rows={3} maxLength={2000}/>;return <Input {...props} type={f.type||'text'} min={f.min} max={f.max} step={f.step||'any'} maxLength={f.maxLength||200} placeholder={f.placeholder||''}/>;}