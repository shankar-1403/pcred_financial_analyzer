import React,{useMemo} from 'react';
import Datatable from '../../components/Datatable';

function StepThree({reportData}) {
    const columns = [
        { field:"id", headerName:"ID",width:80},
        { field: "date", headerName: "Txn date", width:150},
        { field: "description", headerName: "Particulars", width:200},
        { field: "cheque_ref", headerName: "Cheque/Ref nbr", width:200},
        { field: "counterparty", headerName: "Counterparty", width:200},
        { field: "debit", headerName: "Debit (₹)", width:200,align: "right",headerAlign: "right"},
        { field: "credit", headerName: "Credit (₹)", width:200,align: "right",headerAlign: "right"},
        { field: "balance", headerName: "Balance (₹)", width:200,align: "right",headerAlign: "right"},
        { field: "computed_balance", headerName: "Computed balance (₹)", width:200,align: "right",headerAlign: "right"},
        { field: "category", headerName: "Category", width:200},
        { field: "tags", headerName: "Tags", width:200},
        { field: "upi_app", headerName: "UPI App", width:200},
    ]

    const extractRefNo = (desc = "") => {
        const text = desc.toLowerCase();

        // Cheque numbers
        let match = text.match(/(chq|cheque)[^\d]*(\d{4,})/);
        if (match) return match[2];

        // UPI patterns
        match = text.match(/upi[/\- ]([a-z0-9]+)/);
        if (match) return match[1];

        // IMPS patterns
        match = text.match(/imps[/\- ]([a-z0-9]+)/);
        if (match) return match[1];

        // NEFT / RTGS (alphanumeric)
        match = text.match(/(neft|rtgs)[/\- ]([a-z0-9]+)/);
        if (match) return match[2];

        //  Generic long number (fallback)
        match = text.match(/\b\d{6,}\b/);
        if (match) return match[0];

        return "-";
    };

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

    const detectTxnType = (desc = "") => {
        const text = desc.toLowerCase();
        // 1. UPI (most common)
        if (/\bupi\b/.test(text)) return "UPI";

        // 2. IMPS
        if (/\bimps\b/.test(text)) return "IMPS";

        // 3. NEFT
        if (/\bneft\b/.test(text)) return "NEFT";

        // 4. RTGS
        if (/\brtgs\b/.test(text)) return "RTGS";

        // 5. Cheque
        if (/(chq|cheque)/.test(text)) return "CHEQUE";

        // 6. ATM / Cash
        if (/(atm|cash|withdrawal|wdr)/.test(text)) return "CASH";

        // 7. Card (POS / swipe / online)
        if (/(pos|card|debit card|credit card|ecom|purchase)/.test(text)) return "CARD";

        // 8. Bank transfer (fallback structured)
        if (/(transfer|trf|netbanking|ibanking)/.test(text)) return "TRANSFER";

        return "OTHERS";
    };

    const detectUpiApp = (desc = "") => {
        const text = desc.toLowerCase();

        if (!text.includes("upi")) return "-";

        // Try VPA detection
        const vpaMatch = text.match(/[a-z0-9.\-_]+@[a-z]+/g);

        if (vpaMatch) {
            const vpa = vpaMatch[0];

            if (vpa.includes("@ybl")) return "PhonePe";
            if (vpa.includes("@okaxis") || vpa.includes("@okhdfc") || vpa.includes("@oksbi")) return "GPay";
            if (vpa.includes("@paytm")) return "Paytm";
            if (vpa.includes("@apl")) return "Amazon Pay";
        }

        // Keyword fallback
        if (text.includes("phonepe")) return "PhonePe";
        if (text.includes("gpay")) return "GPay";
        if (text.includes("paytm")) return "Paytm";

        // Final fallback
        return "UPI";
    };

    const rows = reportData.transaction

    const data = useMemo(() => {
        return rows.reduce((acc, item, index) => {
            const debit = Number(item.debit) || 0;
            const credit = Number(item.credit) || 0;
            const actualBalance = Number(item.balance) || 0;

            let calculatedBalance;

            if (index === 0) {
                const openingBalance = actualBalance - credit + debit;
                calculatedBalance = openingBalance + credit - debit;
            } else {
                const prevBalance = acc[index - 1].computed_balance_raw;
                calculatedBalance = prevBalance + credit - debit;
            }

            acc.push({
                id: index + 1,
                date: item.date || "-",
                description: item.description || "-",
                cheque_ref: extractRefNo(item.description) || "-",
                counterparty: extractPartyName(item.description) || "-",
                debit: debit.toLocaleString("en-IN") || "",
                credit: credit.toLocaleString("en-IN") || "",
                balance: item.balance ? actualBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) : "-",
                computed_balance: calculatedBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}),
                computed_balance_raw: calculatedBalance,
                category: item.category || "-",
                tags: detectTxnType(item.description) || "-",
                upi_app: detectUpiApp(item.description) || "-",
            });

            return acc;
        }, []);
    }, [rows]);

    return (
        <>
            <div className='card'>
                <Datatable columns={columns} rows={data} height={510}/>
            </div>
        </>
    )
}

export default StepThree
