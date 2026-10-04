import {Check} from 'lucide-react';
import {useLanguage} from '../../lib/i18n';
import {useWorkspace} from '../../lib/store';
import {SubHeader} from './shared';

export default function LanguageSettings(){
 const {lang,setLang}=useLanguage();const {data}=useWorkspace();
 return <div className="page-enter">
  <SubHeader title="Language / ভাষা / 语言" subtitle={data.project.name}/>
  <div className="language-options">{[['en','English','English'],['bn','বাংলা','Bangla'],['zh','中文','Chinese']].map(([code,name,sub])=><button data-testid={`settings-language-${code}`} key={code} className={lang===code?'active':''} onClick={()=>setLang(code)}><div><b>{name}</b><span>{sub}</span></div>{lang===code&&<Check size={18}/>}</button>)}</div>
 </div>;
}
