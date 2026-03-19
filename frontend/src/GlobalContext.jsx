import React,{useState} from 'react'
import { GlobalContext } from './GlobalContext';

const GlobalContextProvider = ({ children }) => {
  const [reportName, setReportName] = useState({});

  return (
    <GlobalContext.Provider value={{ reportName, setReportName }}>
      {children}
    </GlobalContext.Provider>
  );
};

export default GlobalContextProvider