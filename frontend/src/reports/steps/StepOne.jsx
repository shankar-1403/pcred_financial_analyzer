import React from 'react';

function StepOne({reportData}) {

    const accountDetails = reportData?.account || {};
    const transactionDetails = reportData?.transaction || [];
    const monthwise = {};
    let prevDay = null;
    let prevDate = null;
    let prevMonthKey = null;
    let prevBalance = null;
    let prevDayBalance = null;
    function matchKeywords(text, keywords) {
        const escaped = keywords.map(k =>k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        const regex = new RegExp(`(^|\\W)(${escaped.join("|")})(\\W|$)`, "i")
        return regex.test(text)
    }

    transactionDetails.forEach((item) => {

        if (!item.date) return;

        // eslint-disable-next-line no-unused-vars
        const [day, month, year] = item.date.split("-");
        const monthNames = ["Jan","Feb","Mar","Apr","May","June","July","Aug","Sept","Oct","Nov","Dec"];
        const chequeIssuesKeyword = ["chq paid","cheque paid","by chq","by chq no","chq no","cheque no","clg chq","clg-chq","brn-clg-chq","chq clr","cheque debit","chq debit","cheque withdrawal","chq withdrawal"];

        const chequeDepositKeyword = ["chq dep","cheque dep","chq deposit","cheque deposit","chq deposited","cheque deposited","clg chq dep","clg-chq dep","brn-clg-chq dep","chq credit","cheque credit","chq collection","cheque collection","cheque received","chq received"];

        const bankChargesKeywords = ["service charge","service charges","service chrgs","monthly service","maintenance charges","account maintenance","bank charges","bank charge","transaction fee","txn fee","processing fee","processing charges","commission","bank commission","chq rtn","chq return","cheque rtn","cheque return","cheque bounce","return charges","o/w chrgs","o/w charges","atm charges","atm fee","atm withdrawal charges","card charges","debit card fee","credit card fee","annual card fee","sms charges","sms alert charges","alert charges","upi charges","imps charges","neft charges","rtgs charges","penalty","late fee","overdraft charges","od charges","minimum balance charges","non maintenance charges","gst @","gst on charges","gst on service","gst on bank charges"];

        const penaltyKeywords = ["penalty","penal charge","penal charges","penal interest","penalty charge","penalty charges","late fee","late charges","late payment","late payment fee","minimum balance charges","minimum balance penalty","non maintenance charges","non maintenance fee","non maintenance penalty","amb charges","amb penalty","average monthly balance charges","shortfall charges","chq rtn charges","cheque rtn charges","cheque return charges","cheque bounce charges","chq bounce charges","return charges","rtn charges","overdraft charges","od charges","od penal charges","limit overdrawn charges","over limit charges","emi penalty","emi overdue charges","loan penalty","loan overdue charges","loan late fee","gst on penalty","gst on charges","gst @"];

        const cashWithdrawalKeywords = ["cash withdrawal","cash withdraw","cash wd","cash wdl","cash w/d","by cash","to cash","self withdrawal","self cash","self wdl","withdrawal by self","atm withdrawal","atm wdl","atm w/d","atm cash","atm txn","atm transaction","cash atm","debit card atm","dc atm","self chq","self cheque"];

        const fixedObligationKeywords = ["emi","loan emi","loan repayment","loan instalment","loan installment","term loan","pl emi","hl emi","home loan emi","auto loan emi","vehicle loan emi","loan recovery","emi payment"];

        const totalObligationKeywords = ["emi","loan emi","emi payment","loan repayment","loan instalment","loan installment","term loan","pl emi","personal loan emi","hl emi","home loan emi","vehicle loan emi","auto loan emi","loan recovery","loan deduction","ecs","ecs debit","ecs dr","nach","nach debit","nach dr","ach","ach debit","ach dr","auto debit","auto-debit","standing instruction","si dr","credit card payment","cc payment","card payment","cr card payment","credit card bill","bajaj finance","hdb financial","tata capital","l&t finance","hero fincorp","shriram finance","aditya birla finance"];

        const outwardChequeBounceKeywords = ["o/w chq rtn","ow chq rtn","outward chq rtn","outward cheque rtn","outward cheque return","o/w cheque return","chq rtn","chq return","cheque rtn","cheque return","chq dishonour","cheque dishonour","chq bounced","cheque bounced","chq rtn charges","cheque rtn charges","chq return charges","cheque return charges","chq bounce charges","cheque bounce charges","rtn chq","return cheque","chq returned unpaid","cheque returned unpaid","o/w chq return charges"];

        const inwardChequeBounceKeywords = ["i/w chq rtn","iw chq rtn","inward chq rtn","inward cheque rtn","inward cheque return","i/w cheque return","iw cheque return","cheque deposited returned","chq dep rtn","cheque dep rtn","chq returned inward","inward cheque dishonour","inward chq dishonour","return inward cheque","chq dep returned unpaid","cheque dep returned unpaid","inward chq return charges","i/w chrgs"];

        const minimumBalanceChargesKeywords = ["min bal charges","minimum balance charges","minimum balance penalty","min bal penalty","min balance penalty","mab charges","mab penalty","mab non maintenance charges","mab non maintenance chgs","amb charges","amb penalty","amb non maintenance charges","non maintenance charges","non maintenance of minimum balance","avg balance charges","average balance charges","shortfall charges","shortfall in mab","shortfall in amb","penalty for non maintenance","penalty min bal","service charges min balance"];

        const selfWithdrawalKeywords = ["self withdrawal","self chq","self cheque","self","cash withdrawal","cash wd","cash wdl","cash withdraw","atm withdrawal","atm wd","atm wdl","cheque withdrawal","chq withdrawal","by chq self","self chq wd","brn cash wd","branch cash withdrawal","teller withdrawal","cash paid","cash payment","debit card withdrawal","card withdrawal"];

        const selfDepositKeywords = ["self deposit","self chq dep","self cheque deposit","cash deposit","cash dep","cash deposited","by cash","cash received","cdm deposit","cdm cash deposit","branch cash deposit","brn cash dep","teller deposit","cheque deposit self","self cheque dep","cash counter deposit"];

        const overdrawnKeywords = ["overdrawn","overdrawn charges","overdrawn interest","overdraft","od interest","od charges","od int","od chgs","excess overdraft","overdraft interest","dr balance charges","debit balance charges","negative balance charges","over limit charges","temporary overdraft","tod interest","tod charges"];

        const neftReturnKeywords = ["neft return","neft rtn","neft returned","neft return inward","neft return outward","neft reversal","neft reversed","reversal neft","neft failed","neft failure","neft transaction failed","neft rejected","neft reject","neft refund","neft refund txn","neft returned unpaid","return neft","neft credit return","neft debit return","neft inward return","neft outward return","neft remittance return"];

        const ecsNachIssuedKeywords = ["ecs","ecs debit","ecs dr","ecs payment","ecs mandate","ecs auto debit","nach","nach debit","nach dr","nach payment","nach mandate","ach","ach debit","ach dr","ach payment","auto debit","auto-debit","auto debit payment","standing instruction","si debit","si dr","e-mandate","emandate","loan ecs","emi ecs","ecs loan","nach emi","ach emi"];

        const emiLoanPaymentKeywords = ["emi","loan emi","emi payment","emi installment","emi instalment","loan repayment","loan installment","loan instalment","loan inst","loan payment","term loan","pl emi","personal loan emi","home loan emi","hl emi","vehicle loan emi","auto loan emi","loan recovery","loan deduction","loan debit","emi ecs","ecs emi","nach emi","ach emi","emi auto debit","loan auto debit","instalment","installment","loan a/c","loan ac","loan a/c no","emi debit"];

        const loanCreditKeywords = ["loan disbursement","loan disb","loan credit","pl disb","personal loan disb","pl credit","hl disb","home loan disb","home loan credit","vehicle loan disb","auto loan disb","loan a/c credit","loan account credit","loan proceeds","loan amount credited","loan release","loan disburse","loan transfer credit","od limit credit","overdraft credit","cc limit credit","loan booking credit"];

        const cashDepositKeywords = ["cash deposit","cash dep","cash deposited","by cash","cash received","cdm deposit","cdm cash dep","cdm dep","branch cash deposit","brn cash dep","cash counter deposit","cash counter","teller deposit","teller cash dep","cash lodgement","cash lodgment","self cash deposit","deposit by cash","cash credit"];

        const internalTransferKeywords = ["transfer","trf","internal transfer","internal trf","account transfer","a/c transfer","ac transfer","fund transfer","fund trf","self transfer","own account transfer","ib transfer","internet banking transfer","online transfer","mobile banking transfer","standing instruction","si","account adjustment","internal adjustment","contra","bank adjustment","system"];

        const interestPaidKeywords = ["interest paid","interest debit","interest debited","interest charged","interest charge","loan interest","loan interest debit","od interest","overdraft interest","interest on od","interest on overdraft","dr interest","debit interest","tod interest","temporary overdraft interest","interest applied","interest recovered","interest adj debit","interest adjustment debit"];

        const interestReceivedKeywords = ["interest credit","interest received","interest cr","savings interest","savings interest credit","sb interest","sb interest credit","fd interest","fd interest credit","fixed deposit interest","rd interest","recurring deposit interest","interest payout","interest payment","interest adj credit","interest adjustment credit","interest reversal","interest refund","bank interest credit"];

        const interestServiceDelayKeywords = ["penal interest","penalty interest","interest penalty","overdue interest","interest overdue","late payment interest","late interest","delay interest","interest delay charges","penal charges interest","loan overdue interest","emi overdue interest","interest on overdue","default interest","interest on delayed payment","penal interest charges"];

        const monthWord = monthNames[parseInt(month) - 1];

        const monthKey = `${monthWord} ${year}`; 
        const debit = Number(item.debit) || 0;
        const credit = Number(item.credit) || 0;
        const balance = Number(item.balance) || 0;
        const dateKey = item.date;
        const description = (item.description || "").toLowerCase();
        
        if (!monthwise[monthKey]) {
            monthwise[monthKey] = {
                month: monthKey,
                balance: balance,
                opening: balance,
                closing:balance,
                creditCount: credit > 0 ? 1 : 0,
                debitCount: debit > 0 ? 1 : 0,
                minimumBalance:balance,
                maximumBalance:balance,
                netDebit:debit,
                netCredit:credit,
                averageBalance:balance,
                emi_loan:0,
                emiLoanCount:0,
                balanceCount:1,
                chequeIssues:0,
                chqIssuesCount:0,
                chequeDeposit:0,
                chqDepositCount:0,
                bankCharges:0,
                bankChargesCount:0,
                penaltyCharges:0,
                penaltyChargesCount:0,
                firstDayBalance:balance,
                fourteenthDayBalance:balance,
                lastDayBalance:balance,
                avgDailyChangePercent: 0,
                dailyChangeSum: 0,
                dailyChangeCount: 0,
                cashWithdrawal:0,
                cashWithdrawalCount:0,
                cashDeposit:0,
                cashDepositCount:0,
                cashDepositPercentage:0,
                minEODBalance:balance,
                lastProcessedDate: null,
                dateCount:1,
                maxEODBalance:balance,
                sumEODBalance: 0,
                avgEODBalance:0,
                eodCount:0,
                fixedObligation:0,
                totalObligation:0,
                owChqBounce:0,
                owChqBounceCount:0,
                iwChqBounce:0,
                iwChqBounceCount:0,
                owChqBouncePercentage:0,
                iwChqBouncePercentage:0,
                iwChqBouncePer:0,
                minimumBalanceCharges:0,
                selfWithdrawal:0,
                selfDeposit:0,
                overDrawnDays:0,
                neftReturn:0,
                ecsNachIssued:0,
                ecsNachIssuedCount:0,
                abb:0,
                loanCredit:0,
                internalDebit:0,
                internalDebitCount:0,
                internalCredit:0,
                internalCreditCount:0,
                interestPaid:0,
                interestRecieved:0,
                interestServiceDelay:0,
                monthlyIcome:null,
                foirScore:0,
            };
        }else {
            monthwise[monthKey].netDebit += debit
            monthwise[monthKey].netCredit += credit
            monthwise[monthKey].averageBalance += balance
            monthwise[monthKey].balanceCount += 1
            monthwise[monthKey].opening = monthwise[monthKey].balance + monthwise[monthKey].debit - monthwise[monthKey].credit 

            if (matchKeywords(description, chequeIssuesKeyword)) {
                monthwise[monthKey].chequeIssues += debit;
                monthwise[monthKey].chqIssuesCount += 1;
            }

            if (matchKeywords(description, chequeDepositKeyword)) {
                monthwise[monthKey].chequeDeposit += credit;
                monthwise[monthKey].chqDepositCount += 1;
            }

            if (matchKeywords(description, bankChargesKeywords)) {
                monthwise[monthKey].bankCharges += debit;
                monthwise[monthKey].bankChargesCount += 1;
            }

            if (matchKeywords(description, penaltyKeywords)) {
                monthwise[monthKey].penaltyCharges += debit;
                monthwise[monthKey].penaltyChargesCount += 1;
            }

            if (matchKeywords(description, cashWithdrawalKeywords)) {
                monthwise[monthKey].cashWithdrawal += debit;
                monthwise[monthKey].cashWithdrawalCount += 1;
            }

            if (matchKeywords(description, cashDepositKeywords)) {
                monthwise[monthKey].cashDeposit += credit;
                monthwise[monthKey].cashDepositCount += 1;
            }

            if (matchKeywords(description,emiLoanPaymentKeywords)) {
                monthwise[monthKey].emi_loan += debit;
                monthwise[monthKey].emiLoanCount += 1;
            }
                        
            if (item.credit && Number(item.credit) > 0) {
                monthwise[monthKey].creditCount += 1;
            }

            if (item.debit && Number(item.debit) > 0) {
                monthwise[monthKey].debitCount += 1;
            }

            if (day === "01") {
                monthwise[monthKey].firstDayBalance = balance;
            }

            if (day === "14") {
                monthwise[monthKey].fourteenthDayBalance = balance;
            }
            
            if (matchKeywords(description, fixedObligationKeywords)) {
                monthwise[monthKey].fixedObligation += debit;
            }

            if (matchKeywords(description, totalObligationKeywords)) {
                monthwise[monthKey].totalObligation += debit;
            }

            if (matchKeywords(description, outwardChequeBounceKeywords)) {
                monthwise[monthKey].owChqBounce += debit;
                monthwise[monthKey].owChqBounceCount += 1;
            }

            if (matchKeywords(description, inwardChequeBounceKeywords)) {
                monthwise[monthKey].iwChqBounce += debit;
                monthwise[monthKey].iwChqBounceCount += 1;
            }

            if (matchKeywords(description, minimumBalanceChargesKeywords)) {
                monthwise[monthKey].minimumBalanceCharges += debit;
            }

            if (matchKeywords(description, selfWithdrawalKeywords)) {
                monthwise[monthKey].selfWithdrawal += debit;
            }

            if (matchKeywords(description, selfDepositKeywords)) {
                monthwise[monthKey].selfDeposit += credit;
            }

            if (matchKeywords(description, overdrawnKeywords)) {
                monthwise[monthKey].overDrawnDays += 1;
            }

            if (matchKeywords(description, neftReturnKeywords)) {
                monthwise[monthKey].neftReturn += credit;
            }

            if (matchKeywords(description, ecsNachIssuedKeywords)) {
                monthwise[monthKey].ecsNachIssued += debit;
                monthwise[monthKey].ecsNachIssuedCount += 1;
            }

            if (matchKeywords(description, loanCreditKeywords)) {
                monthwise[monthKey].loanCredit += credit;
            }

            if (matchKeywords(description, internalTransferKeywords)) {
                if (debit > 0) {
                    monthwise[monthKey].internalDebit += debit;
                    monthwise[monthKey].internalDebitCount += 1;
                }

                if (credit > 0) {
                    monthwise[monthKey].internalCredit += credit;
                    monthwise[monthKey].internalCreditCount += 1;
                }
            }

            if (matchKeywords(description, interestPaidKeywords)) {
                monthwise[monthKey].interestPaid += debit;
            }

            if (matchKeywords(description, interestReceivedKeywords)) {
                monthwise[monthKey].interestRecieved += credit;
            }

            if (matchKeywords(description, interestServiceDelayKeywords)) {
                monthwise[monthKey].interestServiceDelay += debit;
            }
        }
        
        monthwise[monthKey].minimumBalance = Math.min(monthwise[monthKey].minimumBalance, balance)
        monthwise[monthKey].maximumBalance = Math.max(monthwise[monthKey].maximumBalance, balance)
        monthwise[monthKey].abb = monthwise[monthKey].firstDayBalance + monthwise[monthKey].fourteenthDayBalance + monthwise[monthKey].closing / 3
        monthwise[monthKey].owChqBouncePercentage = monthwise[monthKey].chqIssuesCount ? (monthwise[monthKey].owChqBounceCount/monthwise[monthKey].chqIssuesCount)*100 : 0
        monthwise[monthKey].iwChqBouncePercentage = monthwise[monthKey].chqDepositCount ? (monthwise[monthKey].iwChqBounceCount/monthwise[monthKey].chqDepositCount)*100 : 0
        monthwise[monthKey].cashDepositPercentage = monthwise[monthKey].creditCount ? (monthwise[monthKey].cashDepositCount/monthwise[monthKey].creditCount)*100 : 0
        monthwise[monthKey].monthlyIcome = monthwise[monthKey].credit - monthwise[monthKey].loanCredit - monthwise[monthKey].internalCredit - monthwise[monthKey].interestRecieved

        monthwise[monthKey].foirScore = monthwise[monthKey].monthlyIcome ? (monthwise[monthKey].totalObligation/monthwise[monthKey].monthlyIcome) * 100 : 0

        if (prevDay !== dateKey) {

            if (prevDayBalance !== null) {

                const changePercent =
                    ((balance - prevDayBalance) / prevDayBalance) * 100;

                monthwise[monthKey].dailyChangeSum += changePercent;
                monthwise[monthKey].dailyChangeCount += 1;
            }

            prevDay = dateKey;
        }

        prevDayBalance = balance;

        if (prevDate !== null && prevDate !== dateKey) {
            const eodBalance = prevBalance
            // previous transaction was end of previous day
            monthwise[prevMonthKey].minEODBalance = Math.min(
                monthwise[prevMonthKey].minEODBalance,
                prevBalance
            );

            monthwise[prevMonthKey].maxEODBalance = Math.max(
                monthwise[prevMonthKey].maxEODBalance,
                prevBalance
            );

            monthwise[prevMonthKey].sumEODBalance += eodBalance;
            monthwise[prevMonthKey].eodCount += 1
        }

        prevDate = dateKey;
        prevMonthKey = monthKey;
        prevBalance = balance;
                
    });

    Object.values(monthwise).forEach((m) => {

        if (m.dailyChangeCount > 0) {
            m.avgDailyChangePercent =
                Number((m.dailyChangeSum / m.dailyChangeCount).toFixed(2));
        }

        if (m.eodCount > 0) {
            m.avgEODBalance = Number((m.sumEODBalance / m.eodCount).toFixed(2));
        }

    });
    const result = Object.values(monthwise);

    const firstDate = transactionDetails[0]?.date.split("-").join("/") || "-";
    const lastDate = transactionDetails[transactionDetails.length - 1]?.date.split("-").join("/") || "-";
    return (
        <>
            <div className="flex gap-1">
                <div className='w-[45%]'>
                    <div className="card">
                        <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Bank Accounts</h2>
                        <div className='max-h-110 overflow-auto'>
                            <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                                <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                                    <tr>
                                        <th scope="col" className="px-3 py-2 font-medium text-[14px] w-50">Description</th>
                                        <th scope="col" className="px-3 py-2 font-medium text-[14px]">{(accountDetails?.bank_name || " ") + " - " + (accountDetails?.account_number || " ") + " - " + (accountDetails?.acc_type || " ")}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account Holders</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.account_holder || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account Number</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.account_number || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Bank Name</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.bank_name || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Email</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.email_address || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Phone Number</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.phone_no || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">PAN</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.pan || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Statement From</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.statement_period?.from.split("-").join("/") || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Statement To</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.statement_period?.to.split("-").join("/") || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Txn Start Date</td>
                                        <td className="px-3 py-2 text-[14px]">{firstDate || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Txn End Date</td>
                                        <td className="px-3 py-2 text-[14px]">{lastDate || "-"}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div className='w-[65%]'>
                    <div className="card">
                        <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Monthwise details</h2>
                        <div className='max-h-110 overflow-auto'>
                            <table className="border border-gray-200 text-left rtl:text-right text-body w-full table-fixed">
                                <thead >
                                    <tr>
                                        <th className="px-3 py-2 font-medium text-[14px] sticky top-0 -left-px bg-white z-20 w-50">Description</th>
                                        {result.map((m) => (
                                            <th key={m.month} className="px-3 py-2 font-medium text-[14px] sticky top-0 bg-white z-10 w-50 text-right">
                                                {m.month}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Opening Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.opening?.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Closing Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.closing?.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">FOIR Score</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.foirScore?.toFixed(2) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Min Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.minimumBalance?.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Max Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.maximumBalance?.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Debit Txns Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.debitCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Credit Txns Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.creditCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Net Debit</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.netDebit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Net Credit</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.netCredit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Interest Paid</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.interestPaid.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Interest Recieved</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.interestRecieved.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Average Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {((m.averageBalance || 0) / (m.balanceCount || 1)).toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2})}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">EMI / Loan Payments</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.emi_loan.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">EMI / Loan Payments Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.emiLoanCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cheque Issues</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.chequeIssues.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cheque Issues Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.chqIssuesCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cheque Deposits</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.chequeDeposit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Internal Debit Txns</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.internalDebit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Internal Debit Txns Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.internalDebitCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Internal Credit Txns</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.internalCredit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Internal Credit Txns Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.internalCreditCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Loan Credit</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.loanCredit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cheque Deposits Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.chqDepositCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cash Withdrawal</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.cashWithdrawal.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cash Withdrawal Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.cashWithdrawalCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cash Deposits</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.cashDeposit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cash Deposits Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.cashDepositCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Cash Deposits %</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.cashDepositPercentage.toFixed(2) ?? "-"} %</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Bank Charges</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.bankCharges.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Bank Charges Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.bankChargesCount.toLocaleString("en-IN") ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Penalty Charges</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.penaltyCharges.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Penalty Charges Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.penaltyChargesCount.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Balance on 1st</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.firstDayBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Balance on 14th</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.fourteenthDayBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Balance on 30/last day</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.closing.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">ABB on 1st,14th, 30th/Last Day</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.abb.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"} </td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Daily Balance Change %</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.avgDailyChangePercent.toFixed(2) ?? "-"} %</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Min EOD Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.minEODBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"} </td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Max EOD Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.maxEODBalance.toLocaleString("en-IN") ?? "-"} </td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Avg EOD Balance</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.avgEODBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"} </td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Fixed Obligations aka Loan Repayments</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.fixedObligation.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">O/W Cheque Bounces</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.owChqBounceCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">O/W Cheque Bounces %</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.owChqBouncePercentage.toFixed(2) ?? "-"} %</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">I/W Cheque Bounces</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.iwChqBounceCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">I/W Cheque Bounces %</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.iwChqBouncePercentage.toFixed(2) ?? "-"} %</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Minimum Balance Charges</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.minimumBalanceCharges.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Self Withdrawl</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.selfWithdrawal.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Self Deposit</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.selfDeposit.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Overdrawn Days</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.overDrawnDays ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">NEFT Returns</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.neftReturn.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">ECS/NACH Issued</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.ecsNachIssued.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">ECS/NACH Issued Count</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">{m.ecsNachIssuedCount ?? "-"}</td>
                                        ))}
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] -left-px sticky bg-white z-10">Interest Service Delay</td>
                                        {result.map((m) => (
                                            <td key={m.month} className="px-3 py-2 text-[14px] whitespace-nowrap text-right">₹ {m.interestServiceDelay.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) ?? "-"}</td>
                                        ))}
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </>
    )
}

export default StepOne
