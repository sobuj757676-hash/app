import {BrowserRouter,Routes,Route,Navigate,useLocation} from 'react-router-dom';
import {LanguageProvider} from './lib/i18n';
import {AuthProvider,useAuth} from './lib/auth';
import {WorkspaceProvider} from './lib/store';
import {Toaster} from './components/ui/sonner';
import {Layout} from './components/Layout';
import {ForceChangePassword} from './pages/Login';
import Overview from './pages/Overview';
import WorkerHome from './pages/WorkerHome';
import UnitTracker from './pages/UnitTracker';
import Inspections from './pages/Inspections';
import Defects from './pages/Defects';
import Tasks from './pages/Tasks';
import Testing from './pages/Testing';
import Workforce from './pages/Workforce';
import Materials from './pages/Materials';
import Expenses from './pages/Expenses';
import Projects from './pages/Projects';
import Reports from './pages/Reports';
import References from './pages/References';
import Settings from './pages/Settings';
import Users from './pages/Users';
import Login from './pages/Login';
import './App.css';

function RequireAuth({children}){
 const {user,ready}=useAuth();const loc=useLocation();
 if(!ready)return <div className="loading-state" data-testid="auth-loading">…</div>;
 if(!user)return <Navigate to="/login" replace/>;
 if(user.must_change_password)return <div className="login-page"><ForceChangePassword onDone={()=>window.location.reload()}/></div>;
 const {role}=user,path=loc.pathname;
 if(role==='worker'&&!['/','/units','/defects','/tasks'].includes(path))return <Navigate to="/" replace/>;
 if(path==='/users'&&!['admin','manager'].includes(role))return <Navigate to="/" replace/>;
 if(path==='/expenses'&&role==='supervisor')return <Navigate to="/" replace/>;
 if(path==='/settings'&&role==='worker')return <Navigate to="/" replace/>;
 return children;
}
function Home(){
 const {user}=useAuth();
 return user?.role==='worker'?<WorkerHome/>:<Overview/>;
}
function Shell(){
 return <Routes>
  <Route path="/login" element={<Login/>}/>
  <Route element={<RequireAuth><Layout/></RequireAuth>}>
   <Route path="/" element={<Home/>}/>
   <Route path="/projects" element={<Projects/>}/>
   <Route path="/units" element={<UnitTracker/>}/>
   <Route path="/inspections" element={<Inspections/>}/>
   <Route path="/defects" element={<Defects/>}/>
   <Route path="/tasks" element={<Tasks/>}/>
   <Route path="/testing" element={<Testing/>}/>
   <Route path="/workforce" element={<Workforce/>}/>
   <Route path="/materials" element={<Materials/>}/>
   <Route path="/expenses" element={<Expenses/>}/>
   <Route path="/reports" element={<Reports/>}/>
   <Route path="/references" element={<References/>}/>
   <Route path="/settings" element={<Settings/>}/>
   <Route path="/users" element={<Users/>}/>
   <Route path="*" element={<Navigate to="/" replace/>}/>
  </Route>
 </Routes>;
}
function App(){return <LanguageProvider><AuthProvider><WorkspaceProvider><BrowserRouter><Shell/><Toaster richColors position="bottom-right"/></BrowserRouter></WorkspaceProvider></AuthProvider></LanguageProvider>;}export default App;
