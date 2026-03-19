import React,{useLayoutEffect,useRef,useMemo} from 'react'
import * as am5 from "@amcharts/amcharts5";
import * as am5xy from "@amcharts/amcharts5/xy";
import * as am5percent from "@amcharts/amcharts5/percent";
import am5themes_Animated from "@amcharts/amcharts5/themes/Animated";

function StepSeven({reportData}) {
  const transactionDetails = reportData.transaction

  const chartRef = useRef(null)
  const chartRefTwo = useRef(null)
  const chartRefThree = useRef(null)
  const chartRefFour = useRef(null)
  const chartRefFive = useRef(null)

  function matchKeywords(text, keywords) {
    const escaped = keywords.map(k =>k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    const regex = new RegExp(`(^|\\W)(${escaped.join("|")})(\\W|$)`, "i")
    return regex.test(text)
  }

  const modeKeywords = {
    RTGS: ["rtgs"],
    UPI: ["upi", "p2a", "p2p", "@ok", "@ybl", "@ibl", "@axl"],
    NEFT: ["neft"],
    IMPS: ["imps"],
    CHEQUE: ["chq", "cheque", "clg", "clearing"],
    CASH: ["cash dep", "cash deposit", "cash wd", "cash withdrawal"],
    NACH: ["nach", "ecs", "ach"],
    ATM: ["atm", "wdl atm", "atm wdl"],
  };

  const modeSummary = {
    RTGS: { withdrawal: 0, deposit: 0 },
    UPI: { withdrawal: 0, deposit: 0 },
    NEFT: { withdrawal: 0, deposit: 0 },
    IMPS: { withdrawal: 0, deposit: 0 },
    CHEQUE: { withdrawal: 0, deposit: 0 },
    CASH: { withdrawal: 0, deposit: 0 },
    NACH: { withdrawal: 0, deposit: 0 },
    ATM: { withdrawal: 0, deposit: 0 }
  };

  const labelMap = {
    ow_funds_transfer: "O/W Funds Transfer",
    iw_funds_transfer: "I/W Funds Transfer",
    transfer_to_self: "Transfer To Self",
    utilities: "Utilities",
    loan: "Loan",
    insurance: "Insurance",
    cash_atm: "Cash & ATM",
    interest: "Interest",
    insurance_pension:"Insurance Pension",
    investment_proceeds: "Investment Proceeds"
  };

  const internationalWireKeywords = ["swift","wire transfer","international transfer","intl transfer","foreign remittance","inward remittance","outward remittance","remittance","tt remittance","telegraphic transfer","tt credit","tt debit","forex transfer","foreign inward remittance","foreign outward remittance","swift transfer","swift credit","swift debit","remit","remitly","wise transfer","transferwise","western union","moneygram","xoom","paypal","payoneer","foreign credit","foreign inward","foreign outward","fx remittance","fcnr credit"];

  const cashDepositKeywords = ["cash deposit","cash dep","cdm deposit","atm deposit","cash at atm","by cash","cash counter","cash received"];

  // Outflow
  const owFundsTransferKeywords = ["upi","imps","neft","rtgs","p2a","p2p","fund transfer","ft","trf","transfer","by transfer","online transfer","ib transfer","to account","a/c transfer","account transfer","gpay","google pay","phonepe","paytm","amazon pay","mobikwik","bhim","upi-dr","upi debit","imps dr","neft dr","rtgs dr","imps transfer"];
  const transferToSelfKeywords = ["self transfer","to self","own account","own a/c","self","internal transfer","sweep transfer","sweep in","sweep out","account transfer self","inter account transfer"];
  const utilitiesKeywords = ["electricity","power","water bill","gas bill","broadband","wifi","internet","mobile recharge","postpaid","prepaid","dth","bill payment","utility","billpay","electric","tneb","bescom","mseb","torrent power","bsnl","jio","airtel","vodafone","vi","tata power","adani electricity"];
  const loanKeywords = ["loan","emi","emi payment","emi debit","loan repayment","home loan","personal loan","vehicle loan","auto loan","emi ecs","ecs debit","nach debit","ach debit","loan emi","emi/ecs","emi payment debit"];
  const insuranceKeywords = ["insurance","lic","premium","policy","policy premium","ins premium","icici pru","hdfc life","sbi life","max life","tata aia","bajaj allianz","insurance premium","policy payment"];

  // Daily Avg Balance

  const totalBalance = transactionDetails.reduce((sum, t) => sum + t.balance, 0);
  const avgBalance = totalBalance / transactionDetails.length;

  // Max Balance
  const maxBalance = Math.max(...transactionDetails.map(item => Number(item.balance)));

  // Min Balance
  const minBalance = Math.min(...transactionDetails.map(item => Number(item.balance)));

  // Days Gap between Min and Max balance
  const maxTxn = transactionDetails.reduce((max, item) =>
    Number(item.balance) > Number(max.balance) ? item : max
  );
  
  const minTxn = transactionDetails.reduce((min, item) =>
    Number(item.balance) < Number(min.balance) ? item : min
  );
  

  const parseDate = (d) => {
    if (!d) return null;

    const [day, month, year] = d.split("-"); // 🔥 FIX HERE

    return new Date(
      Number(year),
      Number(month) - 1,
      Number(day)
    );
  };

  const d1 = parseDate(maxTxn?.date);
  const d2 = parseDate(minTxn?.date);

  let daysGap = 0;

  if (d1 && d2) {
    daysGap = Math.abs(d1 - d2) / (1000 * 60 * 60 * 24);
  }

  // Transactions count

  const transactionCount = useMemo(() => {
    return transactionDetails.filter(item => item?.balance != null).length;
  }, [transactionDetails]);
  const firstDate = transactionDetails[0]?.date.split("-").join("/") || "-";
  const lastDate = transactionDetails[transactionDetails.length - 1]?.date.split("-").join("/") || "-";



  // Max Dormant days

  const sorted = [...transactionDetails].sort(
    (a, b) => parseDate(a.date) - parseDate(b.date)
  );


  // AML Score ---------------------------------------------------------------


  // -------------------------------
  // 🔹 1. Quick Withdrawal Count
  // -------------------------------
  let quickWithdrawalCount = 0;

  for (let i = 0; i < sorted.length; i++) {
    const curr = sorted[i];
    const currDate = parseDate(curr.date);
    const credit = Number(curr.credit) || 0;

    if (credit > 0) {
      for (let j = i + 1; j < sorted.length; j++) {
        const next = sorted[j];
        const nextDate = parseDate(next.date);

        const gapDays = (nextDate - currDate) / (1000 * 60 * 60 * 24);

        if (gapDays > 1) break;

        if (Number(next.debit) > 0) {
          quickWithdrawalCount++;
          break;
        }
      }
    }
  }

  // -------------------------------
  //  2. Same-Day In-Out Count
  // -------------------------------
  let sameDayInOutCount = 0;

  const dateMap = {};

  sorted.forEach((txn) => {
    const d = txn.date;

    if (!dateMap[d]) {
      dateMap[d] = { credit: 0, debit: 0 };
    }

    dateMap[d].credit += Number(txn.credit) || 0;
    dateMap[d].debit += Number(txn.debit) || 0;
  });

  Object.values(dateMap).forEach((val) => {
    if (val.credit > 0 && val.debit > 0) {
      sameDayInOutCount++;
    }
  });


  
  // 2. Find max gap
  let maxDormantDays = 0;
  let maxGapInfo = {};

  for (let i = 1; i < sorted.length; i++) {
    const prev = parseDate(sorted[i - 1].date);
    const curr = parseDate(sorted[i].date);

    const gap = (curr - prev) / (1000 * 60 * 60 * 24);

    if (gap > maxDormantDays) {
      maxDormantDays = gap;
      maxGapInfo = {
        from: sorted[i - 1].date,
        to: sorted[i].date,
      };
    }
  }

  // -------------------------------
  //  3. Large Deposit Count
  // -------------------------------
  const credits = sorted.map(t => Number(t.credit) || 0).filter(c => c > 0);

  const avgCredit =
    credits.reduce((a, b) => a + b, 0) / (credits.length || 1);

  let largeDepositCount = credits.filter(c => c > avgCredit * 3).length;

  // -------------------------------
  //  4. Round Transaction %
  // -------------------------------
  let roundCount = 0;

  sorted.forEach((txn) => {
    const amt = Number(txn.credit) || Number(txn.debit) || 0;

    if (amt > 0 && amt % 1000 === 0) {
      roundCount++;
    }
  });

  const roundTxnPercentage = roundCount / sorted.length;

  // -------------------------------
  //  5. Transactions Per Day (Velocity)
  // -------------------------------
  const txnPerDay = {};

  sorted.forEach((txn) => {
    txnPerDay[txn.date] = (txnPerDay[txn.date] || 0) + 1;
  });

  const maxTxnsPerDay = Math.max(...Object.values(txnPerDay));


  // -------------------------------
  // 🔥 FINAL AML SCORE
  // -------------------------------
  let score = 0;

  // weights
  if (quickWithdrawalCount >= 3) score += 25;
  if (sameDayInOutCount >= 2) score += 20;
  if (largeDepositCount >= 2) score += 15;
  if (roundTxnPercentage > 0.5) score += 10;
  if (maxTxnsPerDay > 10) score += 15;
  if (maxDormantDays > 60) score += 15;

  score = Math.min(score, 100);


  // Suspicious activities

  const sortedTransactions = [...transactionDetails].sort(
    (a,b) => new Date(a.date) - new Date(b.date)
  );

  let bigDepositWithdrawal = 0;
  let multipleDepositBigWithdrawal = 0;
  let highValueSpending = 0;
  let internationalWireTransfers = 0;

  const depositsByDate = {};

  for (let i = 0; i < sortedTransactions.length; i++) {

    const txn = sortedTransactions[i];
    const desc = txn.description?.toLowerCase() || "";

    const credit = Number(txn.credit) || 0;
    const debit = Number(txn.debit) || 0;

    // High value spending
    if (debit >= 100000) {
      highValueSpending++;
    }

    // International wire transfers
    if (matchKeywords(desc, internationalWireKeywords)) {
      internationalWireTransfers++;
    }

    // Cash deposits per day
    if (credit > 0 && matchKeywords(desc, cashDepositKeywords)) {
      depositsByDate[txn.date] = (depositsByDate[txn.date] || 0) + 1;
    }

    // Big deposit followed by withdrawal
    if (i < sortedTransactions.length - 1) {

      const next = sortedTransactions[i+1];
      const nextDebit = Number(next.debit) || 0;

      if (credit >= 50000 && nextDebit > 0) {
        bigDepositWithdrawal++;
      }
    }

    // Multiple deposits followed by big withdrawal
    if (i >= 2) {

      const d1 = Number(sortedTransactions[i-2].credit) || 0;
      const d2 = Number(sortedTransactions[i-1].credit) || 0;

      if (d1 > 0 && d2 > 0 && debit >= 50000) {
        multipleDepositBigWithdrawal++;
      }
    }
  }

  const multipleCashDeposits = Object.values(depositsByDate)
    .filter(v => v > 1).length;

  const activitySummary = {
    bigDepositWithdrawal,
    multipleDepositBigWithdrawal,
    multipleCashDeposits,
    highValueSpending,
    internationalWireTransfers
  };


  // -----------------


  const outflowCategories = {
    ow_funds_transfer: owFundsTransferKeywords,
    transfer_to_self: transferToSelfKeywords,
    utilities: utilitiesKeywords,
    loan: loanKeywords,
    insurance: insuranceKeywords
  };

  const outflowSummary = {
    ow_funds_transfer: 0,
    transfer_to_self: 0,
    utilities: 0,
    loan: 0,
    insurance: 0
  };


  // Inflow
  const iwFundsTransferKeywords = ["upi", "imps", "neft", "rtgs","p2a", "p2p","by transfer", "fund transfer","ib transfer", "inward transfer","received from", "from a/c","gpay", "phonepe", "paytm","upi-cr", "upi credit","imps credit", "neft credit","rtgs credit"];
  const cashAtmDepositKeywords = ["cash deposit","cash dep","atm deposit","cdm deposit","cash at atm","cash received","by cash","branch deposit","cash counter"];
  const insurancePensionKeywords = ["insurance claim","claim settlement","lic maturity","policy maturity","annuity","pension","family pension","epfo","pf settlement","superannuation"];
  const interestKeywords = ["interest","int credit","sb interest","savings interest","interest credit","fd interest","rd interest","deposit interest"];
  const investmentKeywords = ["mutual fund redemption","mf redemption","dividend","share dividend","stock dividend","sip redemption","redemption proceeds","investment proceeds","bond redemption","ipo refund"];

  const inflowCategories = {
    iw_funds_transfer: iwFundsTransferKeywords,
    cash_atm: cashAtmDepositKeywords,
    insurance_pension: insurancePensionKeywords,
    interest: interestKeywords,
    investment_proceeds: investmentKeywords
  };

  const inflowSummary = {
    iw_funds_transfer: 0,
    cash_atm: 0,
    insurance_pension: 0,
    interest: 0,
    investment_proceeds: 0
  };
  

  const monthwise = {}
  transactionDetails.forEach((item) => {
    // eslint-disable-next-line no-unused-vars
    const [day, month, year] = item.date.split("-")

    const monthNames = ["Jan","Feb","Mar","Apr","May","June","July","Aug","Sept","Oct","Nov","Dec"];
    const debit = Number(item.debit) || 0
    const credit = Number(item.credit) || 0
    const monthWord = monthNames[parseInt(month) - 1]
    const monthKey = `${monthWord} ${year}`
    const desc = item.description?.toLowerCase() || "";
    if (!monthwise[monthKey]) {
      monthwise[monthKey] = {
        month: monthKey,
        debit:0,
        credit:0,
        txnCount:0,
      }
    }
    monthwise[monthKey].txnCount += 1;

    if (credit > 0) {
      monthwise[monthKey].credit += credit;
    }

    if (debit > 0) {
      monthwise[monthKey].debit += debit;
    }

    for (const mode in modeKeywords) {
      if (modeKeywords[mode].some(keyword => desc.includes(keyword))) {

        if (debit > 0) {
          modeSummary[mode].withdrawal += debit;
        }

        if (credit > 0) {
          modeSummary[mode].deposit += credit;
        }

        break;
      }
    }

    for (const category in outflowCategories) {
      if (outflowCategories[category].some(k => desc.includes(k))) {
        outflowSummary[category] += debit;
        break;
      }
    }

    for (const category in inflowCategories) {
      if (inflowCategories[category].some(k => desc.includes(k))) {
        inflowSummary[category] += credit;
        break;
      }
    }

  })


  // Inflow %
  const totalInflow = Object.values(inflowSummary).reduce((a,b)=>a+b,0);

  const inflowPercentage = Object.entries(inflowSummary).map(([key,val])=>({
    category:labelMap[key] || key,
    value: totalInflow ? ((val/totalInflow)*100).toFixed(2) : 0
  }));

  const inflowChart = inflowPercentage.map(item => ({
    category: item.category.replaceAll("_"," "),
    value: Number(item.value),
  }));



  // Outflow %
  const totalOutflow = Object.values(outflowSummary).reduce((a,b)=>a+b,0);

  const outflowPercentage = Object.entries(outflowSummary).map(([key,val])=>({
    category:labelMap[key] || key,
    value: totalOutflow ? ((val/totalOutflow)*100).toFixed(2) : 0
  }));

  const outflowChart = outflowPercentage.map(item => ({
    category: item.category.replaceAll("_"," "),
    value: Number(item.value),
  }));



  //  Txn Mode – Deposits & Withdrawals %

  const totalWithdrawal = Object.values(modeSummary).reduce((sum, m) => sum + m.withdrawal, 0);
  const totalDeposit = Object.values(modeSummary).reduce((sum, m) => sum + m.deposit, 0);

  const chartData = Object.entries(modeSummary).map(([mode, values]) => ({
    mode,
    withdrawal: totalWithdrawal ? Number(((values.withdrawal / totalWithdrawal) * 100).toFixed(2)) : 0,
    deposit: totalDeposit ? Number(((values.deposit / totalDeposit) * 100).toFixed(2)) : 0,
  }));



  // Overall monthly average vs  Txn Volume
  const monthTxn = Object.values(monthwise);

  const totalTxn = monthTxn.reduce((sum, m) => sum + m.txnCount, 0);

  const overallMonthlyAverage = Math.round(totalTxn / monthTxn.length);

  monthTxn.forEach(m => {
    m.overallMonthlyAverage = overallMonthlyAverage;
  });
  
  const overallVsTxn = monthTxn.sort((a, b) => {
    const parseMonth = (str) => new Date("1 " + str);
    return parseMonth(a.month) - parseMonth(b.month);
  });



  // Withdrawals and Deposits percentage
  const debit_credit = Object.values(monthwise).map((item) => ({
    month: item.month,
    debit: Number(item.debit.toFixed(2)),
    credit: Number(item.credit.toFixed(2)),
  }))


  useLayoutEffect(() => {

    const root = am5.Root.new(chartRef.current);

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
      centerX: am5.p50,
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


  // Overall Avg vs Txn Count

  useLayoutEffect(() => {

    const root = am5.Root.new(chartRefTwo.current);

    root.setThemes([am5themes_Animated.new(root)]);

    const chart = root.container.children.push(
      am5xy.XYChart.new(root, {
        panX: true,
        panY: true,
        wheelX: "panX",
        wheelY: "zoomX",
        layout: root.verticalLayout,
        pinchZoomX: true
      })
    );

    const data = overallVsTxn;

    // X Axis
    const xRenderer = am5xy.AxisRendererX.new(root, {
      minorGridEnabled: true,
      minGridDistance: 10
    });

    xRenderer.labels.template.setAll({
      rotation: -45,
      centerY: am5.p50,
      centerX: am5.p50,
      fontSize: 12
    })

    xRenderer.grid.template.set("location", 0.5);

    const xAxis = chart.xAxes.push(
      am5xy.CategoryAxis.new(root, {
        categoryField: "month",
        renderer: xRenderer,
      })
    );

    xAxis.data.setAll(data);

    // Y Axis
    const yAxis = chart.yAxes.push(
      am5xy.ValueAxis.new(root, {
        maxPrecision: 0,
        renderer: am5xy.AxisRendererY.new(root, {
          inversed: true
        })
      })
    );

    xAxis.get("renderer").grid.template.setAll({
      visible: false
    });

    yAxis.get("renderer").grid.template.setAll({
      visible: true
    });

    // Cursor
    const cursor = chart.set(
      "cursor",
      am5xy.XYCursor.new(root, {
        alwaysShow: false,
        xAxis: xAxis,
      })
    );

    cursor.lineY.set("visible", false);

    // Create series function
    const createSeries = (name, field) => {
      const series = chart.series.push(
        am5xy.LineSeries.new(root, {
          name: name,
          xAxis: xAxis,
          yAxis: yAxis,
          valueYField: field,
          categoryXField: "month",
          tooltip: am5.Tooltip.new(root, {
            pointerOrientation: "horizontal",
            labelText: "[bold]{name}[/]\n{categoryX}: {valueY}"
          })
        })
      );

      series.bullets.push(() =>
        am5.Bullet.new(root, {
          sprite: am5.Circle.new(root, {
            radius: 5,
            fill: series.get("fill")
          })
        })
      );

      series.data.setAll(data);
      series.appear(1000);
    };

    createSeries("Overall Monthly Avg", "overallMonthlyAverage");
    createSeries("Txn Count", "txnCount");

    // Legend
    const legend = chart.children.push(
      am5.Legend.new(root, {
        centerX: am5.p50,
        x: am5.p50
      })
    );

    legend.data.setAll(chart.series.values);

    chart.appear(1000, 100);
    if (root._logo) {
      root._logo.dispose();
    }
    return () => {
      root.dispose();
    };
  }, [transactionDetails]);


  // Top 5 Uses - Outflow %

  useLayoutEffect(() => {

    const root = am5.Root.new(chartRefThree.current);

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
      centerX: am5.p50,
      fontSize: 12
    })

    const xAxis = chart.xAxes.push(
      am5xy.CategoryAxis.new(root, {
        categoryField: "mode",
        renderer: xRenderer,
        tooltip: am5.Tooltip.new(root, {})
      })
    );

    xRenderer.grid.template.setAll({
      location: 1
    });

    xAxis.data.setAll(chartData);

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
            categoryXField: "mode"
          })
        );

        series.columns.template.setAll({
          tooltipText: "{name}: {valueY.formatNumber('#.00')}%",
          width: am5.percent(90),
          tooltipY: 0,
          strokeOpacity: 0
        });

        series.data.setAll(chartData);

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

    makeSeries("Withdrawals", "withdrawal");
    makeSeries("Deposits", "deposit");

    chart.appear(1000, 100);
    if (root._logo) {
      root._logo.dispose();
    }
    return () => {
    root.dispose();
    };

  }, [transactionDetails]);


  // Outflow

  useLayoutEffect(() => {

    const root = am5.Root.new(chartRefFour.current);

    root.setThemes([
      am5themes_Animated.new(root)
    ]);

    const chart = root.container.children.push(
      am5percent.PieChart.new(root, {
        layout: root.verticalLayout,
        innerRadius: am5.percent(50)
      })
    );

    const series = chart.series.push(
      am5percent.PieSeries.new(root, {
        valueField: "value",
        categoryField: "category",
        alignLabels: true
      })
    );

    series.labels.template.setAll({
      text: "{category}: {value}%"
    });

    series.slices.template.setAll({
      tooltipText: "{category}: {value}%"
    });

    series.data.setAll(outflowChart);

    const legend = chart.children.push(
      am5.Legend.new(root, {
        centerX: am5.percent(50),
        x: am5.percent(50),
        marginTop: 15,
        marginBottom: 15
      })
    );

    legend.data.setAll(series.dataItems);

    series.appear(1000, 100);
    if (root._logo) {
      root._logo.dispose();
    }
    return () => {
      root.dispose();
    };

  }, []);


  // Inflow

  useLayoutEffect(() => {

    const root = am5.Root.new(chartRefFive.current);

    root.setThemes([
      am5themes_Animated.new(root)
    ]);

    const chart = root.container.children.push(
      am5percent.PieChart.new(root, {
        layout: root.verticalLayout,
        innerRadius: am5.percent(50)
      })
    );

    const series = chart.series.push(
      am5percent.PieSeries.new(root, {
        valueField: "value",
        categoryField: "category",
        alignLabels: true
      })
    );

    series.labels.template.setAll({
      text: "{category}: {value}%"
    });

    series.slices.template.setAll({
      tooltipText: "{category}: {value}%"
    });

    series.data.setAll(inflowChart);

    const legend = chart.children.push(
      am5.Legend.new(root, {
        centerX: am5.percent(50),
        x: am5.percent(50),
        marginTop: 15,
        marginBottom: 15
      })
    );

    legend.data.setAll(series.dataItems);

    series.appear(1000, 100);
    if (root._logo) {
      root._logo.dispose();
    }
    return () => {
      root.dispose();
    };

  }, []);

  return (
    <>
      
      <div className="grid grid-cols-2 gap-2">
        <div className="col-span-2">
          <div className="card h-full grid grid-cols-7 gap-4">
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>{score || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>AML Risk Score</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>₹ {avgBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>Daily avg balance</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>₹ {maxBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>Max Balance</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>₹ {minBalance.toLocaleString("en-IN",{minimumFractionDigits: 2,maximumFractionDigits: 2}) || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>Min Balance</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>{daysGap || 0} days</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>Days Gap b/w Max & <br/> Min Balance</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>{transactionCount || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>Transactions</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>{firstDate} - {lastDate}</p>
            </div>
            <div className="col-span-1 border border-gray-300 px-1 pt-2 pb-2 rounded-lg">
              <p className='font-semibold text-2xl text-[#084b6f] text-center'>{maxDormantDays || 0}</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>MAX DORMANT DAYS</p>
              <p className='text-[10px] font-semibold text-gray-500 text-center uppercase'>{maxGapInfo.from} - {maxGapInfo.to}</p>
            </div>
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Suspicious Activities</h2>
            <div className='max-h-100 overflow-auto'>
              <table className="border border-gray-200 text-left rtl:text-right text-body w-full">
                  <thead className="text-body bg-neutral-secondary-soft border-b rounded-base border-gray-200">
                      <tr>
                          <th scope="col" className="px-3 py-2 font-medium text-[14px] w-[80%]">Activity</th>
                          <th scope="col" className="px-3 py-2 font-medium text-[14px]">Incidences</th>
                      </tr>
                  </thead>
                  <tbody>
                      <tr className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-2 text-[14px]">Big deposit followed by withdrawals on same or next day</td>
                          <td className="px-3 py-2 text-[14px]">{activitySummary.bigDepositWithdrawal}</td>
                      </tr>
                      <tr className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-2 text-[14px]">Multiple deposits followed by big withdrawal on same or next day</td>
                          <td className="px-3 py-2 text-[14px]">{activitySummary.multipleDepositBigWithdrawal}</td>
                      </tr>
                      <tr className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-2 text-[14px]">Multiple Cash/ ATM deposits on same day</td>
                          <td className="px-3 py-2 text-[14px]">{activitySummary.multipleCashDeposits}</td>
                      </tr>
                      <tr className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-2 text-[14px]">High value spending</td>
                          <td className="px-3 py-2 text-[14px]">{activitySummary.highValueSpending}</td>
                      </tr>
                      <tr className="bg-neutral-primary border-b border-gray-200">
                          <td className="px-3 py-2 text-[14px]">International wire transfers</td>
                          <td className="px-3 py-2 text-[14px]">{activitySummary.internationalWireTransfers}</td>
                      </tr>
                  </tbody>
              </table>
            </div>
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Monthly Deposits & Withdrawals (₹)</h2>
            <div ref={chartRef} className='w-full h-90' />
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Account Activity – Txn Volume vs Overall Monthly Avg</h2>
            <div ref={chartRefTwo} className='w-full h-90' />
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Txn Mode – Deposits & Withdrawals %</h2>
            <div ref={chartRefThree} className='w-full h-90' />
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Top 5 Uses - Outflow %</h2>
            <div ref={chartRefFour} className='w-full h-90' />
          </div>
        </div>
        <div className="col-span-1">
          <div className="card h-full">
            <h2 className='text-base text-[#084b6f] font-semibold mb-2'>Top 5 Uses - Inflow %</h2>
            <div ref={chartRefFive} className='w-full h-90' />
          </div>
        </div>
      </div>
    </>
  )
}

export default StepSeven