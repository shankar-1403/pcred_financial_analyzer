import React from 'react';
import Datatable from '../../components/Datatable';

function StepThree({reportData}) {
    const columns = [
        { field:"id", headerName:"ID",width:80},
        { field: "date", headerName: "Txn date", width:150},
        { field: "description", headerName: "Particulars", width:200},
        { field: "cheque_ref", headerName: "Cheque/Ref nbr", width:200},
        { field: "counterparty", headerName: "Counterparty", width:200},
        { field: "debit", headerName: "Debit (₹)", width:200},
        { field: "credit", headerName: "Credit (₹)", width:200},
        { field: "balance", headerName: "Balance (₹)", width:200},
        { field: "computed_balance", headerName: "Computed balance (₹)", width:200},
        { field: "category", headerName: "Category", width:200},
        { field: "tags", headerName: "Tags", width:200},
        { field: "upi_app", headerName: "UPI App", width:200},
    ]

    const rows = reportData.transaction

    const data = rows.map((item,index) => ({
        id:index + 1,
        date:item.date || "-",
        description:item.description || "-",
        cheque_ref:item.cheque_ref || "-",
        counterparty:item.counterparty || "-",
        debit:item.debit || "-",
        credit:item.credit || "-",
        balance:item.balance || "-",
        computed_balance:item.computed_balance || "-",
        category:item.category || "-",
        tags:item.tags || "-",
        upi_app:item.upi_app || "-",
    }))

    return (
        <>
            <div className='card'>
                <Datatable columns={columns} rows={data} height={510}/>
            </div>
        </>
    )
}

export default StepThree
