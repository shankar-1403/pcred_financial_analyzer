import React,{useEffect,useState} from 'react';
import axios from 'axios';
import Header from '../layout/header';
import { Link } from 'react-router-dom';
import { IconListCheck } from '@tabler/icons-react';
import { IconList } from '@tabler/icons-react';

function Dashboard() {
  const comapany_name = localStorage.getItem("name")
  const [reports, setReports] = useState([])
  const fetchReports = async() => {
    try{
      const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/reports`)
      if(response.data.status == 200){
        setReports(response.data?.result);
      }
    } catch(error){
      console.log(error);
    } finally {
      // console.log(object)
    }
  }

  const reportStart = reports.slice(0, 3);

  const activeReports = reports.filter((item) => {
    return item.status === "active"
  })

  const inactiveReports = reports.filter((item) => {
    return item.status === "deleted"
  })

  useEffect(() => {
    fetchReports();
  },[])
  return (
    <>
      <Header/> 
      <div className="main-container">
        <div className="flex pt-2 mb-4">
          <div>
            <p className='text-2xl text-[#084b6f] font-semibold'>{comapany_name}</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="col-span-1">
            <div className="card h-full">
              <div className="flex w-full justify-between items-center">
                <div className='flex flex-col'>
                  <p className='font-semibold text-gray-600'>Active Reports</p>
                  <p className='text-3xl font-semibold text-[#084b6f]'>{activeReports.length || 0}</p>
                </div>
                <div>
                  <div className='bg-[#E18126] rounded-full p-2'>
                    <IconListCheck size={36} color='white'/>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="col-span-1">
            <div className="card h-full">
              <div className="flex w-full justify-between items-center">
                <div className='flex flex-col'>
                  <p className='font-semibold text-gray-600'>Inactive Reports</p>
                  <p className='text-3xl font-semibold text-[#084b6f]'>{inactiveReports.length || 0}</p>
                </div>
                <div>
                  <div className='bg-[#E18126] rounded-full p-2'>
                    <IconList size={36} color='white'/>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div className="col-span-2">
            <div className="card">
              <h1 className='text-xl mb-2 text-[#084b6f] font-semibold'>Recently Used</h1>
              <table className='w-full'>
                <thead>
                  <tr className='border-t border-b border-gray-200 bg-gray-100'>
                    <th className="px-3 py-2 font-medium text-[14px] text-left">Report Name</th>
                    <th className="px-3 py-2 font-medium text-[14px] text-left">Status</th>
                    <th className="px-3 py-2 font-medium text-[14px] text-left">Remaining Days</th>
                  </tr>
                </thead>
                <tbody>
                  {reportStart.map((item,index)=>(
                    <tr key={index}>
                      <td className="px-3 py-1 text-[14px] -left-px sticky bg-white z-10 border-b border-gray-200">
                        <Link to={`/report/${item.report_name}/${item._id}`} className='text-blue-600 underline font-semibold'>{item.report_name}</Link>
                      </td>
                      <td className="px-3 py-1 -left-px sticky bg-white z-10 border-b border-gray-200 capitalize">
                        <span className={item.status === "active" ? "bg-green-600 text-white text-[12px] px-3 py-0.5 rounded-xl" : "bg-yellow-500 text-white text-[12px] px-3 py-0.5 rounded-xl"}>
                          {item.status}
                        </span>
                      </td>
                      <td className="px-3 py-1 text-[14px] -left-px sticky bg-white z-10 border-b border-gray-200">{item.active}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="flex justify-end">
                  <Link to={'/reports'} className='underline text-sm font-semibold text-blue-500'>View all</Link>
              </div>
            </div>
          </div>
          <div className="col-span-1"></div>
        </div>
      </div>
    </>
  )
}

export default Dashboard