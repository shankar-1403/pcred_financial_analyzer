import { BrowserRouter,Routes,Route } from 'react-router-dom';
import Login from './login/Login';
import Dashboard from './dashboard/Dashboard';
import Report from './reports/Report';
import NewReport from './reports/NewReport';
import ReportView from './reports/ReportView';
import Users from './masters/Users';
import PrivateRoute from './PrivateRoute';
import PublicRoute from './PublicRoute';
import './App.css'

function App() {
  return (
    <>
      <BrowserRouter>
        <Routes>
          <Route path='/' element={<PublicRoute><Login/></PublicRoute>}/>
          <Route path='/dashboard' element={<PrivateRoute><Dashboard/></PrivateRoute>}/>
          <Route path='/reports' element={<PrivateRoute><Report/></PrivateRoute>}/>
          <Route path='/manage-users' element={<PrivateRoute><Users/></PrivateRoute>}/>
          <Route path='/new-report' element={<PrivateRoute><NewReport/></PrivateRoute>}/>
          <Route path='/report/:name/:id' element={<PrivateRoute><ReportView/></PrivateRoute>}/>
        </Routes>
      </BrowserRouter>
    </>
  )
}

export default App