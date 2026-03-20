import React, {useState, useRef, useEffect} from 'react';
import { Modal } from '@mui/material';
import axios from 'axios';
import {Box, TextField,IconButton} from '@mui/material';
import { IconEdit,IconTrash } from '@tabler/icons-react';
import Datatable from '../components/Datatable';
import Header from '../layout/header';
import { useSnackbar } from '../components/SnackbarContext';

function Role() {
    const style = {
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        bgcolor: 'background.paper',
        boxShadow: 24,
        borderRadius:1,
        p: 2,
    };
    const {showSnackbar} = useSnackbar(); 
    const formRef = useRef(null)
    const [rows, setRows] = useState([]);
    const [editId , setEditId] = useState("");
    const [isEdit, setIsEdit] = useState(false);
    const [open, setOpen] = useState(false);

    const handleOpen = () => {
        setOpen(true);
        setIsEdit(false);
    }
    
    const handleEdit = (row) => {
        setEditId(row._id);
        setOpen(true);
        setIsEdit(true);
        setTimeout(() => {
            formRef.current.role_name.value = row.role_name || "";
        }, 0);
    }
    const handleClose = () => {
        setOpen(false);
    }

    const handleSubmit = async(e) => {
        e.preventDefault()
        try{
            const date = new Date();
            const showDateTime = 
                    date.getDate() + '/' +
                    (date.getMonth() + 1) + '/' +
                    date.getFullYear() + ' ' + date.getHours() 
                    + ':' + date.getMinutes() 
                    + ":" + date.getSeconds();
            const user_name = localStorage.getItem("name");
            if(editId){
                const payload = {
                    _id:editId,
                    role_name:formRef.current.elements.namedItem("role_name").value,
                    created_at:showDateTime,
                    created_by:user_name,
                }
                const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/role-update`,payload)
                if(response.data.status == 200){
                    fetchData();
                    setOpen(false);
                    showSnackbar(response.data.message,"success");
                }else{
                    showSnackbar(response.data.message,"error");
                }
            }else{
                const payload = {
                    role_name:formRef.current.elements.namedItem("role_name").value,
                    updated_at:showDateTime,
                    updated_by:user_name,
                }
                const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/role-update`,payload)
                if(response.data.status == 200){
                    fetchData();
                    setOpen(false);
                    showSnackbar(response.data.message,"success");
                }else{
                    showSnackbar(response.data.message,"error");
                }
            }
            
        } catch(error){
            console.log(error);
        }
    }

    const data = rows?.map((row,index)=>{
        return{
            ...row,
            id:index + 1,
        }
    })

    const fetchData = async() => {
        try{
            const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/roles`)
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

    const columns = [
        { field:"id", headerName:"ID",width:80},
        { field: "role_name", headerName: "Role",width:1000},
        { field:"action", headerName:"Action",flex:1,renderCell:(params)=>{
            return(
                <div className="flex h-full items-center gap-3">
                    <IconButton size='small' color='primary' onClick={()=>handleEdit(params.row)}>
                        <IconEdit size={16} color='blue'/>
                    </IconButton>
                    <IconButton size='small' color='danger'>
                        <IconTrash size={16} color='red'/>
                    </IconButton>
                </div>
            )
        }}
    ];
    

    return (
        <>
            <Header/>
            <div className="main-container">
                <div className="flex justify-between items-start pt-3">
                    <div>
                        <span className='text-xl text-[#084b6f] font-bold'>Role Master</span>
                    </div>
                    <div>
                        <button onClick={handleOpen} className='bg-[#084b6f] text-white py-2 px-4 rounded-md text-sm cursor-pointer font-semibold'>Add New Role</button>
                        <Modal
                            open={open}
                            aria-labelledby="modal-modal-title"
                            aria-describedby="modal-modal-description"
                        >
                            <Box sx={style}>
                                <h1 className='font-semibold text-lg'>{isEdit?"Edit Role":"Add Role"}</h1>
                                <form ref={formRef} onSubmit={handleSubmit}>
                                    <div className='grid grid-cols-1 gap-4 mt-4'>
                                        <div className="col-span-1">
                                            <TextField name='role_name' label="Role name" size='small' fullWidth/>
                                        </div>
                                    </div>
                                    <div className="mt-4 flex gap-4 justify-center">
                                        <button type='button' className='bg-red-700 py-2 px-4 rounded-md text-sm cursor-pointer text-white' onClick={handleClose}>Cancel</button>
                                        <button type='submit' className='bg-[#084b6f] py-2 px-4 rounded-md text-sm cursor-pointer text-white'>Submit</button>
                                    </div>
                                </form>
                            </Box>
                        </Modal>
                    </div>
                </div>
                <div className="card mt-4">
                    <Datatable columns={columns} rows={data} height={510}/>
                </div>
            </div>
        </>
    )
}

export default Role
