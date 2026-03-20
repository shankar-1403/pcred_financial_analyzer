import React, { useState, useEffect } from 'react';
import Header from '../layout/header';
import { useParams, useNavigate } from 'react-router-dom';
import Breadcrumbs from '../components/Breadcrumbs';
import {Box,Tabs,Tab, Modal, TextField, FormControl, InputLabel, MenuItem, Select} from '@mui/material';
import StepOne from './steps/StepOne';
import StepTwo from './steps/StepTwo';
import StepThree from './steps/StepThree';
import StepFour from './steps/StepFour';
import StepFive from './steps/StepFive';
import StepSix from './steps/StepSix';
import StepSeven from './steps/StepSeven';
import axios from 'axios';
import PropTypes from 'prop-types';
import { IconEdit,IconCirclePlus,IconTrash } from '@tabler/icons-react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import dayjs from 'dayjs';
import customParseFormat from "dayjs/plugin/customParseFormat";
import { Link } from 'react-router-dom';
import { useSnackbar } from '../components/SnackbarContext';

function CustomTabPanel(props) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

CustomTabPanel.propTypes = {
  children: PropTypes.node,
  index: PropTypes.number.isRequired,
  value: PropTypes.number.isRequired,
};

function a11yProps(index) {
  return {
    id: `simple-tab-${index}`,
    'aria-controls': `simple-tabpanel-${index}`,
  };
}

const style = {
  position: 'absolute',
  top: '50%',
  left: '50%',
  transform: 'translate(-50%, -50%)',
  bgcolor: 'background.paper',
  boxShadow: 24,
  p: 4,
};

dayjs.extend(customParseFormat);

