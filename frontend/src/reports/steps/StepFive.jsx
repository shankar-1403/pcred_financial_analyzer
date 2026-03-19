import React,{useState} from 'react';
import { IconChevronRight,IconChevronLeft } from '@tabler/icons-react';

function StepFive({reportData}) {
  
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const transactionDetails = reportData?.transaction || [];

  function extractPartyName(description) {
    if (!description) return null;

    let text = description.replace(/\s+/g, " ").trim();
    text = text.replace(/chq paid to/gi, "");
    text = text.replace(/cheque paid to/gi, "");
    text = text.replace(/chq clr/gi, "");
    text = text.replace(/cheque clr/gi, "");
    text = text.replace(/cheque rtn/gi, "");
    text = text.replace(/chq rtn/gi, "");
    // normalize separators
    const tokens = text
      .split(/[/|\-:]/)
      .map(t => t.trim())
      .filter(Boolean);

    const ignorePatterns = [
      /^neft$/i,
      /^rtgs$/i,
      /^imps$/i,
      /^upi$/i,
      /^p2a$/i,
      /^mob$/i,
      /^mb$/i,
      /^trf$/i,
      /^clg$/i,
      /^sak$/i,
      /^cash$/i,
      /^transfer$/i,
      /^payment$/i,
      /^self$/i,
      /^utr/i,
      /^dr$/i,
      /^cr$/i,
      /^ref$/i,
      /^txn$/i,
      /^inb$/i,
      /^tpt$/i,
      /^pos$/i,
      /^atm$/i,
      /^cheque$/i,
      /^chq$/i,

      /^[a-z]{4}\d{7}$/i,      // IFSC
      /^[a-z]{4,6}r?\d+/i,     // UTR
      /^\d+$/,                 // numbers only

      /bank/i,
      /india/i,
      /ltd$/i,
      /limited$/i,
      /pvt/i,
      /private/i
    ];

    const candidates = tokens.filter(token => {
      if (token.length < 4) return false;

      const ignore = ignorePatterns.some(p => p.test(token));
      if (ignore) return false;

      // remove ids inside name
      if (/^\d+$/.test(token)) return false;

      return true;
    });

    if (!candidates.length) return null;

    // choose the most meaningful token
    return candidates.sort((a, b) => b.length - a.length)[0];
  }

  const monthNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  /* ---------- Attach counterparty + month ---------- */

  const processedTxns = transactionDetails.map(t => {

    // eslint-disable-next-line no-unused-vars
    const [d,m,y] = t.date.split("-");

    const month = `${monthNames[Number(m)-1]} ${y}`;

    return {
      ...t,
      month,
      counterparty: extractPartyName(t.description) || "Unknown"
    };

  });

  /* ---------- Get unique months ---------- */

  const months = [...new Set(processedTxns.map(t => t.month))];

  /* ---------- Get counterparties ---------- */

  const counterparties = [...new Set(processedTxns.map(t => t.counterparty))];

  /* ---------- Rows ---------- */

  const rows = counterparties.map((party,index)=>{

    const row = {
      id:index+1,
      counterparty:party
    };

    months.forEach(month=>{

      const key = month.replace(/\s/g,"_");

      const txns = processedTxns.filter(t =>
        t.month === month && t.counterparty === party
      );

      row[`${key}_credit`] =
        txns.reduce((s,t)=>s+(Number(t.credit)||0),0);

      row[`${key}_credit_txn`] =
        txns.filter(t=>Number(t.credit)>0).length;

      row[`${key}_debit`] =
        txns.reduce((s,t)=>s+(Number(t.debit)||0),0);

      row[`${key}_debit_txn`] =
        txns.filter(t=>Number(t.debit)>0).length;

    });

    return row;

  });

  const filteredRows = rows.filter((row) =>
    row.counterparty.toLowerCase().includes(search.toLowerCase())
  );

  const start = page * rowsPerPage;
  const paginatedRows = filteredRows.slice(start, start + rowsPerPage);
  const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
  return (
    <>
      <div className="card">
        <div className="mb-3 flex justify-end">
          <input type="text" placeholder="Search counterparty..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(0);}} className="border-2 border-gray-200 px-3 py-1 rounded focus:border-[#084b6f] outline-none"/>
        </div>
        <div className='overflow-x-auto h-120 overflow-auto'>
          <table>
            <thead>
              <tr>
                <th colSpan="1" className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 -left-1 bg-white z-10 border border-gray-200"></th>

                {months.map((m) => (
                  <th key={m} colSpan="4" className="px-3 py-2 font-medium text-[14px] w-100 sticky -top-0.5 bg-white border border-gray-200">{m}</th>
                ))}
              </tr>

              <tr>
                <th className="px-3 py-2 font-medium text-[14px] text-nowrap border border-gray-200 text-left sticky -left-1 top-8 z-10 bg-[#084b6f] text-white">Counterparty</th>
                {months.map((m) => (
                  <React.Fragment key={m}>
                    <th className="px-3 py-2 font-medium text-[14px] text-nowrap bg-[#084b6f] sticky top-8 text-white text-right w-100">Credit (₹)</th>
                    <th className="px-3 py-2 font-medium text-[14px] text-nowrap bg-[#084b6f] sticky top-8 text-white text-right w-100">Credit Txns</th>
                    <th className="px-3 py-2 font-medium text-[14px] text-nowrap bg-[#084b6f] sticky top-8 text-white text-right w-100">Debit (₹)</th>
                    <th className="px-3 py-2 font-medium text-[14px] text-nowrap bg-[#084b6f] sticky top-8 text-white text-right w-100">Debit Txns</th>
                  </React.Fragment>
                ))}
              </tr>
            </thead>

            <tbody>
              {paginatedRows.map((row) => (
                <tr key={row.id}>
                  <td className="px-3 py-2 text-[14px] text-nowrap border border-gray-200 sticky -left-1 bg-white">{row.counterparty}</td>

                  {months.map((m) => {
                    const key = m.replace(/\s/g, "_");

                    return (
                      <React.Fragment key={m}>
                        <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row[`${key}_credit`].toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row[`${key}_credit_txn`]}</td>
                        <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row[`${key}_debit`].toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row[`${key}_debit_txn`]}</td>
                      </React.Fragment>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-end gap-3 mt-3">
          <div>
            Rows per page:
            <select
              value={rowsPerPage}
              onChange={(e) => {
                setRowsPerPage(Number(e.target.value));
                setPage(0);
              }}
              className="ml-2 px-2 py-1 cursor-pointer"
            >
              <option value={5}>5</option>
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
            </select>
          </div>

          <div className="flex gap-1 items-center">
            <span>
              Page {page + 1} of {totalPages}
            </span>
            <button disabled={page === 0} onClick={() => setPage(page - 1)} className="px-2 py-1 cursor-pointer"><IconChevronLeft size={18}/></button>
            <button disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)} className="px-2 py-1 cursor-pointer"><IconChevronRight size={18}/></button>
          </div>
        </div>
      </div>
    </>
  )
}

export default StepFive
