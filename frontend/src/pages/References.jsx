import {useState} from 'react';
import {Files,Maximize2,ArrowUpRight,Image} from 'lucide-react';
import {Dialog,DialogContent,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {useLanguage} from '../lib/i18n';
import {PageTitle} from '../components/Common';

const photos=[['site-board-5.webp','ref0'],['site-board-4.webp','ref1'],['site-board-3.webp','ref2'],['site-board-2.webp','ref3'],['site-reference.webp','ref4']];

export default function References(){
 const {t}=useLanguage();
 const [photo,setPhoto]=useState(null);
 return <div className="page-enter">
  <PageTitle title={t('references')} subtitle={t('referencesSub')}/>
  <div className="reference-info" data-testid="reference-source-note">
   <Files size={19}/><div><b>{t('source')}</b><p>{t('sampleNote')}</p></div><span>5 WEBP</span>
  </div>
  <div className="reference-grid">
   {photos.map(([src,title],i)=><button className="reference-card" data-testid={`reference-photo-${i}`} key={src} onClick={()=>setPhoto([src,title])}>
    <div className="reference-photo"><img src={`/images/${src}`} alt={t(title)} loading="lazy"/><span><Maximize2 size={17}/></span></div>
    <div className="reference-caption"><Image size={16}/><h2 data-testid={`reference-caption-${i}`}>{t(title)}</h2><ArrowUpRight size={16}/></div>
   </button>)}
  </div>
  {photo&&<Dialog open onOpenChange={v=>!v&&setPhoto(null)}>
   <DialogContent className="reference-modal" data-testid="reference-modal">
    <DialogTitle data-testid="reference-modal-title">{t(photo[1])}</DialogTitle>
    <DialogDescription className="sr-only">{t('source')}</DialogDescription>
    <img src={`/images/${photo[0]}`} alt={t(photo[1])}/>
    <a data-testid="reference-original-link" href={`/images/${photo[0]}`} target="_blank" rel="noreferrer" className="text-link">{t('source')}<ArrowUpRight size={15}/></a>
   </DialogContent>
  </Dialog>}
 </div>;
}