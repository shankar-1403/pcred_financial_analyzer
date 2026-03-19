import React,{useState, useEffect, useRef} from 'react';
import Header from '../layout/header';
import { Link } from 'react-router-dom';
import Datatable from '../components/Datatable';
import axios from 'axios';
import { IconButton } from '@mui/material';
import { IconEdit,IconTrash } from '@tabler/icons-react';
import {Modal, Box, TextField, FormControl, InputLabel, Select, MenuItem} from '@mui/material';

function Users() {
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
    const formRef = useRef(null)
    const [rows, setRows] = useState([]);
    const [editId , setEditId] = useState("");
    const [isEdit, setIsEdit] = useState(false);
    const [open, setOpen] = useState(false);
    const [roleValue, setRoleValue] = useState("");
    const [statusValue, setStatusValue] = useState("");
    const fetchData = async() => {
        try{
           const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/users`)
           setRows(response.data?.result)
        } catch(error){
            console.log(error)
        } finally{
            // 
        }
    }

    const handleOpen = () => {
        setOpen(true);
        setIsEdit(false);
    }
    
    const handleEdit = (row) => {
        setEditId(row._id);
        setOpen(true);
        setIsEdit(true);
        setTimeout(() => {
            formRef.current.full_name.value = row.full_name || "";
            formRef.current.email_id.value = row.email_id || "";
            setRoleValue(row.role || "");
            setStatusValue(row.status || "");
        }, 0);
    }
    const handleClose = () => {
        setOpen(false);
        setRoleValue("")
        setStatusValue("")
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
                    full_name:formRef.current.elements.namedItem("full_name").value,
                    email_id:formRef.current.elements.namedItem("email_id").value,
                    role:formRef.current.elements.namedItem("role").value,
                    status:formRef.current.elements.namedItem("status").value,
                    created_at:showDateTime,
                    created_by:user_name,
                }
                const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/users-update`,payload)
                if(response.data.status == 200){
                    console.log(response.data.message);
                    setRoleValue("")
                    setStatusValue("")
                    fetchData();
                    setOpen(false);
                }else{
                    console.log(response.data.message)
                }
            }else{
                const payload = {
                    full_name:formRef.current.elements.namedItem("full_name").value,
                    email_id:formRef.current.elements.namedItem("email_id").value,
                    role:roleValue,
                    status:statusValue,
                    updated_at:showDateTime,
                    updated_by:user_name,
                }
                const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/users-update`,payload)
                if(response.data.status == 200){
                    console.log(response.data.message);
                    setRoleValue("")
                    setStatusValue("")
                    fetchData();
                    setOpen(false);
                }else{
                    console.log(response.data.message)
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

    useEffect(()=>{
        fetchData()
    },[])

    const columns = [
        { field:"id", headerName:"ID",width:80},
        { field: "full_name", headerName: "Name", renderCell:(params) => {
            return(
                <Link to={`/report/${params.row.report_name}/${params.row._id}`} className='underline text-blue-500'>{params.value}</Link>
            )
        }, width:300},
        { field: "email_id", headerName: "Email ID", width:300},
        { field: "role", headerName: "Role", width:250,renderCell:(params) => {
            return(
                <><span className='capitalize'>{params.row.role}</span></>
            )
        }},
        { field: "status", headerName: "Status",renderCell:(params) => {
            return(
                <><span className='capitalize'>{params.row.status}</span></>
            )
        },width:250},
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
                <div className="flex justify-between items-start pt-6">
                    <div>
                        <span className='text-xl text-[#084b6f] font-bold'>Manage Users</span>
                    </div>
                    <div>
                        <button onClick={handleOpen} className='bg-[#084b6f] text-white py-2 px-4 rounded-md text-sm cursor-pointer font-semibold'>Add New User</button>
                        <Modal
                            open={open}
                            aria-labelledby="modal-modal-title"
                            aria-describedby="modal-modal-description"
                        >
                            <Box sx={style}>
                                <h1 className='font-semibold text-lg'>{isEdit?"Edit User":"Add User"}</h1>
                                <form ref={formRef} onSubmit={handleSubmit}>
                                    <div className='grid grid-cols-2 gap-4 mt-4'>
                                        <div className="col-span-1">
                                            <TextField name='full_name' label="Name" size='small' fullWidth/>
                                        </div>
                                        <div className="col-span-1">
                                            <TextField name='email_id' label="Email Id" size='small' fullWidth/>
                                        </div>
                                        <div className="col-span-1">
                                            <FormControl size='small' fullWidth>
                                                <InputLabel id="role">Role</InputLabel>
                                                <Select labelId="role" onChange={(e) => setRoleValue(e.target.value)} value={roleValue} id="role" name='role' label="Role">
                                                    <MenuItem value='admin'>Admin</MenuItem>
                                                    <MenuItem value="users">Users</MenuItem>
                                                </Select>
                                            </FormControl>
                                        </div>
                                        <div className="col-span-1">
                                            <FormControl size='small' fullWidth>
                                                <InputLabel id="status">Status</InputLabel>
                                                <Select labelId="status" onChange={(e) => setStatusValue(e.target.value)} value={statusValue} id="status" name='status' label="Status">
                                                    <MenuItem value='active'>Active</MenuItem>
                                                    <MenuItem value="inactive">Inactive</MenuItem>
                                                </Select>
                                            </FormControl>
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

export default Users