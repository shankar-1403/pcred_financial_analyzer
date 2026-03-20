import React,{useMemo} from 'react';
import Accordion from '@mui/material/Accordion';
import AccordionSummary from '@mui/material/AccordionSummary';
import AccordionDetails from '@mui/material/AccordionDetails';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';

function StepFour({reportData}) {
  const [expanded, setExpanded] = React.useState(false);

  const handleChange = (panel) => (event, isExpanded) => {
    setExpanded(isExpanded ? panel : false);
  };

  const transactionDetails = reportData.transaction
  const rtgsPaymentKeywords = [  "rtgs",  "rtgs payment",  "rtgs transfer",  "rtgs outward",  "rtgs out",  "rtgs txn",  "rtgs trf",  "rtgs remittance",  "by rtgs",  "rtgs paid",  "rtgs dr",  "rtgs debit",  "rtgs outward remittance",  "rtgs customer transfer",  "rtgs fund transfer",  "rtgs payment to",  "rtgs transfer to",  "rtgs outward payment"];
  const cashDepositKeywords = ["cash deposit","cash dep","cash deposited","by cash","cash received","cdm deposit","cdm cash dep","cdm dep","branch cash deposit","brn cash dep","cash counter deposit","cash counter","teller deposit","teller cash dep","cash lodgement","cash lodgment","self cash deposit","deposit by cash","cash credit"];
  const atmWithdrawalKeywords = ["atm","atm wdl","atm withdrawal","atm cash","cash withdrawal atm","cash wd","cash wdl","cash withdrawal","atm-cash","atm cash withdrawal","atm withdrawal self","self atm","self withdrawal","atm txn","atm trxn","atm transaction","atm debit","atm dr","atm withdraw","card withdrawal","card cash withdrawal","card wdl","debit card atm","dc atm withdrawal","dc wdl","nfs atm withdrawal","nfs cash withdrawal","atm nfs","atm-nfs","nfs wdl","atm pos cash","atm withdrawal charges","atm charges"];
  const loanCreditKeywords = ["loan disbursement","loan disb","loan credit","pl disb","personal loan disb","pl credit","hl disb","home loan disb","home loan credit","vehicle loan disb","auto loan disb","loan a/c credit","loan account credit","loan proceeds","loan amount credited","loan release","loan disburse","loan transfer credit","od limit credit","overdraft credit","cc limit credit","loan booking credit"];
  const internalTransferKeywords = ["transfer","trf","internal transfer","internal trf","account transfer","a/c transfer","ac transfer","fund transfer","fund trf","self transfer","own account transfer","ib transfer","internet banking transfer","online transfer","mobile banking transfer","standing instruction","si","account adjustment","internal adjustment","contra","bank adjustment","system"];
  const interestReceivedKeywords = ["interest credit","interest received","interest cr","savings interest","savings interest credit","sb interest","sb interest credit","fd interest","fd interest credit","fixed deposit interest","rd interest","recurring deposit interest","interest payout","interest payment","interest adj credit","interest adjustment credit","interest reversal","interest refund","bank interest credit"];
  const salaryKeywords = ["salary","sal","salary credit","sal credit","sal cr","salary cr","salary payment","salary deposit","payroll","payroll credit","net salary","monthly salary","salary for","sal for","salary transfer","sal transfer","salary processed","salary via","salary ach","salary neft","salary imps","salary rtgs"];
  const taxKeywords = ["gst","gst payment","cgst","sgst","igst","tds","income tax","tax payment","advance tax","self assessment tax","challan","tax deposit"];
  
  function matchKeywords(text, keywords) {
    const escaped = keywords.map(k =>k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    const regex = new RegExp(`(^|\\W)(${escaped.join("|")})(\\W|$)`, "i")
    return regex.test(text)
  }

  const monthwise = {}
  transactionDetails.forEach((item)=>{
    if (!item.date) return;
    // eslint-disable-next-line no-unused-vars
    const [day, month, year] = item.date.split("-");
    const monthNames = ["Jan","Feb","Mar","Apr","May","June","July","Aug","Sept","Oct","Nov","Dec"];
    const monthWord = monthNames[parseInt(month) - 1];
    const monthKey = `${monthWord} ${year}`;
    const debit = item.debit;
    const description = item.description;
    const credit = item.credit;
    if (!monthwise[monthKey]){
      monthwise[monthKey] = {
        month:monthKey,
        credit:0,
        creditCount:0,
        debit:0,
        debitCount:0,
        chequeDeposit:0,
        loanCredit:0,
        internalCredit:0,
        interestRecieved:0,
        monthlyIncome:null,
        transactions:[]
      }
    }

    if (credit > 0) {
      monthwise[monthKey].credit += credit;
      monthwise[monthKey].creditCount += 1;
    }

    if (debit > 0) {
      monthwise[monthKey].debit += debit;
      monthwise[monthKey].debitCount += 1;
    }

    const isLoanCredit = matchKeywords(description, loanCreditKeywords);
    const isInternalTransfer = matchKeywords(description, internalTransferKeywords);
    const isInterest = matchKeywords(description, interestReceivedKeywords);

    if (isInterest) {
      monthwise[monthKey].interestRecieved += credit;
    }

    if (isInternalTransfer) {
      monthwise[monthKey].internalCredit += credit;
    }

    if (isLoanCredit) {
      monthwise[monthKey].loanCredit += credit;
    }

    monthwise[monthKey].monthlyIncome = monthwise[monthKey].credit - monthwise[monthKey].loanCredit - monthwise[monthKey].internalCredit - monthwise[monthKey].interestRecieved
    monthwise[monthKey].transactions.push(item);

  })

  const debit_credit = Object.values(monthwise).filter(
    m => m.creditCount === m.debitCount
  );

  function extractRTGSCounterparty(description) {
    if (!description) return null;

    const tokens = description
      .split(/[/:-]/)
      .map(t => t.trim())
      .filter(Boolean);

    const ignorePatterns = [
      /^rtgs$/i,
      /^neft$/i,
      /^imps$/i,
      /^upi$/i,
      /^mb$/i,
      /^ib$/i,
      /^net$/i,
      /^utr/i,
      /^[a-z]{4}\d{7}$/i,        // IFSC
      /^[a-z]{4,6}r?\d+/i,       // UTR like UTIBR72025
      /^\d+$/,                   // numbers
      /bank/i
    ];

    for (const token of tokens) {
      const ignore = ignorePatterns.some(p => p.test(token));

      if (!ignore && token.length > 2) {
        return token;
      }
    }

    return null;
  }

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

  const roundFigureTaxPayments = Object.values(monthwise)
    .flatMap(m => m.transactions)
    .filter(txn => {
      const desc = txn.description?.toLowerCase() || "";
      const debit = Number(txn.debit) || 0;

      return (
        debit > 0 &&
        debit % 1000 === 0 &&
        matchKeywords(desc, taxKeywords)
      );
    })
    .map(txn => ({
      txn_date: txn.date,
      description: txn.description,
      counterparty: extractRTGSCounterparty(txn.description),
      amount: txn.debit,
      balance: txn.balance
    }));

  const rtgsbelow = Object.values(monthwise)
    .flatMap(m => m.transactions) 
    .filter((txn) => {
      const desc = txn.description?.toLowerCase() || "";
      const debit = Number(txn.debit) || 0;
      return matchKeywords(desc, rtgsPaymentKeywords) && debit > 0 && debit < 200000;
    })
    .map((txn) => ({
      txn_date: txn.date,
      description: txn.description,
      counterparty: extractRTGSCounterparty(txn.description),
      amount: txn.debit,
      balance: txn.balance
    }));

  const atmWithdrawalAbove = Object.values(monthwise)
    .flatMap(m => m.transactions)
    .filter((txn)=> {
      const debit = txn.debit
      const desc = txn.description?.toLowerCase() || "";
      return matchKeywords(desc, atmWithdrawalKeywords) && debit >= 20000
    })
    .map((txn) => ({
      txn_date: txn.date,
      description: txn.description,
      amount: txn.debit,
      balance: txn.balance
    }));


  let prevBalance = null;

  const balanceVsComputedBalance = Object.values(monthwise)
    .flatMap(m => m.transactions)
    .map((txn) => {

      const debit = txn.debit || 0;
      const credit = txn.credit || 0;
      const balance = txn.balance || 0;

      const computedBalance =
        prevBalance !== null ? prevBalance - debit + credit : null;

      const gap =
        computedBalance !== null ? Number((balance - computedBalance).toFixed(2)) : null;

      const mismatch =
        computedBalance !== null && Math.abs(gap) > 1;

      prevBalance = balance;

      return {
        txn_date: txn.date,
        description: txn.description,
        counterparty: extractRTGSCounterparty(txn.description),
        debit:debit,
        credit:credit,
        balance:balance,
        computed_balance: computedBalance?.toFixed(2),
        balance_gap:gap,
        mismatch
      };
    })
    .filter(txn => txn.mismatch);

  const partiesBothDebitCredit = Object.values(monthwise)
    .flatMap(month =>
      month.transactions.map(txn => ({
        ...txn,
        party: extractPartyName(txn.description),
        month: month.month
      }))
    )
    .reduce((acc, txn) => {

      if (!txn.party) return acc;

      const key = `${txn.party}-${txn.month}`;
      const debit = Number(txn.debit) || 0;
      const credit = Number(txn.credit) || 0;

      if (!acc[key]) {
        acc[key] = {
          party: txn.party,
          month: txn.month,
          debitAmount: 0,
          creditAmount: 0,
          txnCount: 0
        };
      }

      acc[key].debitAmount += debit;
      acc[key].creditAmount += credit;
      acc[key].txnCount += 1;

      return acc;

    }, {});

  const partiesPresentDebitCredit = Object.values(partiesBothDebitCredit)
    .filter(p => p.debitAmount > 0 && p.creditAmount > 0)
    .map(p => ({
      counterparty: p.party,
      month: p.month,
      debit_amount: p.debitAmount,
      credit_amount: p.creditAmount,
      debit_percentage: ((p.debitAmount / (p.debitAmount + p.creditAmount)) * 100).toFixed(2),
      credit_percentage: ((p.creditAmount / (p.debitAmount + p.creditAmount)) * 100).toFixed(2),
      txn_count: p.txnCount
    }));

  const highCashDeposits = Object.values(monthwise)
    .flatMap(month =>
      month.transactions
      .filter(txn => {
        const desc = (txn.description || "").toLowerCase();
        const credit = Number(txn.credit) || 0;
        const monthlyIncome = Number(month.monthlyIncome) || 0;
        const isCashDeposit = matchKeywords(desc,cashDepositKeywords);

        return isCashDeposit && credit > monthlyIncome;
      })
      .map(txn => ({
        month: month.month,
        cash_txn: Number(txn.credit) || 0,
        salary_txn: Number(month.monthlyIncome) || 0,
      }))
  );

  // Salary unchanged ------------------------------------- //

    const salaryAnalysis = useMemo(() => {

      const tolerance = 2000;

      const isSalary = (desc, amount) => {
        if (!desc) return false;
        const text = desc.toLowerCase();
        return salaryKeywords.some(k => text.includes(k)) && amount > 2000;
      };

      // Step 1: filter salary
      const salaryTxns = transactionDetails.filter(item =>
          isSalary(item.description, item.credit)
      );

      // Step 2: group by month
      const monthMap = {};

      salaryTxns.forEach(item => {
          // eslint-disable-next-line no-unused-vars
          const [day, month, year] = item.date.split("-");
          const key = `${month} ${year}`;

          if (!monthMap[key]) {
              monthMap[key] = [];
          }

          monthMap[key].push(item.credit);
      });

      // Step 3: monthly salary
      const monthwise = Object.entries(monthMap).map(([month, values]) => ({
        month,
        income: Math.max(...values)
      }));

      // Step 4: sort
      const monthOrder = {
        Jan:1, Feb:2, Mar:3, Apr:4, May:5, June:6,
        July:7, Aug:8, Sept:9, Oct:10, Nov:11, Dec:12
      };

      const months = monthwise.sort((a, b) => {
        const [m1, y1] = a.month.split(" ");
        const [m2, y2] = b.month.split(" ");

        if (y1 !== y2) return Number(y1) - Number(y2);
        return monthOrder[m1] - monthOrder[m2];
      });

      // unchanged periods (for table)
      const salaryUnchanged = [];

      let startMonth = null;
      let prevIncome = null;
      let count = 0;

      months.forEach((m, index) => {
        const income = Number(m.income) || 0;

        if (prevIncome !== null && Math.abs(income - prevIncome) <= tolerance && income > 0) {
            count++;
        } else {

            if (count >= 3) {
                salaryUnchanged.push({
                    period: `${startMonth} - ${months[index-1].month}`,
                    salary_credit_from: startMonth,
                    amount: prevIncome,
                    txn_count: count
                });
            }

            startMonth = m.month;
            prevIncome = income;
            count = 1;
        }
      });

      if (count >= 3) {
        salaryUnchanged.push({
          period: `${startMonth} - ${months[months.length-1].month}`,
          salary_credit_from: startMonth,
          amount: prevIncome,
          txn_count: count
        });
      }

      // change count (for summary)
      let changeCount = 0;

      for (let i = 1; i < months.length; i++) {
          const prev = months[i - 1].income;
          const curr = months[i].income;

          if (Math.abs(curr - prev) > tolerance) {
              changeCount++;
          }
      }

      return {
          salaryUnchanged,
          changeCount
      };

    }, [transactionDetails]);
  
  // -------------------
  return (
    <>
      <div className="card">
        <div className='flex flex-col gap-1'>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel1'} onChange={handleChange('panel1')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel1-content" id="panel1-header">
              <span className='font-bold'>Round Figure Tax Payments</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Txn date</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Particulars</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Counterparty</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Balance (₹)</th>
                    </tr>
                </thead>
                <tbody>
                    {roundFigureTaxPayments.length > 0 ? (
                      roundFigureTaxPayments.map((data, index) => (
                        <tr key={`${data.month}-${index}`} className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-1.5 text-[12px]">{data?.month ?? "-"}</td>
                          <td className="px-3 py-1.5 text-[12px]">{data?.description ?? "-"}</td>
                          <td className="px-3 py-1.5 text-[12px]">{data?.counterparty ?? "-"}</td>
                          <td className="px-3 py-1.5 text-[12px] text-right">₹ {data?.amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                          <td className="px-3 py-1.5 text-[12px] text-right">₹ {data?.balance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td className="px-3 py-1.5 text-[12px] text-center" colSpan={5}>
                          No Data Available
                        </td>
                      </tr>
                    )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel2'} onChange={handleChange('panel2')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel2-content" id="panel2-header">
              <span className='font-bold'>Equal Debits and Credits</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Month</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Credit Txn count</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Credit amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Debit txn count</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Debit amount (₹)</th>
                    </tr>
                </thead>
                <tbody>
                  {debit_credit.length > 0 ? (
                    debit_credit.map((data, index) => (
                      <tr key={`${data.month}-${index}`} className="bg-neutral-primary border-b border-gray-200">
                        <td className="px-3 py-1.5 text-[12px]">{data?.month ?? "-"}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{data?.creditCount ?? "-"}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {data?.credit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{data?.debitCount ?? "-"}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {data?.debit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={5}>
                        No Data Available
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel3'} onChange={handleChange('panel3')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel3-content" id="panel3-header">
              <span className='font-bold'>RTGS Payments Below ₹ 2,00,000</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Txn date</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Particulars</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Counterparty</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Balance (₹)</th>
                    </tr>
                </thead>
                <tbody>
                  {rtgsbelow.length > 0 ? (
                    rtgsbelow.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.txn_date}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.description}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.counterparty}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.balance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>

                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={5}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel6'} onChange={handleChange('panel6')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel6-content" id="panel6-header">
              <span className='font-bold'>ATM Withdrawals above ₹20,000</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Txn date</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Particulars</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Balance (₹)</th>
                    </tr>
                </thead>
                <tbody>
                  {atmWithdrawalAbove.length > 0 ? (
                    atmWithdrawalAbove.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.txn_date}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.description}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.balance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={5}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel7'} onChange={handleChange('panel7')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel7-content" id="panel7-header">
              <span className='font-bold'>Balance VS Computed Balance Mismatch</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Txn date</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Particulars</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Counterparty</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Debit (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Credit (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Balance (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Computed Balance (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Balance Gap (₹)</th>
                    </tr>
                </thead>
                <tbody>
                  {balanceVsComputedBalance.length > 0 ? (
                    balanceVsComputedBalance.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.txn_date}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.description}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.counterparty}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.debit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.credit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.balance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.computed_balance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td> 
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.balance_gap.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={8}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel9'} onChange={handleChange('panel9')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel9-content" id="panel9-header">
              <span className='font-bold'>Parties Present in Both Debits and Credits</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Counterparty</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Month</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Debit amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">% Debit Amount</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Credit Amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">% Credit Amount</th>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Txn Count</th>
                    </tr>
                </thead>
                <tbody>
                  {partiesPresentDebitCredit.length > 0 ? (
                    partiesPresentDebitCredit.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.counterparty}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.month}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.debit_amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.debit_percentage}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">₹ {txn.credit_amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.credit_percentage}</td>
                        <td className="px-3 py-1.5 text-[12px]">{txn.txn_count}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={7}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
          <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel10'} onChange={handleChange('panel10')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel10-content" id="panel10-header">
              <span className='font-bold'>More Cash deposits vs Salary</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Month</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Cash Txn (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Salary Txn (₹)</th>
                    </tr>
                </thead>
                <tbody>
                  {highCashDeposits.length > 0 ? (
                    highCashDeposits.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.month}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.cash_txn.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.salary_txn.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={3}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
           <Accordion sx={{borderRadius:"4px","&:before": {display: "none"}}} expanded={expanded === 'panel11'} onChange={handleChange('panel11')}>
            <AccordionSummary sx={{background:"#084b6f",color:"white",borderRadius:"4px"}} expandIcon={<ArrowDropDownIcon sx={{color:"white"}}/>} aria-controls="panel11-content" id="panel11-header">
              <span className='font-bold'>Salary credit amount remains unchanged over extended period</span>
            </AccordionSummary>
            <AccordionDetails>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                    <tr>
                        <th className="px-3 py-1.5 font-medium text-[12px]">Month</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Salary Credit From</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Amount (₹)</th>
                        <th className="px-3 py-1.5 font-medium text-[12px] text-right">Txn count</th>
                    </tr>
                </thead>
                <tbody>
                  {salaryAnalysis.salaryUnchanged.length > 0 ? (
                    salaryAnalysis.salaryUnchanged.map((txn, index) => (
                      <tr key={index}>
                        <td className="px-3 py-1.5 text-[12px]">{txn.period}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.salary_credit_from}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.amount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                        <td className="px-3 py-1.5 text-[12px] text-right">{txn.txn_count}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-3 py-1.5 text-[12px] text-center" colSpan={4}>No Data Available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
        </div>
      </div>
    </>
  )
}

export default StepFour
