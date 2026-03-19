import React,{useState,useEffect} from 'react';
import axios from 'axios';
import Header from '../layout/header';
import Datatable from '../components/Datatable';
import Chip from '@mui/material/Chip';
import { Link } from 'react-router-dom';

function Report() {
    const [rows, setRows] = useState([])
    const fetchData = async() => {
        try{
           const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/reports`)
           setRows(response.data?.result)
        } catch(error){
            console.log(error)
        } finally{
            // 
        }
    }

    useEffect(()=>{
        fetchData()
    },[])

    const data = rows?.map((row,index)=>{
        return{
            ...row,
            id:index + 1,
        }
    })

    const columns = [
        { field:"id", headerName:"ID",width:80},
        { field: "report_name", headerName: "Name", width:250, renderCell:(params) => {
            return(
                params.row.status == "active" ? 
                    <Link to={`/report/${params.row.report_name}/${params.row._id}`} className='underline text-blue-500'>{params.value}</Link>
                    :
                    <span>{params.value}</span>
                
            )
        }},
        { field: "reference_id", headerName: "Reference ID",width:200 },
        { field: "status", headerName: "Status",width:250 , renderCell:(params) => {
            let color;
            let text;
            if (params.value === "active") {
                color = "success";
                text = "Active"
            }else if(params.value === "deleted"){
                color = "disabled";
                text = params.value
            }
            return (
                <div className="flex items-center h-full">
                    <Chip label={params.value ? text : params.value} color={color} size="small" style={{fontSize:"12px",textTransform:"capitalize"}} variant="contained"/>
                </div>
            );
        }},
        { field: "active", headerName: "Active days",width:180},
        { field: "created_at", headerName: "Created on",flex:1},
        { field: "created_by", headerName: "Created by",flex:1},
    ];

    return (
        <>
            <Header/>
            <div className="main-container">
                <div className="flex justify-between items-start pt-3">
                    <div>
                        <span className='text-xl text-[#084b6f] font-bold'>Reports</span>
                    </div>
                    <div>
                        <Link to={"/new-report"} className='bg-[#084b6f] text-white py-2 px-4 rounded-md text-sm cursor-pointer font-semibold'>Add New Report</Link>
                    </div>
                </div>
                <div className="card mt-4">
                    <Datatable columns={columns} rows={data} height={510}/>
                </div>
            </div>
        </>
    )
}

export default Report
