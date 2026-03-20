import React, { useMemo, useRef, useLayoutEffect } from 'react';
import dayjs from 'dayjs';
import duration from 'dayjs/plugin/duration';
import relativeTime from 'dayjs/plugin/relativeTime';
import customParseFormat from "dayjs/plugin/customParseFormat";
import * as am5 from "@amcharts/amcharts5";
import * as am5xy from "@amcharts/amcharts5/xy";
import am5themes_Animated from "@amcharts/amcharts5/themes/Animated";


function StepTwo({reportData}) {
   
    const accountDetails = reportData?.account
    const transactionDetails = reportData?.transaction

    const averageMonthBalance = useMemo(() => {

        const monthwise = {};

        transactionDetails.forEach((item) => {
            if (!item.date) return;

            // eslint-disable-next-line no-unused-vars
            const [day, month, year] = item.date.split("-");
            const monthKey = `${year}-${month}`;
            const balance = Number(item.balance) || 0;

            if (!monthwise[monthKey]) {
                monthwise[monthKey] = { total: balance, count: 1 };
            } else {
                monthwise[monthKey].total += balance;
                monthwise[monthKey].count += 1;
            }
        });

        const months = Object.values(monthwise);

        const total = months.reduce((s, m) => s + m.total / m.count, 0);

        return months.length ? total / months.length : 0;

    }, [transactionDetails]);

    const transactionCount = useMemo(() => {
        return transactionDetails.filter(item => item?.balance != null).length;
    }, [transactionDetails]);

    const cashDeposit40to50k = useMemo(() => {
        return transactionDetails.filter(item => 
            item.debit >= 40000 && item.debit <= 50000
        ).length
    }, [transactionDetails]);

    const cashDeposit9to10L = useMemo(() => {
        return transactionDetails.filter(item => 
            item.debit >= 900000 && item.debit <= 1000000
        ).length
    }, [transactionDetails]);


    
    const bounceChqCount = useMemo(() => {
        const chequeReturn = ["chq return","chq dishonoured","dishonour","bounce","ret","rtn","returned","chq rtn","insf balance/insufficient fund","funds insuff"];
        return transactionDetails.filter(item => 
            chequeReturn.some(keyword =>
                (item.description || "").toLowerCase().includes(keyword)
            )
        ).length
    }, [transactionDetails]);

    const circularTransactionCount = useMemo(() => {

        const debitSet = new Set()

        transactionDetails.forEach(item => {
            if (Number(item.debit) > 0) {
                debitSet.add(Number(item.debit))
            }
        })

        return transactionDetails.filter(item =>
            Number(item.credit) > 0 && debitSet.has(Number(item.credit))
        ).length

    }, [transactionDetails])

    const firstDate = transactionDetails[0]?.date.split("-").join("/") || "-";
    const lastDate = transactionDetails[transactionDetails.length - 1]?.date.split("-").join("/") || "-";

    dayjs.extend(duration);
    dayjs.extend(relativeTime);
    dayjs.extend(customParseFormat);

    const parseDate = (date) => {
        const formats = [
            "YYYY-MM-DD",
            "DD-MM-YYYY",
            "DD/MM/YYYY",
            "DD/MM/YY",
            "DD MMM YYYY",
            "DD MMM YY",
            "DD-MMM-YY",
            "DD-MMM-YYYY"
        ];

        return dayjs(date, formats, true);
    };

    const calculateDuration = (startDate, endDate) => {

        let start = parseDate(startDate);
        let end = parseDate(endDate);

        let years = end.diff(start, "year");
        start = start.add(years, "year");

        let months = end.diff(start, "month");
        start = start.add(months, "month");

        let days = end.diff(start, "day");

        let result = [];

        if (years) result.push(`${years} year${years > 1 ? "s" : ""}`);
        if (months) result.push(`${months} month${months > 1 ? "s" : ""}`);
        if (days) result.push(`${days} day${days > 1 ? "s" : ""}`);

        return result.join(", ");
    };

    function matchKeywords(text, keywords) {
        const escaped = keywords.map(k =>k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
        const regex = new RegExp(`(^|\\W)(${escaped.join("|")})(\\W|$)`, "i")
        return regex.test(text)
    }

    const monthwise = {}
    let prevBalance = null
    let volatilitySum = 0
    let volatilityCount = 0
    transactionDetails.forEach((item) => {
        const balance = Number(item.balance) || 0
        const debit = Number(item.debit) || 0
        const credit = Number(item.credit) || 0
        const description = (item.description || "").toLowerCase();
        // eslint-disable-next-line no-unused-vars
        const [day, month, year] = item.date.split("-")

        const monthNames = ["Jan","Feb","Mar","Apr","May","June","July","Aug","Sept","Oct","Nov","Dec"];

        const loanCreditKeywords = ["loan disbursement","loan disb","loan credit","pl disb","personal loan disb","pl credit","hl disb","home loan disb","home loan credit","vehicle loan disb","auto loan disb","loan a/c credit","loan account credit","loan proceeds","loan amount credited","loan release","loan disburse","loan transfer credit","od limit credit","overdraft credit","cc limit credit","loan booking credit"];

        const internalTransferKeywords = ["transfer","trf","internal transfer","internal trf","account transfer","a/c transfer","ac transfer","fund transfer","fund trf","self transfer","own account transfer","ib transfer","internet banking transfer","online transfer","mobile banking transfer","standing instruction","si","account adjustment","internal adjustment","contra","bank adjustment","system"];

        const interestReceivedKeywords = ["interest credit","interest received","interest cr","savings interest","savings interest credit","sb interest","sb interest credit","fd interest","fd interest credit","fixed deposit interest","rd interest","recurring deposit interest","interest payout","interest payment","interest adj credit","interest adjustment credit","interest reversal","interest refund","bank interest credit"];

        const totalObligationKeywords = ["emi","loan emi","emi payment","loan repayment","loan instalment","loan installment","term loan","pl emi","personal loan emi","hl emi","home loan emi","vehicle loan emi","auto loan emi","loan recovery","loan deduction","ecs","ecs debit","ecs dr","nach","nach debit","nach dr","ach","ach debit","ach dr","auto debit","auto-debit","standing instruction","si dr","credit card payment","cc payment","card payment","cr card payment","credit card bill","bajaj finance","hdb financial","tata capital","l&t finance","hero fincorp","shriram finance","aditya birla finance"];


        const monthWord = monthNames[parseInt(month) - 1]
        const monthKey = `${monthWord} ${year}`
        
        if (!monthwise[monthKey]) {
            monthwise[monthKey] = {
                month: monthKey,
                totalBalance: balance,
                debit:0,
                credit:0,
                creditCount:0,
                debitCount:0,
                loanCredit:0,
                internalCredit:0,
                interestRecieved:0,
                monthlyObligation:0,
                count: 1,
                circularCreditCount: 0,
                dailyChangeSum: 0,
                dailyChangeCount: 0,
                volatilityScore: 0,
                monthlyIncome:null,
                transactions:[],
            }
        }

        monthwise[monthKey].totalBalance += balance
        monthwise[monthKey].count += 1
        if (credit > 0) {
            monthwise[monthKey].credit += credit;
            monthwise[monthKey].creditCount += 1;
        }

        if (debit > 0) {
            monthwise[monthKey].debit += debit;
            monthwise[monthKey].debitCount += 1;
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

        if (matchKeywords(description, interestReceivedKeywords)) {
            monthwise[monthKey].interestRecieved += credit;
        }

        if (matchKeywords(description, totalObligationKeywords)) {
            monthwise[monthKey].monthlyObligation += debit;
        }

        if (prevBalance !== null && prevBalance !== 0) {

            const changePercent =
                ((balance - prevBalance) / prevBalance) * 100

            volatilitySum += Math.abs(changePercent)
            volatilityCount += 1
        }

        prevBalance = balance

        monthwise[monthKey].monthlyIncome = monthwise[monthKey].credit - monthwise[monthKey].loanCredit - monthwise[monthKey].internalCredit - monthwise[monthKey].interestRecieved
        monthwise[monthKey].transactions.push(item)
    })

    const volatilityScore = volatilityCount
        ? volatilitySum / volatilityCount
        : 0

    Object.values(monthwise).forEach(m => {
        m.monthlyIncome =
            m.credit
            - m.loanCredit
            - m.internalCredit
            - m.interestRecieved
    })

    // totals
    let totalIncome = 0
    let totalObligation = 0
    let monthCount = 0
    Object.values(monthwise).forEach(m => {
        totalIncome += m.monthlyIncome || 0
        totalObligation += m.monthlyObligation || 0
        monthCount++
    })

    // averages
    const avgMonthlyIncome = monthCount ? totalIncome / monthCount : 0
    const avgMonthlyObligation = monthCount ? totalObligation / monthCount : 0

    // FOIR
    const overallFoirScore = avgMonthlyIncome > 0 ? (avgMonthlyObligation / avgMonthlyIncome) * 100 : 0

    const data = Object.values(monthwise).map((item) => ({
        month: item.month,
        value: Number((item.totalBalance / item.count).toFixed(2))
    }))

    const debit_credit = Object.values(monthwise).map((item) => ({
        month: item.month,
        debit: Number(item.debit.toFixed(2)),
        credit: Number(item.credit.toFixed(2)),
    }))

    const equal_debit_credit = Object.values(monthwise).filter(
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
    
    const rtgsPaymentKeywords = [  "rtgs",  "rtgs payment",  "rtgs transfer",  "rtgs outward",  "rtgs out",  "rtgs txn",  "rtgs trf",  "rtgs remittance",  "by rtgs",  "rtgs paid",  "rtgs dr",  "rtgs debit",  "rtgs outward remittance",  "rtgs customer transfer",  "rtgs fund transfer",  "rtgs payment to",  "rtgs transfer to",  "rtgs outward payment"];
    const cashDepositKeywords = ["cash deposit","cash dep","cash deposited","by cash","cash received","cdm deposit","cdm cash dep","cdm dep","branch cash deposit","brn cash dep","cash counter deposit","cash counter","teller deposit","teller cash dep","cash lodgement","cash lodgment","self cash deposit","deposit by cash","cash credit"];
    const atmWithdrawalKeywords = ["atm","atm wdl","atm withdrawal","atm cash","cash withdrawal atm","cash wd","cash wdl","cash withdrawal","atm-cash","atm cash withdrawal","atm withdrawal self","self atm","self withdrawal","atm txn","atm trxn","atm transaction","atm debit","atm dr","atm withdraw","card withdrawal","card cash withdrawal","card wdl","debit card atm","dc atm withdrawal","dc wdl","nfs atm withdrawal","nfs cash withdrawal","atm nfs","atm-nfs","nfs wdl","atm pos cash","atm withdrawal charges","atm charges"];
    const taxKeywords = ["gst","gst payment","cgst","sgst","igst","tds","income tax","tax payment","advance tax","self assessment tax","challan","tax deposit"];
    const salaryKeywords = ["salary","sal","salary credit","sal credit","sal cr","salary cr","salary payment","salary deposit","payroll","payroll credit","net salary","monthly salary","salary for","sal for","salary transfer","sal transfer","salary processed","salary via","salary ach","salary neft","salary imps","salary rtgs"];


    
    const atmWithdrawalAbove2k = useMemo(() => {
        return transactionDetails.filter(item => 
            matchKeywords(item.description?.toLowerCase() || "", atmWithdrawalKeywords) && item.debit >= 2000
        )
    },[transactionDetails])

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
    
    
    const atmWithdrawalAbove20k = useMemo(() => {
        return transactionDetails.filter(item => 
            matchKeywords(item.description?.toLowerCase() || "", atmWithdrawalKeywords) && item.debit >= 20000
        )
    },[transactionDetails])

    
    
    let previousBalance = null;
    
    const balanceVsComputedBalance = Object.values(monthwise)
        .flatMap(m => m.transactions)
        .map((txn) => {
    
          const debit = txn.debit || 0;
          const credit = txn.credit || 0;
          const balance = txn.balance || 0;
    
          const computedBalance =
            previousBalance !== null ? previousBalance - debit + credit : null;
    
          const gap =
            computedBalance !== null ? Number((balance - computedBalance).toFixed(2)) : null;
    
          const mismatch =
            computedBalance !== null && Math.abs(gap) > 1;
    
          previousBalance = balance;
    
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

        const salaryChangeCount = useMemo(() => {

            const tolerance = 2000;


            const isSalary = (desc, amount) => {
                if (!desc) return false;
                const text = desc.toLowerCase();
                return salaryKeywords.some(k => text.includes(k)) && amount > 2000;
            };

            // Step 1: filter salary transactions
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

            // Step 3: monthly salary (max per month)
            const monthwise = Object.entries(monthMap).map(([month, values]) => ({
                month,
                income: Math.max(...values)
            }));

            // Step 4: sort months
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

            //  Step 5: count changes
            let changeCount = 0;

            for (let i = 1; i < months.length; i++) {
                const prev = months[i - 1].income;
                const curr = months[i].income;

                if (Math.abs(curr - prev) > tolerance) {
                    changeCount++;
                }
            }

            return changeCount;

        }, [transactionDetails]);

    // -------------------
    const chartRef = useRef(null)
    const chartRefTwo = useRef(null)

    useLayoutEffect(() => {

        const root = am5.Root.new(chartRef.current)

        root.setThemes([am5themes_Animated.new(root)])

        const chart = root.container.children.push(
            am5xy.XYChart.new(root, {
                paddingLeft: 0,
                wheelX: "panX",
                wheelY: "zoomX",
                layout: root.verticalLayout
            })
        )
        var cursor = chart.set("cursor", am5xy.XYCursor.new(root, {}));
        cursor.lineY.set("visible", false);

        const xRenderer = am5xy.AxisRendererX.new(root, {minGridDistance: 10})

        // rotate labels
        xRenderer.labels.template.setAll({
            rotation: -45,
            centerY: am5.p50,
            centerX: am5.p100,
            fontSize: 12
        })
        const xAxis = chart.xAxes.push(
            am5xy.CategoryAxis.new(root, {
                categoryField: "month",
                renderer: xRenderer,
            })
        )
        

        const yAxis = chart.yAxes.push(
            am5xy.ValueAxis.new(root, {
                renderer: am5xy.AxisRendererY.new(root, {})
            })
        )

        xAxis.get("renderer").grid.template.setAll({ visible: false });

        const series = chart.series.push(
            am5xy.ColumnSeries.new(root, {
                name: "Average Balance",
                xAxis,
                yAxis,
                valueYField: "value",
                categoryXField: "month",
                tooltip: am5.Tooltip.new(root, {
                    labelText: "{valueY}"
                })
            })
        )

        series.columns.template.setAll({ cornerRadiusTL: 5, cornerRadiusTR: 5, strokeOpacity: 0 });
        series.columns.template.adapters.add("fill", function (fill, target) {
            return chart.get("colors").getIndex(series.columns.indexOf(target));
        });

        series.columns.template.adapters.add("stroke", function (stroke, target) {
            return chart.get("colors").getIndex(series.columns.indexOf(target));
        });

        xAxis.data.setAll(data)
        series.data.setAll(data)
        if (root._logo) {
            root._logo.dispose();
        }
        return () => {
            root.dispose()
        }

    }, [transactionDetails])


    // -------------------- Debit Credit ------------------

    useLayoutEffect(() => {

        const root = am5.Root.new(chartRefTwo.current);

        root.setThemes([
        am5themes_Animated.new(root)
        ]);

        const chart = root.container.children.push(
        am5xy.XYChart.new(root, {
            panX: false,
            panY: false,
            paddingLeft: 0,
            wheelX: "panX",
            wheelY: "zoomX",
            layout: root.verticalLayout
        })
        );

        const legend = chart.children.push(
        am5.Legend.new(root, {
            centerX: am5.p50,
            x: am5.p50
        })
        );

        const xRenderer = am5xy.AxisRendererX.new(root, {
            cellStartLocation: 0.1,
            cellEndLocation: 0.9,
            minorGridEnabled: true,
            minGridDistance: 10
        });

        xRenderer.labels.template.setAll({
            rotation: -45,
            centerY: am5.p50,
            centerX: am5.p100,
            fontSize: 12
        })

        const xAxis = chart.xAxes.push(
        am5xy.CategoryAxis.new(root, {
            categoryField: "month",
            renderer: xRenderer,
            tooltip: am5.Tooltip.new(root, {})
        })
        );

        xRenderer.grid.template.setAll({
            location: 1
        });

        xAxis.data.setAll(debit_credit);

        const yAxis = chart.yAxes.push(
        am5xy.ValueAxis.new(root, {
            renderer: am5xy.AxisRendererY.new(root, {
            strokeOpacity: 0.1
            })
        })
        );
        xAxis.get("renderer").grid.template.setAll({
            visible: false
        });

        yAxis.get("renderer").grid.template.setAll({
            visible: true
        });

        function makeSeries(name, fieldName) {

            const series = chart.series.push(
                am5xy.ColumnSeries.new(root, {
                name,
                xAxis,
                yAxis,
                valueYField: fieldName,
                categoryXField: "month"
                })
            );

            series.columns.template.setAll({
                tooltipText: "{name}, {valueY}",
                width: am5.percent(90),
                tooltipY: 0,
                strokeOpacity: 0
            });

            series.data.setAll(debit_credit);

            series.bullets.push(() =>
                am5.Bullet.new(root, {
                sprite: am5.Label.new(root, {
                    fill: root.interfaceColors.get("alternativeText"),
                    centerY: am5.p50,
                    centerX: am5.p50,
                    populateText: true
                })
                })
            );

            legend.data.push(series);

            series.appear();
        }

        makeSeries("Withdrawals", "debit");
        makeSeries("Deposits", "credit");

        chart.appear(1000, 100);
        if (root._logo) {
            root._logo.dispose();
        }
        return () => {
        root.dispose();
        };

    }, [transactionDetails]);

    const durationResult = calculateDuration(accountDetails?.statement_period?.from, accountDetails?.statement_period?.to);
    return (
        <>
            <div className="card grid grid-cols-6 gap-4">
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>{volatilityScore.toFixed(2) || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>VOLATILITY SCORE</p>
                </div>
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>{overallFoirScore.toFixed(2) || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>FOIR</p>
                </div>
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>{circularTransactionCount || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>CIRCULAR TXNS</p>
                </div>
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>{bounceChqCount || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>BOUNCED CHEQUES</p>
                </div>
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>{transactionCount || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>TRANSACTIONS</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>{firstDate} - {lastDate}</p>
                </div>
                <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
                    <p className='font-semibold text-2xl text-[#084b6f] text-center'>₹ {averageMonthBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) || 0}</p>
                    <p className='text-[10px] font-semibold text-gray-500 text-center'>MONTHLY AVG BALANCE</p>
                </div>
            </div>
            <div className="pt-2 grid grid-cols-2 gap-2">
                <div className="col-span-1">
                    <div className="card">
                        <h1 className='text-base text-[#084b6f] font-semibold mb-2'>Bank account details</h1>
                        <div className='max-h-90 overflow-auto w-full'>
                            <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                                <tbody>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px] w-[50%]">Bank name</td>
                                        <td className="px-3 py-2 text-[14px] w-[50%]">{accountDetails?.bank_name || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">IFSC & MICR Code</td>
                                        <td className="px-3 py-2 text-[14px]">IFSC: <span className='font-semibold'>{accountDetails?.ifsc || "-"}</span>, MICR: <span className='font-semibold'>{accountDetails?.micr || "-"}</span></td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">IFSC branch name & address</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.branch || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account number</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.account_number || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account type</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.acc_type || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Statement period</td>
                                        <td className="px-3 py-2 text-[14px]">{durationResult} ({accountDetails?.statement_period.from || "-"} - {accountDetails?.statement_period.to || "-"})</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account holder</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.account_holder || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">PAN</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.pan || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Account holder address</td>
                                        <td className="px-3 py-2 text-[14px]">{accountDetails?.address || "-"}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Cash Deposits in range (9-10)L</td>
                                        <td className="px-3 py-2 text-[14px]">{cashDeposit9to10L || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Cash Deposits in range (40-50)k</td>
                                        <td className="px-3 py-2 text-[14px]">{cashDeposit40to50k || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">ATM Withdrawals above ₹2,000</td>
                                        <td className="px-3 py-2 text-[14px]">{atmWithdrawalAbove2k.length || 0}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div className="col-span-1">
                    <div className="card">
                        <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Irregularities</h2>
                        <div className='max-h-90 overflow-auto w-full'>
                            <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                                <thead>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <th className="px-3 py-2 text-[14px] w-[50%] sticky -top-1 bg-white">Activity</th>
                                        <th className="px-3 py-2 text-[14px] w-[50%] sticky -top-1 bg-white">Incidences</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">RTGS Payments below ₹2,00,000</td>
                                        <td className="px-3 py-2 text-[14px]">{rtgsbelow.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">More Cash deposits vs Salary</td>
                                        <td className="px-3 py-2 text-[14px]">{highCashDeposits.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Round Figure Tax Payments</td>    
                                        <td className="px-3 py-2 text-[14px]">{roundFigureTaxPayments.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Equal Debits & Credits</td>
                                        <td className="px-3 py-2 text-[14px]">{equal_debit_credit.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">ATM withdrawals above ₹20,000</td>
                                        <td className="px-3 py-2 text-[14px]">{atmWithdrawalAbove20k.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Balance vs Computed balance mismatch</td>
                                        <td className="px-3 py-2 text-[14px]">{balanceVsComputedBalance.length || 0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Salary Credit Amount remains unchanged over extended period</td>
                                        <td className="px-3 py-2 text-[14px]">{salaryChangeCount > 0 ? salaryChangeCount :  0}</td>
                                    </tr>
                                    <tr className="bg-neutral-primary border-b border-gray-200">
                                        <td className="px-3 py-2 text-[14px]">Parties present in both debits and credits</td>
                                        <td className="px-3 py-2 text-[14px]">{partiesPresentDebitCredit.length || 0}</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div className="col-span-1">
                    <div className="card">
                        <h3 className='text-base text-[#084b6f] font-semibold mb-2'>Monthly Average Balance</h3>
                        <div ref={chartRef} className='w-full h-90' />
                    </div>
                </div>
                <div className="col-span-1">
                    <div className="card">
                        <h3 className='text-base text-[#084b6f] font-semibold mb-2'>Total Debit and Credit</h3>
                        <div ref={chartRefTwo} className='w-full h-90' />
                    </div>
                </div>
            </div>
        </>
    )
}

export default StepTwo