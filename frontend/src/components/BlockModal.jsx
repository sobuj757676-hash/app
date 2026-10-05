import {useState} from 'react';
import {Minus,Plus,Loader2} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {Input} from './ui/input';
import {useLanguage} from '../lib/i18n';
import {toast} from 'sonner';

export const ROOM_TYPES=['2-room','3-room','4-room','5-room','executive'];
export const POINT_KINDS=['power','light','socket','switch','aircon','heater','fan','data'];

export function Stepper({value,onChange,testid,max=30}){
 const {t}=useLanguage();
 const set=v=>onChange(Math.max(0,Math.min(max,v)));
 return <div className="stepper" data-testid={testid}>
  <button type="button" className="icon-button" data-testid={`${testid}-minus`} disabled={value<=0} onClick={()=>set(value-1)} aria-label={t('decrease')}><Minus size={16}/></button>
  <span className="stepper-value" data-testid={`${testid}-value`}>{value}</span>
  <button type="button" className="icon-button" data-testid={`${testid}-plus`} disabled={value>=max} onClick={()=>set(value+1)} aria-label={t('increase')}><Plus size={16}/></button>
 </div>;
}

export function BlockModal({open,onClose,onSubmit}){
 const {t}=useLanguage();
 const [name,setName]=useState(''),[levels,setLevels]=useState(10),[firstUnit,setFirstUnit]=useState(401),[busy,setBusy]=useState(false);
 const [mix,setMix]=useState({'4-room':8,'2-room':0,'3-room':0,'5-room':0,'executive':0});
 const total=ROOM_TYPES.reduce((s,rt)=>s+(mix[rt]||0),0);
 const save=async e=>{
  e.preventDefault();if(busy||!total)return;setBusy(true);
  try{
   await onSubmit({name,levels:Number(levels)||1,first_unit:Number(firstUnit)||401,
    units_per_level:total,
    room_mix:ROOM_TYPES.filter(rt=>mix[rt]>0).map(rt=>({room_type:rt,count:mix[rt]}))});
   toast.success(t('saved'));onClose();
  }catch{}finally{setBusy(false);}
 };
 return <Dialog open={open} onOpenChange={v=>!v&&onClose()}>
  <DialogContent className="form-modal" data-testid="block-modal">
   <DialogHeader><DialogTitle data-testid="block-modal-title">{t('addBlock')}</DialogTitle><DialogDescription className="sr-only">{t('addBlock')}</DialogDescription></DialogHeader>
   <form onSubmit={save} data-testid="block-modal-form">
    <div className="form-fields">
     <label className="wide">{t('block')}<Input data-testid="block-field-name" value={name} onChange={e=>setName(e.target.value)} required maxLength={16} placeholder="40A"/></label>
     <label>{t('numberOfLevels')}<Input data-testid="block-field-levels" type="number" min={1} max={60} value={levels} onChange={e=>setLevels(e.target.value)}/></label>
     <label>{t('firstUnit')}<Input data-testid="block-field-first-unit" type="number" min={1} max={9999} value={firstUnit} onChange={e=>setFirstUnit(e.target.value)}/></label>
    </div>
    <div className="drawer-section" data-testid="block-room-mix">
     <h3>{t('roomMix')}</h3>
     <p className="section-sub">{t('roomMixSub')}</p>
     {ROOM_TYPES.map(rt=><div key={rt} className="mix-row" data-testid={`mix-row-${rt}`}>
      <span className="mix-label">{t(rt)}</span>
      <Stepper value={mix[rt]||0} onChange={v=>setMix(m=>({...m,[rt]:v}))} testid={`mix-${rt}`}/>
     </div>)}
     <div className="mix-total" data-testid="mix-total"><strong>{total}</strong> {t('totalUnitsPerLevel')}</div>
     {(!total||!name.trim())&&<p className="form-hint" data-testid="block-save-hint">{t('blockSaveHint')}</p>}
    </div>
    <div className="form-footer">
     <Button type="button" variant="outline" data-testid="block-cancel" onClick={onClose}>{t('cancel')}</Button>
     <Button type="submit" className="action" disabled={busy||!total||!name.trim()} data-testid="block-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('save')}</Button>
    </div>
   </form>
  </DialogContent>
 </Dialog>;
}