function ReportView() {
    const {name,id} = useParams();
    const navigate = useNavigate();
    const { showSnackbar } = useSnackbar();
    const [reportData, setReportData] = useState({});
    const [loading, setLoading] = useState(true);
    const [btnLoading, setBtnLoading] = useState(false);
    const [formData, setFormData] = useState({ bank_name: "", acc_type: "", account_holder: "", account_number: "", analysis_from: null, analysis_to: null, statement_from: null, statement_to: null, account_opening_date: null, account_status: "", ifsc: "", micr: "", branch: "", branch_address: "", joint_holder: "", email_address: "", phone_no: "", pan: ""});
    const [open, setOpen] = useState(false);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const [rowId, setRowId] = useState("")
    const handleClose = () => setOpen(false);
    const handleDeleteClose = () => setDeleteOpen(false);
    const [value, setValue] = useState(0);
    
    const handleTabChange = (event, newValue) => {
        setValue(newValue);
    };
    const steps = ['Summary', 'Overview', 'Transactions','Irregularities','Monthly Counterparty','Counterparty','AML Analysis'];
    const stepComponents = [
        StepOne,
        StepTwo,
        StepThree,
        StepFour,
        StepFive,
        StepSix,
        StepSeven,
    ];

    const fetchData = async() => {
        if(!name) return;
        try{
            const payload = {
                report_name:name
            }
            const result = await axios.post(`${import.meta.env.VITE_API_URL}/api/report_view`,payload)
            if(result.data.status === 200){
                setReportData(result.data);
            }
        }catch(error){
            console.log(error)
        }finally{
            setLoading(false);
        }
    };

    useEffect(()=>{
        fetchData()
    },[])

    const accountDetails = reportData.account

    const handleChange = (e) => {
        const {name,value} = e.target;
        setFormData(prevFormData=>({
            ...prevFormData,
            [name]:value
        }));
    }

    const handleEdit = () => { 
        setOpen(true);
        setFormData({
            report_name:name,
            type:"account",
            bank_name: accountDetails?.bank_name || "",
            acc_type: accountDetails?.acc_type || "",
            account_holder: accountDetails?.account_holder || "",
            account_number: accountDetails?.account_number || "",
            analysis_from: accountDetails?.analysis_from ? dayjs(accountDetails.analysis_from, "DD/MM/YYYY") : null,
            analysis_to: accountDetails?.analysis_to ? dayjs(accountDetails.analysis_to, "DD/MM/YYYY") : null,
            statement_from: accountDetails?.statement_period?.from ? dayjs(accountDetails.statement_period.from, "DD/MM/YYYY") : null,
            statement_to: accountDetails?.statement_period?.to ? dayjs(accountDetails.statement_period.to, "DD/MM/YYYY") : null,
            account_opening_date: accountDetails?.account_opening_date ? dayjs(accountDetails.account_opening_date, "DD/MM/YYYY") : null,
            account_status: accountDetails?.account_status || "",
            ifsc: accountDetails?.ifsc || "",
            micr: accountDetails?.micr || "",
            branch: accountDetails?.branch || "",
            branch_address: accountDetails?.branch_address || "",
            joint_holder: accountDetails?.joint_holder || "",
            email_address: accountDetails?.email_address || "",
            phone_no: accountDetails?.phone_no || "",
            pan: accountDetails?.pan || ""
        });
    }

    const handleDeleteOpen = (id) => {
        setDeleteOpen(true);
        setRowId(id)
    }

    const handleDelete = async() => {
        try{
            const payload = {
                id:rowId,
                report_name:name,
            }
            const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/report-delete`,payload)
            if(response.data.status == 200){
                navigate('/reports');
                showSnackbar(response.data.message,"success");
            }else{
                showSnackbar(response.data.message,"error");
            }
        }catch(error){
            console.log(error)
        }finally{
            setDeleteOpen(false)
        }
    }

    const formSubmit = async(e) => {
        e.preventDefault();
        setBtnLoading(true);
        try{
            const payload = {
                ...formData,
                analysis_from: formData.analysis_from?.format("DD/MM/YYYY"),
                analysis_to: formData.analysis_to?.format("DD/MM/YYYY"),
                statement_from: formData.statement_from?.format("DD/MM/YYYY"),
                statement_to: formData.statement_to?.format("DD/MM/YYYY"),
                account_opening_date: formData.account_opening_date?.format("DD/MM/YYYY")
            };
            const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/reports/update-bank-details`,payload)
            if(response.data.status == 200){
                setOpen(false);
                fetchData();
                showSnackbar(response.data.message,"success")
            }else{
                showSnackbar(response.data.message,"error")
            }
        }catch(error){
            console.log(error)
        }finally{
            setBtnLoading(false);
        }
    }

    const list = [
        { label: "Reports", path: "/reports" },
        { label: name },
        { label: (accountDetails?.bank_name || " ") + " - " + (accountDetails?.account_number || " ") + " - " + (accountDetails?.acc_type || " ") },
    ]
    return (
        <>
            <Header/>
            <div className="main-container">
                <div className="pt-3">
                    <div className="flex justify-between">
                        <div>
                            <Breadcrumbs items={list}/>
                            <h1 className='text-2xl text-[#084b6f] font-bold'>{name}</h1>
                        </div>
                        <div className='flex gap-2 justify-end'>
                            <div>
                                <button onClick={() => handleDeleteOpen(id)} className='flex gap-2 items-center rounded-md text-sm cursor-pointer font-semibold py-2 px-3 border border-[#084b6f] text-[#084b6f] hover:text-red-600 hover:border-red-600'>
                                    Delete<IconTrash size={16}/>
                                </button>
                            </div>
                            <div>
                                <Link to={"/new-report"} className='flex gap-2 items-center text-white rounded-md text-sm cursor-pointer font-semibold py-2 px-3 border border-green-700 bg-green-700'>
                                    Add<IconCirclePlus size={16} color='white'/>
                                </Link>
                            </div>
                            <div>
                                <button onClick={handleEdit} className='flex gap-2 items-center text-white rounded-md text-sm cursor-pointer font-semibold py-2 px-3 border border-[#084b6f] bg-[#084b6f]'>
                                    Edit<IconEdit size={16} color='white'/>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                <div className='mt-4'>
                    {loading ? <div>Loading...</div>:
                        <Box sx={{ width: '100%' }}>
                            <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                                <Tabs value={value} onChange={handleTabChange} aria-label="basic tabs example">
                                    {steps.map((label,index) => (
                                        <Tab key={index} label={label} {...a11yProps(index)} sx={{fontSize:'12px',fontWeight:"bold"}}/>
                                    ))}
                                </Tabs>
                            </Box>
                            {stepComponents.map((StepComponent, index) => (
                                <CustomTabPanel key={index} value={value} index={index}>
                                    <StepComponent reportData={reportData} />
                                </CustomTabPanel>
                            ))}
                        </Box>
                    }
                </div>
            </div>
            <Modal
                open={open}
                onClose={handleClose}
                aria-labelledby="modal-modal-title"
                aria-describedby="modal-modal-description"
            >
                <Box sx={style}>
                    <p className='font-semibold text-xl'>{(accountDetails?.bank_name || " ") + " - " + (accountDetails?.account_number || " ") + " - " + (accountDetails?.acc_type || " ")}</p>
                    <form onSubmit={formSubmit}>
                        <div className="grid grid-cols-2 gap-4 mt-2">
                            <div className="col-span-1">
                                <TextField name='bank_name' label="Bank Name *" onChange={handleChange} value={formData.bank_name ?? ""} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <FormControl size='small' fullWidth>
                                    <InputLabel id="acc_type">Account Type *</InputLabel>
                                    <Select labelId="acc_type" id="acc_type" name='acc_type' label="Account Type *" onChange={handleChange} value={formData.acc_type ?? ""}>
                                        <MenuItem value='Savings'>Savings</MenuItem>
                                        <MenuItem value="Current">Current</MenuItem>
                                        <MenuItem value="Overdraft">Overdraft</MenuItem>
                                        <MenuItem value="Cash Credit">Cash Credit</MenuItem>
                                    </Select>
                                </FormControl>
                            </div>
                            <div className="col-span-1">
                                <TextField name='account_holder' label="Account holder *" value={formData.account_holder ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='account_number' label="Account Number *" value={formData.account_number ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                    <DatePicker 
                                        label="Analysis from" 
                                        name='analysis_from' 
                                        format="DD/MM/YYYY"
                                        value={formData.analysis_from}
                                        onChange={(newValue) => 
                                            setFormData((prev) => ({
                                                ...prev,
                                                analysis_from: newValue
                                            }))} 
                                        slotProps={{textField: {fullWidth: true,size:"small"}}}
                                    />
                                </LocalizationProvider>
                            </div>
                            <div className="col-span-1">
                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                    <DatePicker 
                                        label="Analysis to" 
                                        name='analysis_to' 
                                        format="DD/MM/YYYY"
                                        value={formData.analysis_to}
                                        onChange={(newValue) =>
                                            setFormData((prev) => ({
                                                ...prev,
                                                analysis_to: newValue
                                            }))
                                        } 
                                        slotProps={{textField: {fullWidth: true,size:"small"}}}
                                    />
                                </LocalizationProvider>
                            </div>
                            <div className="col-span-1">
                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                    <DatePicker 
                                        label="Statement start date" 
                                        name='statement_from' 
                                        value={formData.statement_from}
                                        onChange={(newValue) =>
                                            setFormData((prev) => ({
                                                ...prev,
                                                statement_from: newValue
                                            }))
                                        } 
                                        slotProps={{textField: {fullWidth: true,size:"small"}}}
                                    />
                                </LocalizationProvider>
                            </div>
                            <div className="col-span-1">
                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                    <DatePicker 
                                        label="Statement end date" 
                                        name='statement_to' 
                                        format="DD/MM/YYYY"
                                        value={formData.statement_to}
                                        onChange={(newValue) =>
                                            setFormData((prev) => ({
                                                ...prev,
                                                statement_to: newValue
                                            }))
                                        }
                                        slotProps={{textField: {fullWidth: true,size:"small"}}}
                                    />
                                </LocalizationProvider>
                            </div>
                            <div className="col-span-1">
                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                    <DatePicker 
                                        label="Account opening date" 
                                        name='account_opening_date' 
                                        format="DD/MM/YYYY"
                                        value={formData.account_opening_date}
                                        onChange={(newValue) =>
                                            setFormData((prev) => ({
                                                ...prev,
                                                account_opening_date: newValue
                                            }))
                                        }
                                        slotProps={{textField: {fullWidth: true,size:"small"}}}
                                    />
                                </LocalizationProvider>
                            </div>
                            <div className="col-span-1">
                                <TextField name='account_status' label="Account status" value={formData.account_status ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='ifsc' label="IFSC" value={formData.ifsc ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='micr' label="MICR" value={formData.micr ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='branch' label="Branch" value={formData.branch ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='branch_address' label="Branch address" value={formData.branch_address ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='joint_holder' label="Joint holder" value={formData.joint_holder ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='email_address' label="Email address" value={formData.email_address ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='phone_no' label="Phone no" value={formData.phone_no ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField name='pan' label="PAN" value={formData.pan ?? ""} onChange={handleChange} size='small' fullWidth/>
                            </div>
                        </div>
                        <div className="flex justify-center gap-4 mt-4">
                            <div>
                                <button type='button' onClick={handleClose} className='bg-red-700 py-2 px-4 rounded-md text-sm cursor-pointer text-white'>Cancel</button>
                            </div>
                            <div>
                                <button type='submit' className='bg-[#084b6f] py-2 px-4 rounded-md text-sm cursor-pointer text-white' disabled={btnLoading ? true : false}>{btnLoading ? "Submitting..." :"Submit"}</button>
                            </div>
                        </div>
                    </form>
                </Box>
            </Modal>
            <Modal
                open={deleteOpen}
                onClose={handleDeleteClose}
                aria-labelledby="modal-modal-title"
                aria-describedby="modal-modal-description"
            >
                <Box sx={style}>
                    <p className='text-2xl text-center font-semibold'>Delete Report</p>
                    <p className='text-lg'>Are you sure you want to delete the report?</p>
                    <div className="flex justify-center gap-4 mt-4">
                        <div>
                            <button onClick={handleDeleteClose} className='bg-red-700 py-2 px-4 rounded-md text-sm cursor-pointer text-white'>Cancel</button>
                        </div>
                        <div>
                            <button onClick={handleDelete} className='bg-[#084b6f] py-2 px-4 rounded-md text-sm cursor-pointer text-white'>Delete</button>
                        </div>
                    </div>
                </Box>
            </Modal>
        </>
    )
}

export default ReportView
