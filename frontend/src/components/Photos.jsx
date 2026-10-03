import {useState,useEffect,useRef} from 'react';
import {Camera,ImagePlus,X,Trash2} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {api,errorText} from '../lib/api';
import {Action,Empty} from './Common';
import {toast} from 'sonner';

/** Camera-first photo upload. Posts multipart to /api/photos/upload. */
export function PhotoUpload({entityType,entityId,onUploaded,id}){
 const {t}=useLanguage();const [file,setFile]=useState(null),[preview,setPreview]=useState(''),[caption,setCaption]=useState(''),[busy,setBusy]=useState(false);
 const input=useRef();
 useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview);},[preview]);
 const pick=e=>{const f=e.target.files?.[0];if(!f)return;setFile(f);setPreview(URL.createObjectURL(f));};
 const upload=async()=>{
  if(!file||busy)return;setBusy(true);
  try{
   const form=new FormData();
   form.append('file',file);form.append('entity_type',entityType);form.append('entity_id',entityId);form.append('caption',caption);
   const {data}=await api.post('/photos/upload',form);
   setFile(null);setPreview('');setCaption('');if(input.current)input.current.value='';
   toast.success(t('saved'));onUploaded&&onUploaded(data);
  }catch(e){toast.error(errorText(e));}
  finally{setBusy(false);}
 };
 return <div className="photo-upload" data-testid={id||'photo-upload'}>
  <input ref={input} type="file" accept="image/*" capture="environment" className="hidden-file" data-testid="photo-file-input" onChange={pick}/>
  {!preview
   ?<button type="button" className="photo-pick" data-testid="photo-pick" onClick={()=>input.current.click()}><Camera size={18}/>{t('takePhoto')}</button>
   :<div className="photo-preview"><img src={preview} alt=""/><button type="button" className="icon-button photo-clear" data-testid="photo-clear" onClick={()=>{setFile(null);setPreview('');}}><X size={16}/></button></div>}
  {preview&&<>
   <input className="photo-caption" data-testid="photo-caption" placeholder={t('photoCaption')} value={caption} maxLength={200} onChange={e=>setCaption(e.target.value)}/>
   <Action id="photo-upload-submit" icon={ImagePlus} disabled={busy} onClick={upload}>{t(busy?'uploading':'addPhoto')}</Action>
  </>}
 </div>;
}

/** Thumbnail gallery with lightbox + optional delete. */
export function PhotoGallery({entityType,entityId,canDelete=false,refreshKey=0,id}){
 const {t}=useLanguage();const [photos,setPhotos]=useState([]),[lightbox,setLightbox]=useState(null);
 const load=()=>api.get('/photos',{params:{entity_type:entityType,entity_id:entityId}}).then(r=>setPhotos(r.data)).catch(()=>{});
 // eslint-disable-next-line react-hooks/exhaustive-deps
 useEffect(()=>{load();},[entityType,entityId,refreshKey]);
 const remove=async p=>{
  if(!window.confirm(t('confirmDelete')))return;
  try{await api.delete(`/photos/${p.id}`);load();toast.success(t('saved'));}
  catch(e){toast.error(errorText(e));}
 };
 if(!photos.length)return <Empty text={t('noRecords')}/>;
 return <div className="photo-gallery" data-testid={id||'photo-gallery'}>
  {photos.map(p=><div key={p.id} className="photo-thumb" data-testid={`photo-${p.id}`}>
   <button type="button" onClick={()=>setLightbox(p)}><img src={p.thumb_url||p.url} alt={p.caption||''} loading="lazy"/></button>
   {canDelete&&<button type="button" className="icon-button photo-delete" data-testid={`photo-delete-${p.id}`} onClick={()=>remove(p)}><Trash2 size={15}/></button>}
  </div>)}
  {lightbox&&<div className="lightbox" data-testid="photo-lightbox" onClick={()=>setLightbox(null)}>
   <img src={lightbox.url} alt={lightbox.caption||''}/>
   {lightbox.caption&&<p>{lightbox.caption}</p>}
   <button type="button" className="icon-button lightbox-close" onClick={()=>setLightbox(null)}><X size={20}/></button>
  </div>}
 </div>;
}
