import React from 'react'

function StepSix({reportData}) {
  const transactionDetails = reportData.transaction
  
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

  const creditTxns = transactionDetails.reduce((acc, t) => {

    const party = extractPartyName(t.description) || "Unknown";
    const credit = Number(t.credit) || 0;
    const debit = Number(t.debit) || 0;

    if (!acc[party]) {
      acc[party] = {
        counterparty: party,
        credit: 0,
        debit: 0,
        creditCount: 0,
        creditPercentage: 0
      };
    }

    if (credit > 0) {
      acc[party].credit += credit;
      acc[party].creditCount += 1;
    }

    if (debit > 0) {
      acc[party].debit += debit;
    }

    return acc;

  }, {});

  const totalCredit = Object.values(creditTxns).reduce((sum, p) => sum + p.credit, 0);

  const creditTxnArray = Object.values(creditTxns)
    .filter(party => party.credit > 0)
    .map(party => {
      return {
        ...party,
        creditPercentage: totalCredit > 0 ? ((party.credit / totalCredit) * 100).toFixed(2) : 0
      };
    });

  const debitTxns = transactionDetails.reduce((acc, t) => {

    const party = extractPartyName(t.description) || "Unknown";
    const credit = Number(t.credit) || 0;
    const debit = Number(t.debit) || 0;

    if (!acc[party]) {
      acc[party] = {
        counterparty: party,
        credit: 0,
        debit: 0,
        debitCount: 0,
        debitPercentage: 0
      };
    }

    if (credit > 0) {
      acc[party].credit += credit;
    }

    if (debit > 0) {
      acc[party].debit += debit;
      acc[party].debitCount += 1;
    }

    return acc;

  }, {});

  const totalDebit = Object.values(creditTxns).reduce((sum, p) => sum + p.debit, 0);

  const debitTxnArray = Object.values(debitTxns)
    .filter(party => party.debit > 0)
    .map(party => {
      return {
        ...party,
        debitPercentage: totalDebit > 0 ? ((party.debit / totalDebit) * 100).toFixed(2) : 0
      };
    });

  const debitTxnCount = debitTxnArray.length
  const creditTxnCount = creditTxnArray.length

  return (
    <>
      <div className="flex gap-1 w-full">
        <div className="w-[50%]">
          <div className="card">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Credit Txns [{debitTxnCount}]</h2>
            <div className="overflow-y-auto h-120">
              <table className='w-full'>
                <thead>
                  <tr>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200 text-start">Counterparty</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Amount (₹)</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Amount %</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Txn count</th>
                  </tr>
                </thead>
                <tbody>
                  {creditTxnArray.map((row, index) => (
                    <tr key={index}>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 capitalize">{row.counterparty}</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.credit.toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.creditPercentage}%</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.creditCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="w-[50%]">
          <div className="card">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Debit Txns [{creditTxnCount}]</h2>
            <div className="overflow-y-auto h-120">
              <table className='w-full'>
                <thead>
                  <tr>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200 text-start">Counterparty</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Amount (₹)</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Amount %</th>
                    <th scope='col' className="px-3 py-2 font-medium text-[14px] text-nowrap sticky -top-0.5 border-b bg-[#084b6f] text-white border-gray-200">Txn count</th>
                  </tr>
                </thead>
                <tbody>
                  {debitTxnArray.map((row, index) => (
                    <tr key={index}>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 capitalize">{row.counterparty}</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.debit.toLocaleString("en-IN")}</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.debitPercentage}%</td>
                      <td className="px-3 py-2 text-[14px] border-b border-gray-200 text-right">{row.debitCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

export default StepSix
