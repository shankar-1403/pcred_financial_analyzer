import React, { useState, useRef } from 'react';
import Header from '../layout/header';
import axios from 'axios';
import Breadcrumbs from '../components/Breadcrumbs';
import {TextField,FormControl,Select,MenuItem, InputLabel,Modal, Box,CircularProgress } from '@mui/material';
import { IconChevronDown,IconCirclePlus, IconTrash } from '@tabler/icons-react';
import { motion as Motion,AnimatePresence } from 'motion/react';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { useNavigate } from 'react-router-dom';
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf";
import { useSnackbar } from '../components/SnackbarContext';
import pdfWorker from "pdfjs-dist/legacy/build/pdf.worker?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker;

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

function NewReport() {
    const formRef = useRef(null);
    const { showSnackbar } = useSnackbar()
    const navigate = useNavigate();
    const [selectedFile, setSelectedFile] = useState(null)
    const [open, setOpen] = useState(false);
    const [password, setPassword] = useState("");
    const [showModal, setShowModal] = useState(false);
    const [needsPassword, setNeedsPassword] = useState(false);
    const [accordion, setAccordion] = useState([{ id: 1, open: true }]);
    const [loading, setLoading] = useState(false);
    const [fileName, setFileName] = useState("")

    const handleFileChange = (e) => {
        const file = e.target.files[0];
        if (file) {
            setFileName(file.name);
        }
        setSelectedFile(file);
        const fileReader = new FileReader();
        fileReader.onload = async function () {
        const typedArray = new Uint8Array(this.result);

        try {
            await pdfjsLib.getDocument({ data: typedArray }).promise;
            setNeedsPassword(false);
        } catch (err) {
            if (err.name === "PasswordException") {
                setNeedsPassword(true);
                setShowModal(true);
            }
        }
        };

        fileReader.readAsArrayBuffer(file);
    };

    const handleChange = (id,e) => {
        const {name, value} = e.target;
        setAccordion(prev =>
            prev.map(acc => {
                if (acc.id === id) {
                    return {
                    ...acc,
                    [name]: value,
                    isDate: value === "from_to_date",
                    isMonths: value === "statement_transaction"
                    };
                }
                return acc;
            })
        );
    }

    const handleToggle = (id) => {
        setAccordion(prev =>
            prev.map(acc =>
            acc.id === id ? { ...acc, open: !acc.open } : acc
            )
        );
    };

    const handleDelete = (id) => {
        setAccordion(prev =>
            prev.map(acc =>
            acc.id === id ? { ...acc, open: !acc.open } : acc
            )
        );
    };

    const handleNewAccordion = () => {
        setAccordion(prev => [
            ...prev,
            {
                id: Date.now(),
                open: true,
                pre_analysis_check: "",
                isDate: false,
                isMonths: false
            }
        ]);
    }

    const handleSubmit = async(e) => {
        e.preventDefault();
        setLoading(true);
        setOpen(true);
        if (needsPassword && !password) {
            setShowModal(true);
            return;
        }
        try{
            const user_name = localStorage.getItem("name")
            const formData = new FormData();
            formData.append("report_name",formRef.current.elements.namedItem("report_name").value);
            formData.append("reference_id",formRef.current.elements.namedItem("reference_id").value);
            formData.append("status", "active");
            formData.append("password", password);
            formData.append("created_by", user_name);

            formData.append("file",selectedFile);

            const response = await axios.post(`${import.meta.env.VITE_API_URL}/api/reports/create-new`,formData)
            if(response.data.status == 200){
                navigate("/reports");
                showSnackbar(response.data.message,"success");
            }else{
                showSnackbar(response.data.message,"error");
            }
        }catch(error){
            console.log(error);
        } finally{
            setLoading(false);
            setOpen(false);
        }
    }

    const handlePasswordSubmit = () => {
        setShowModal(false);
    };

    const list = [
        { label: "Reports", path: "/reports" },
        { label: "New Report" }
    ]
    return (
        <>
            <Header/>
            <div className="main-container">
                <div className="pt-3">
                    <Breadcrumbs items={list}/>
                    <h1 className='text-2xl text-[#084b6f] font-bold'>New Report</h1>
                </div>
                <div className="card mt-4">
                    <div className='border-b border-[#084B6f] pb-4'>
                        <h2 className='text-lg font-semibold text-[#084b6f]'>Report Details</h2>
                    </div>
                    <form ref={formRef} onSubmit={handleSubmit}>
                        <div className="grid grid-cols-3 gap-4 my-4">
                            <div className="col-span-1">
                                <TextField label="Report Name *" name='report_name' size='small' fullWidth/>
                            </div>
                            <div className="col-span-1">
                                <TextField label="Reference ID" name='reference_id' size='small' fullWidth/>
                            </div>
                        </div>
                        <div className="flex justify-end pb-2">
                            <button onClick={handleNewAccordion} type='button' className='text-base text-[#084b6f] flex items-center gap-2 cursor-pointer'><IconCirclePlus size={18}/>Add Bank Account</button>
                        </div>
                        {accordion.map((acc)=> ( 
                            <div key={acc.id} className="mb-2">
                                <div className={`bg-[#084b6f] px-4 py-4 rounded-tl-sm rounded-tr-sm flex justify-between items-center ${ acc.open == false ? "rounded-br-sm rounded-bl-sm" : ""}`}>
                                    <div>
                                        <h2 className='text-base font-semibold text-white'>Bank Account</h2>
                                    </div>
                                    <div className='flex gap-4'>
                                        <div>
                                            <button type='button' onClick={() => handleDelete(acc.id)} className='hover:bg-gray-300/30 rounded-full cursor-pointer p-0.5'><IconTrash color='white' size={20}/></button>
                                        </div>
                                        <div>
                                            <button type='button' onClick={() => handleToggle(acc.id)} className='hover:bg-gray-300/30 rounded-full cursor-pointer p-0.5'><IconChevronDown color='white' size={20} className={`transition-transform duration-300 ${ acc.open ? "rotate-180" : ""}`}/></button>
                                        </div>
                                    </div>
                                </div>
                                <AnimatePresence initial={false}>
                                    {acc.open && (
                                        <Motion.div
                                            key="accordion-wrapper"
                                            initial={{  height: 0 }}
                                            animate={{  height: "auto" }}
                                            exit={{  height: 0 }}
                                            transition={{ duration: 0.35, ease: "easeInOut" }}
                                            className="overflow-hidden rounded-bl-sm rounded-br-sm border-x border-b border-gray-500"
                                        >
                                            <div className='p-4'>
                                                <div className="grid grid-cols-4 gap-4 mb-4">
                                                    <div className="cols-span-1">
                                                        <FormControl size='small' fullWidth>
                                                            <InputLabel id="pre_analysis_check">Pre-analysis check *</InputLabel>
                                                            <Select
                                                                labelId="pre_analysis_check"
                                                                id="pre_analysis_check"
                                                                name='pre_analysis_check'
                                                                label="Pre-analysis check *"
                                                                value={acc.pre_analysis_check}
                                                                onChange={(e)=>handleChange(acc.id,e)}
                                                            >
                                                                <MenuItem value='not_required'>Not required</MenuItem>
                                                                <MenuItem value="from_to_date">From - To Date</MenuItem>
                                                                <MenuItem value="statement_transaction">Statement contains transaction</MenuItem>
                                                            </Select>
                                                        </FormControl>
                                                    </div>
                                                    {acc.isDate ? 
                                                        <>
                                                            <div className="col-span-1">
                                                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                                                    <DatePicker label="From Date *" slotProps={{textField: {fullWidth: true,size:"small"}}}/>
                                                                </LocalizationProvider>
                                                            </div>
                                                            <div className="col-span-1">
                                                                <LocalizationProvider dateAdapter={AdapterDayjs}>
                                                                    <DatePicker label="To Date *" slotProps={{textField: {fullWidth: true,size:"small"}}}/>
                                                                </LocalizationProvider>
                                                            </div>
                                                        </>
                                                        :
                                                        null
                                                    }
                                                    {acc.isMonths ? 
                                                        <div className="col-span-1">
                                                            <TextField label="No of months *" type='number' size='small' fullWidth/>
                                                        </div>
                                                        : null
                                                    }
                                                </div>
                                                <h3 className='text-base font-semibold text-[#084b6f]'>Upload Bank Statements</h3>
                                                <div className='grid grid-cols-3 mt-2'>
                                                    <div className="col-span-1">
                                                        <label className="cursor-pointer inline-block w-full">
                                                            <input type="file" name='financial_statement' accept="application/pdf" onChange={handleFileChange} className="hidden"/>
                                                            <div className="px-20 py-12 border-2 border-dashed border-gray-300 rounded-md hover:border-[#084b6f] hover:text-[#084b6f] transition-colors flex flex-col justify-center items-center">
                                                                <p className="text-gray-800 text-base font-semibold">Drop Bank Statements to upload</p>
                                                                <p className='text-xs text-gray-400'>Click here to download sample statement</p>
                                                            </div>
                                                        </label>
                                                        {fileName && (
                                                            <p className='text-xs text-red-400 mt-2'>{fileName}</p>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        </Motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        ))}
                        <div className='flex justify-center gap-4 mt-4'>
                            <button type='button' className='bg-red-700 py-2 px-4 rounded-md text-sm cursor-pointer text-white'>Cancel</button>
                            <button type='submit' className='bg-[#084b6f] py-2 px-4 rounded-md text-sm cursor-pointer text-white' disabled={loading ? true : false}>{loading ? "Submitting..." :"Submit"}</button>
                        </div>
                    </form>
                </div>
            </div>
            <Modal
                open={open}
                aria-labelledby="modal-modal-title"
                aria-describedby="modal-modal-description"
            >
                <Box sx={style}>
                    <div className="flex gap-4 items-center p-4">
                        <CircularProgress size="2rem" color='#084b6f'/><p className='font-semibold text-2xl'>Fetching Details from Bank Statement..</p>
                    </div>
                </Box>
            </Modal>
            <Modal
                open={showModal}
                aria-labelledby="modal-modal-title"
                aria-describedby="modal-modal-description"
            >
                <Box sx={style}>
                    <div className="modal">
                        <h4 className='font-semibold text-2xl mb-4'>Enter PDF Password</h4>
                        <div className="flex flex-col gap-2">
                            <TextField label="Password" value={password} onChange={(e) => setPassword(e.target.value)} size='small' fullWidth/>
                            <button className='bg-[#084b6f] py-2 px-4 rounded-md text-sm cursor-pointer text-white' onClick={handlePasswordSubmit}>Submit</button>
                        </div>
                    </div>
                </Box>
            </Modal>
        </>
    )
}

export default NewReport
