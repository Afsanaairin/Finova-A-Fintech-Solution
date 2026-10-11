'use strict';
let DATA = null;
let selectedAnomaly = null;
let anomalyFilter = 'all';
let activeCardInfo = null;
let pinnedCardInfo = null;
let cardInfoCloseTimer;
let serverHasPDF = null;
const $ = id => document.getElementById(id);
const fmt = x => x === null || x === undefined ? 'Not provided' : '$' + Math.abs(Number(x)).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});
const signed = x => (Number(x)<0 ? '−' : '') + fmt(x);
const text = (id,value) => {$(id).textContent = String(value)};
const friendlyMonth = iso => new Date(iso+'-01T00:00:00').toLocaleString('en-US',{month:'short',year:'numeric'});
const escapeHTML = value => String(value??'').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function notify(message, bad=false) { const box=$('alert');box.textContent=message;box.classList.remove('hidden');box.classList.toggle('error',bad);setTimeout(()=>box.classList.add('hidden'),7000);}
const pageInfo = {anomalies:['Anomaly Explorer','Find what changed. Understand why it matters.','Evidence-backed cost and invoice investigations.'],overview:['Overview','A clearer picture of your business.','From transactions to foresight. Understand what changed, what matters, and what comes next.'],forecast:['Forecast & Scenarios','Plan for what comes next.','Explore the cash implications of tomorrow’s decisions.'],subscriptions:['Subscriptions','Make every recurring dollar count.','Understand recurring expenses and price changes.'],transactions:['Transactions','Your money, line by line.','Transparent transaction analysis with an audit trail.'],wrapped:['Business Wrapped','Your financial story, reimagined.','FINOVA turns numbers into a meaningful business recap.']};
function switchPage(id){
 hideCardInfo();
 document.querySelectorAll('.page').forEach(el=>el.classList.toggle('hidden',el.id!==id));
 document.querySelectorAll('.nav-link').forEach(el=>el.classList.toggle('active',el.dataset.view===id));
 const [name,title,sub] = pageInfo[id];text('page-crumb',name);text('page-title',title);text('page-subtitle',sub);
 if(id==='overview'||id==='forecast') requestAnimationFrame(drawCharts);
 window.scrollTo({top:0,behavior:'smooth'});
}
async function getJSON(url,options={}){
 const {timeoutMs=45000,timeoutMessage='The request timed out. Check that FINOVA is running and try again.',...requestOptions}=options;
 const headers=new Headers(requestOptions.headers);
 if((requestOptions.method||'GET').toUpperCase()==='POST')headers.set('X-Finova-Request','1');
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeoutMs);
 try{
  const r=await fetch(url,{...requestOptions,headers,signal:controller.signal});let d;
  try{d=await r.json()}catch(e){if(e.name==='AbortError')throw e;throw new Error(r.status===401?'Sign in to FINOVA to continue.':'Server returned a non-JSON response.')}
  if(!r.ok)throw new Error(d.error||'Request failed');return d;
 }catch(e){if(e.name==='AbortError')throw new Error(timeoutMessage);throw e;}
 finally{clearTimeout(timer);}
}
function lineChart(host,rows, includeForecast=false){
 const el=$(host);if(!rows.length){el.textContent='Not enough data for this chart.';return;}
 const W=760,H=295,pL=65,pT=17,pR=16,pB=43,chartW=W-pL-pR,chartH=H-pT-pB;
 const vals=rows.flatMap(r=>[r.cash_in,r.cash_out]);const max=Math.max(...vals,1)*1.13;
 const x=i=>pL+chartW*i/Math.max(1,rows.length-1),y=v=>pT+chartH*(1-v/max);
 const labels=rows.map((r,i)=>i%Math.max(1,Math.ceil(rows.length/6))===0||i===rows.length-1?`<text x="${x(i)}" y="${H-11}" fill="#8794a6" font-size="11" text-anchor="middle">${escapeHTML(friendlyMonth(r.month))}</text>`:'').join('');
 const grid=Array.from({length:5},(_,i)=>{const v=max*i/4;const yy=y(v);return `<line x1="${pL}" y1="${yy}" x2="${W-pR}" y2="${yy}" stroke="#edf0f7" stroke-width="1"/><text x="${pL-10}" y="${yy+4}" fill="#91a0b2" font-size="10" text-anchor="end">${fmt(v)}</text>`}).join('');
 const pointPath=(key,kind)=>rows.map((r,i)=>`${i?'L':'M'} ${x(i)} ${y(r[key])}`).join(' ');
 const series=[['cash_in','#16b6a2'],['cash_out','#8a7bf4']].map(([key,col])=>`<path d="${pointPath(key)}" fill="none" stroke="${col}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`+rows.map((r,i)=>`<circle cx="${x(i)}" cy="${y(r[key])}" r="3" fill="${col}"><title>${escapeHTML(r.month)} ${key==='cash_in'?'Cash receipts':'Cash payments'} ${fmt(r[key])}</title></circle>`).join('')).join('');
 const boundary=includeForecast?`<line x1="${x(Math.max(0,rows.length-4))}" y1="${pT}" x2="${x(Math.max(0,rows.length-4))}" y2="${H-pB}" stroke="#a5aec0" stroke-dasharray="5 5"/><text x="${x(Math.max(0,rows.length-4))+6}" y="14" fill="#8b95a6" font-size="10">Forecast →</text>`:'';
 el.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Financial cash-flow trend chart">${grid}${labels}${boundary}${series}</svg>`;
}
function drawCharts(){if(!DATA)return;lineChart('cash-chart',DATA.monthly.slice(-12));lineChart('forecast-chart',DATA.forecast.length?[...DATA.monthly.slice(-6),...DATA.forecast]:[],true)}
function render(){if(!DATA)return;
 document.querySelectorAll('.financial-card').forEach(card=>toggleCardBreakdown(card,false));
 const d=DATA,t=d.totals,invoiceOnly=d.analysis_kind==='invoices'; text('company-title',d.company);text('report-date',invoiceOnly?`${d.invoice_count} customer invoices · evaluated as of ${d.as_of}`:`${d.reporting_period} · ${d.transaction_count.toLocaleString()} transactions · ${d.months_count} months`);
 $('invoice-overview').classList.toggle('hidden',!invoiceOnly);
 ['cash-metrics','cash-panels','revenue-note'].forEach(id=>$(id).classList.toggle('hidden',invoiceOnly));
 document.querySelectorAll('.nav-link').forEach(button=>{
   const unavailable=(invoiceOnly&&['forecast','transactions','wrapped'].includes(button.dataset.view))||(!d.forecast.length&&button.dataset.view==='forecast');
   button.disabled=unavailable;button.title=unavailable?'Provide a complete cash ledger with sufficient history to use this view.':'';
 });
 const scoped=d.data_scope&&d.data_scope!=='complete';
 $('data-scope-note').classList.toggle('hidden',!scoped);
 text('data-scope-note',invoiceOnly?'Customer invoice report. Invoice amounts do not establish cash received; cash balances and forecasts need transaction records.':'This report covers the uploaded records only. It does not establish your business’s complete cash flow or closing cash balance.');
 if(invoiceOnly){
   text('invoice-total',fmt(t.invoice_amount));text('invoice-outstanding',fmt(t.outstanding_invoices));text('invoice-overdue',t.overdue_invoices);
   text('invoice-unknown',`${t.unknown_invoice_balances} unknown payment balance(s); excluded from the subtotal.`);
   text('invoice-as-of',`As of ${d.as_of} · ${t.missing_invoice_due_dates} missing due date(s)`);
   $('invoice-table').innerHTML=d.invoices.map(i=>`<tr><td>${escapeHTML(i.customer)}<small>${escapeHTML(i.invoice)}</small></td><td>${escapeHTML(i.due||'Not provided')}</td><td>${escapeHTML(i.status)}</td><td class="right">${fmt(i.amount)}</td><td class="right">${fmt(i.outstanding)}</td></tr>`).join('');
 }
 text('billed-revenue',t.last_month_invoiced_revenue===null?'Not provided':fmt(t.last_month_invoiced_revenue));text('metric-income',fmt(t.last_month_cash_in));text('metric-expenses',fmt(t.last_month_cash_out));text('metric-net',signed(t.last_month_net));text('metric-balance',signed(t.closing_cash));
 text('income-trend',t.cash_in_change_pct===null?'Cash receipts, not sales revenue':`${t.cash_in_change_pct>0?'+':''}${t.cash_in_change_pct}% vs previous month`);
 text('expense-trend',t.expense_change_pct===null?'Uploaded outgoing payments':`${t.expense_change_pct>0?'+':''}${t.expense_change_pct}% vs previous month`);
 text('balance-note',d.has_opening_cash?'From supplied opening cash + ledger entries':'Provide opening cash and a complete cash ledger');
 const biggest=Math.max(...d.categories.map(c=>c.amount),1);
 $('category-bars').innerHTML=d.categories.slice(0,6).map(c=>`<div><div class="bar-label"><span>${escapeHTML(c.category)}</span><b>${fmt(c.amount)}</b></div><div class="bar-bg"><div class="bar-fill" style="width:${Math.max(1,100*c.amount/biggest)}%"></div></div></div>`).join('')||'<p>No expense categories found.</p>';
 $('insight-list').innerHTML=d.anomalies.slice(0,4).map(a=>`<button class="insight insight-link" type="button" data-anomaly="${escapeHTML(a.id)}"><div class="insight-icon">!</div><div><strong>${escapeHTML(a.type)} · ${escapeHTML(a.category)}</strong><p>${escapeHTML(a.message)}</p><small>Investigate evidence →</small></div></button>`).join('')||'<p>No notable anomalies detected.</p>';
 $('insight-list').querySelectorAll('[data-anomaly]').forEach(button=>button.addEventListener('click',()=>openAnomaly(button.dataset.anomaly)));
 renderAnomalies();
 const future=d.forecast[0];text('predicted-sales',fmt(future?.invoiced_revenue));text('future-in',fmt(future?.cash_in));text('future-out',fmt(future?.cash_out));text('future-net',signed(future?.net));text('future-ar',fmt(d.has_invoice_data?t.outstanding_invoices:null));
 $('invoice-list').innerHTML=d.overdue_invoices.slice(0,8).map(i=>`<div class="invoice"><div><strong>${escapeHTML(i.customer)}</strong> <span>· ${escapeHTML(i.invoice)} · due ${escapeHTML(i.due)}</span></div><b>${fmt(i.amount)} · ${i.overdue_days} days overdue</b></div>`).join('')||(d.has_invoice_data?'<p>No overdue invoices with known balances in this dataset.</p>':'<p>Customer invoice records were not provided.</p>');
 text('sub-count',d.has_subscription_data?d.subscriptions.length:'Not provided');text('sub-monthly',fmt(d.has_subscription_data?t.subscription_monthly:null));text('sub-annual',fmt(d.has_subscription_data?t.subscription_annual:null));
 $('subscription-list').innerHTML=d.subscriptions.map(s=>`<div class="subscription-row"><div class="service-icon">${escapeHTML((s.name||'?').slice(0,1))}</div><div class="service-name">${escapeHTML(s.name)}<small>Recurring monthly · Usage not known</small></div><div class="service-amount">${fmt(s.monthly_cost)}<small>per month</small></div><div class="review-tag ${s.price_increase===0?'ok':''}">${s.price_increase>0?`↑ ${fmt(s.price_increase)} price rise`:'No price change detected'}</div></div>`).join('')||'<div class="callout">No subscription sheet present in this upload.</div>';
 if(d.wrapped){text('wrap-income',fmt(d.wrapped.cash_in));text('wrap-expense',fmt(d.wrapped.cash_out));text('wrap-month',friendlyMonth(d.wrapped.biggest_expense_month));text('wrap-category',d.wrapped.largest_category);text('wrap-subs',fmt(d.has_subscription_data?d.wrapped.subscription_annual:null));}
 renderTransactions();updateScenario();window.FINOVAStory.setData(d.wrapped?d:null);requestAnimationFrame(drawCharts);
}
function openAnomaly(id){
  selectedAnomaly=id;
  anomalyFilter='all';
  document.querySelectorAll('.anomaly-filter').forEach(b=>b.classList.toggle('active',b.dataset.filter==='all'));
  switchPage('anomalies');
  renderAnomalies();
}
function renderAnomalies(){
  if(!DATA)return;
  const all=DATA.anomalies||[];
  text('anomaly-count',all.length);
  text('spike-count',all.filter(a=>a.type==='Spending spike').length);
 text('price-count',DATA.has_subscription_data?all.filter(a=>a.type==='Subscription increase').length:'Not provided');
 text('overdue-count',DATA.has_invoice_data?DATA.totals.overdue_invoices:'Not provided');
  renderFinancialCards();
  const visible=all.filter(a=>anomalyFilter==='all'||a.type===anomalyFilter);
  if(!visible.some(a=>a.id===selectedAnomaly))selectedAnomaly=visible.length?visible[0].id:null;
  $('anomaly-list').innerHTML=visible.map(a=>`<button class="anomaly-item ${a.id===selectedAnomaly?'selected':''}" type="button" data-anomaly="${escapeHTML(a.id)}">
    <span class="anomaly-type">${escapeHTML(a.type)}</span><strong>${escapeHTML(a.category)} <span>›</span></strong>
    <small>${escapeHTML(a.month)} · ${escapeHTML(a.message)}</small></button>`).join('') || '<p class="anomaly-empty">No flagged patterns in this category.</p>';
  $('anomaly-list').querySelectorAll('[data-anomaly]').forEach(b=>b.addEventListener('click',()=>{selectedAnomaly=b.dataset.anomaly;renderAnomalies();}));
  renderAnomalyDetail(visible.find(a=>a.id===selectedAnomaly));
}
function hideCardInfo(){
  clearTimeout(cardInfoCloseTimer);
  document.querySelectorAll('.financial-card-info').forEach(button=>button.setAttribute('aria-expanded','false'));
  document.querySelectorAll('.financial-card-tooltip').forEach(tip=>tip.classList.add('hidden'));
  activeCardInfo=null;pinnedCardInfo=null;
}
function positionCardInfo(card){
  const tip=card.querySelector('.financial-card-tooltip'),anchor=card.getBoundingClientRect();
  const bounds=tip.getBoundingClientRect(),below=anchor.bottom+8,above=anchor.top-bounds.height-8;
  tip.style.left=`${Math.max(16,Math.min(anchor.left,window.innerWidth-bounds.width-16))}px`;
  tip.style.top=`${Math.max(16,Math.min(below+bounds.height<=window.innerHeight-16?below:above,window.innerHeight-bounds.height-16))}px`;
}
function showCardInfo(card,pin=false){
  if(activeCardInfo!==card){hideCardInfo();activeCardInfo=card;}
  clearTimeout(cardInfoCloseTimer);
  if(pin)pinnedCardInfo=card;
  card.querySelector('.financial-card-tooltip').classList.remove('hidden');
  card.querySelector('.financial-card-info').setAttribute('aria-expanded','true');
  positionCardInfo(card);
}
function toggleCardBreakdown(card,expanded){
  const button=card.querySelector('.financial-card-toggle');
  const show=expanded??button.getAttribute('aria-expanded')!=='true';
  hideCardInfo();
  button.setAttribute('aria-expanded',String(show));
  button.querySelector('span').textContent=show?'Hide breakdown':'Show breakdown';
  button.querySelector('b').textContent=show?'⌃':'⌄';
  card.querySelector('.financial-card-breakdown').classList.toggle('hidden',!show);
}
function renderFinancialCards(){
  hideCardInfo();
  const d=DATA,t=d.totals,latest=d.monthly.at(-1),previous=d.monthly.at(-2),all=d.anomalies||[];
  const spikes=all.filter(a=>a.type==='Spending spike'),prices=all.filter(a=>a.type==='Subscription increase');
  const invoiceFlag=all.find(a=>a.type==='Overdue invoices');
  const invoiceRows=d.analysis_kind==='invoices'?(d.invoices||[]).filter(i=>i.overdue_days>0).map(i=>({...i,amount:i.outstanding})):(d.overdue_invoices||[]);
  const amount=value=>value===null||value===undefined?'Not provided':Number(value).toLocaleString('en-US',{style:'currency',currency:'USD'});
  const row=(label,value,total=false)=>`<div class="financial-breakdown-row${total?' financial-breakdown-total':''}"><span>${escapeHTML(label)}</span><b${total&&String(value).startsWith('-')?' class="financial-value-negative"':''}>${escapeHTML(value)}</b></div>`;
  const note=message=>`<p class="financial-breakdown-note">${escapeHTML(message)}</p>`;
  const findingRows=findings=>findings.length?`<ul class="financial-record-list">${findings.map(a=>`<li><button type="button" data-card-anomaly="${escapeHTML(a.id)}"><b>${escapeHTML(a.service||a.category)} <i aria-hidden="true">→</i></b><small>${escapeHTML(a.type)} · ${escapeHTML(a.month)}</small><p>${amount(a.amount)}${a.baseline!==null&&a.baseline!==undefined?` vs ${amount(a.baseline)} baseline`:''}</p></button></li>`).join('')}</ul>`:note('No matching patterns flagged in the uploaded records.');
  const explanations={
    'cash-received':'Money actually received during the latest reporting month. Customer invoices show billed amounts separately.',
    'cash-paid':'Money paid during the latest reporting month, including recorded payroll, supplier and operating payments.',
    'net-cash':'Cash received minus cash paid. This measures cash flow, not accounting profit.',
    'closing-cash':'Opening cash plus receipts minus payments across the reporting period. Complete transaction coverage is required.',
    patterns:'Financial patterns flagged in your records: spending spikes, subscription price increases and overdue invoices.',
    spikes:'Monthly category spending compared with its recent median. Large increases are flagged for review.',
    subscriptions:d.has_subscription_data?'Recorded subscription price increases compared with each service’s first recorded charge.':'Subscription records were not provided in this upload.',
    overdue:d.has_invoice_data?'Customer invoices with known outstanding balances and due dates before the reporting date.':'Customer invoice records were not provided in this upload.'
  };
  const cashComparison=(key,change)=>row('Reporting month',latest?friendlyMonth(latest.month):'Not provided')+row('This month',amount(latest?.[key]))+row('Previous month',amount(previous?.[key]))+row('Change',change===null||change===undefined?'Not available':`${change>0?'+':''}${change}%`);
  const breakdowns={
    'cash-received':cashComparison('cash_in',t.cash_in_change_pct)+note('Calculated from posted Income transactions. Billed revenue is tracked separately.'),
    'cash-paid':cashComparison('cash_out',t.expense_change_pct)+note('Calculated from posted Expense transactions. Payroll and supplier payments already in the ledger are counted once.'),
    'net-cash':row('Cash received',amount(t.last_month_cash_in))+row('Cash paid',amount(t.last_month_cash_out))+row('Net cash movement',amount(t.last_month_net),true)+note('Cash received − cash paid. This is a cash-flow measure, not the company’s accounting profit.'),
    'closing-cash':row('Opening cash',d.has_opening_cash?amount(t.closing_cash-t.net):'Not provided')+row('Cash received · whole period',amount(t.cash_in))+row('Cash paid · whole period',amount(t.cash_out))+row('Closing cash',amount(t.closing_cash),true)+note(d.has_opening_cash?'Opening cash + recorded receipts − recorded payments, across the uploaded reporting period.':'Provide an opening balance and a complete cash ledger to calculate closing cash.'),
    patterns:row('Spending spikes',spikes.length)+row('Subscription changes',prices.length)+row('Flags for overdue invoices',all.filter(a=>a.type==='Overdue invoices').length)+row('Total patterns',all.length,true)+note('A single overdue-invoice pattern can cover several customer invoices.')+findingRows(all),
    spikes:note('Flagged when monthly category spending is more than 40% and at least $100 above its recent median.')+findingRows(spikes),
    subscriptions:d.has_subscription_data?findingRows(prices)+note('Current charges are compared with the first recorded charges. Usage is not established by payment records.'):note('Provide a Subscriptions worksheet and matching Operating Expenses history to investigate price changes.'),
    overdue:d.has_invoice_data?row('Reporting date',d.as_of)+row('Overdue invoices',t.overdue_invoices,true)+(invoiceRows.length?`<ul class="financial-record-list">${invoiceRows.map(i=>`<li><button type="button" data-card-anomaly="${escapeHTML(invoiceFlag?.id||'')}"><b>${escapeHTML(i.customer)} <i aria-hidden="true">→</i></b><small>${escapeHTML(i.invoice)} · due ${escapeHTML(i.due)}</small><p>${amount(i.amount)} outstanding · ${i.overdue_days} days overdue</p></button></li>`).join('')}</ul>`:note('No overdue invoices with known outstanding balances.'))+(t.unknown_invoice_balances?note(`${t.unknown_invoice_balances} invoice(s) have unknown payment balances and are excluded.`):'')+(invoiceRows.length<t.overdue_invoices?note(`Showing ${invoiceRows.length} of ${t.overdue_invoices} overdue invoices included in this report.`):''):note('Provide customer invoice due dates and outstanding balances to check overdue payments.')
  };
  document.querySelectorAll('.financial-card').forEach(card=>{
    const kind=card.dataset.card;
    card.querySelector('.financial-card-tooltip').textContent=explanations[kind];
    card.querySelector('.financial-card-breakdown').innerHTML=breakdowns[kind];
    card.querySelectorAll('[data-card-anomaly]').forEach(button=>button.addEventListener('click',()=>{
      toggleCardBreakdown(card,false);openAnomaly(button.dataset.cardAnomaly);
      $('anomaly-detail').scrollIntoView({behavior:'smooth',block:'nearest'});
      $('explain-anomaly')?.focus({preventScroll:true});
    }));
  });
  const net=t.last_month_net;
  text('net-cash-period',latest?`${friendlyMonth(latest.month)} · ${net>0?'Positive':net<0?'Negative':'No'} net cash movement`:'Cash transactions not provided');
  $('metric-net').classList.toggle('metric-positive',net!==null&&net>0);
  $('metric-net').classList.toggle('metric-negative',net!==null&&net<0);
}
function initFinancialCards(){
  document.querySelectorAll('.financial-card').forEach(card=>{
    const kind=card.dataset.card,label=card.querySelector('span'),title=label.textContent;
    label.outerHTML=`<div class="financial-card-heading"><span id="card-${kind}-label">${escapeHTML(title)}</span><button type="button" class="financial-card-info" aria-label="About ${escapeHTML(title)}" aria-expanded="false" aria-controls="card-${kind}-tip" aria-describedby="card-${kind}-tip">ⓘ</button></div>`;
    card.insertAdjacentHTML('beforeend',`<p id="card-${kind}-tip" class="financial-card-tooltip hidden" role="tooltip"></p><button type="button" class="financial-card-toggle" aria-expanded="false" aria-controls="card-${kind}-breakdown"><span>Show breakdown</span><b aria-hidden="true">⌄</b></button><div id="card-${kind}-breakdown" class="financial-card-breakdown hidden" role="region" aria-labelledby="card-${kind}-label"></div>`);
    const info=card.querySelector('.financial-card-info');
    card.addEventListener('pointerenter',event=>{if(event.pointerType!=='touch')showCardInfo(card)});
    card.addEventListener('pointerleave',()=>{
      cardInfoCloseTimer=setTimeout(()=>{if(activeCardInfo===card&&pinnedCardInfo!==card&&document.activeElement!==info)hideCardInfo()},160);
    });
    info.addEventListener('focus',()=>showCardInfo(card));
    info.addEventListener('blur',()=>{if(pinnedCardInfo!==card&&!card.matches(':hover'))hideCardInfo()});
    info.addEventListener('click',()=>{if(pinnedCardInfo===card)hideCardInfo();else showCardInfo(card,true)});
    card.querySelector('.financial-card-toggle').addEventListener('click',()=>toggleCardBreakdown(card));
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')hideCardInfo()});
  document.addEventListener('pointerdown',event=>{if(activeCardInfo&&!activeCardInfo.contains(event.target))hideCardInfo()});
  document.addEventListener('scroll',event=>{
    if(activeCardInfo){
      const bounds=activeCardInfo.getBoundingClientRect();
      if(bounds.bottom<0||bounds.top>window.innerHeight)hideCardInfo();else positionCardInfo(activeCardInfo);
    }
  },{capture:true,passive:true});
  window.addEventListener('resize',()=>{if(activeCardInfo)positionCardInfo(activeCardInfo)});
}
function renderAnomalyDetail(a){
  const el=$('anomaly-detail');
  if(!a){el.innerHTML='<p>Choose a financial signal to inspect its evidence.</p>';return;}
  const pct=(a.increase_pct!==null&&a.increase_pct!==undefined)?`<span class="detail-badge">+${escapeHTML(a.increase_pct)}% vs baseline</span>`:'';
  const baseline=a.baseline!==null&&a.baseline!==undefined?`<div><small>Comparison baseline</small><strong>${fmt(a.baseline)}</strong></div>`:'';
  const stats=`<div class="anomaly-stats"><div><small>Flagged amount</small><strong>${fmt(a.amount)}</strong></div>${baseline}<div><small>Period</small><strong>${escapeHTML(a.month)}</strong></div></div>`;
  const transactions=(a.evidence||[]).length?`<h4>Supporting transactions <span>(${a.evidence_count||a.evidence.length} matching records; showing up to ${a.evidence.length})</span></h4>
    <div class="table-scroll"><table class="evidence-table"><thead><tr><th>Date</th><th>Counterparty / description</th><th class="right">Amount</th></tr></thead><tbody>${a.evidence.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td>${escapeHTML(t.vendor)}<small>${escapeHTML(t.description)}</small></td><td class="right">${fmt(t.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const invoices=(a.invoices||[]).length?`<h4>Overdue customer invoices <span>(at reporting date)</span></h4><div class="table-scroll"><table class="evidence-table"><thead><tr><th>Customer / invoice</th><th>Due</th><th class="right">Outstanding</th></tr></thead><tbody>${a.invoices.map(i=>`<tr><td>${escapeHTML(i.customer)}<small>${escapeHTML(i.invoice)}</small></td><td>${escapeHTML(i.due)}<small>${i.overdue_days} days late</small></td><td class="right">${fmt(i.amount)}</td></tr>`).join('')}</tbody></table></div>`:'';
  const hist=a.history?.length?`<h4>Recorded monthly amounts</h4><div class="anomaly-history">${a.history.map(h=>`<div><small>${escapeHTML(h.month)}</small><strong>${fmt(h.amount)}</strong><i style="width:${Math.max(3,Math.min(100,100*h.amount/Math.max(1,...a.history.map(z=>z.amount))))}%"></i></div>`).join('')}</div>`:'';
  el.innerHTML=`<div class="anomaly-detail-heading"><span class="eyebrow">${escapeHTML(a.type)} · ${escapeHTML(a.category)}</span><h3>${escapeHTML(a.message)}</h3>${pct}</div>
    ${stats}<h4>How FINOVA flagged it</h4><p>${escapeHTML(a.method||'FINOVA compared historical records.')}</p>
    ${hist}${transactions}${invoices}<div class="anomaly-action"><strong>Recommended next step</strong><p>${escapeHTML(a.action||'Review the original source records.')}</p></div>
    <button id="explain-anomaly" type="button" class="button button-primary">✦ Ask FINOVA about this</button>`;
  $('explain-anomaly').addEventListener('click',()=>{
    switchPage('overview');
    const q=`Explain the ${a.type.toLowerCase()} for ${a.category} in ${a.month} and what we should check.`;
    $('question').value=q;ask(q);
    $('ai-answer').scrollIntoView({behavior:'smooth',block:'center'});
  });
}
function renderTransactions(){if(!DATA)return;const q=$('transaction-search').value.trim().toLowerCase();const trs=DATA.recent_transactions.filter(t=>[t.description,t.category,t.vendor,t.date].some(x=>String(x).toLowerCase().includes(q)));
 $('transaction-table').innerHTML=trs.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td><strong>${escapeHTML(t.description)}</strong></td><td>${escapeHTML(t.category)}</td><td>${escapeHTML(t.type)}</td><td class="right ${t.signed<0?'negative':'positive'}">${signed(t.signed)}</td></tr>`).join('')||'<tr><td colspan="5">No matching transactions found.</td></tr>';
}
function updateScenario(){if(!DATA)return;let r=Number($('rev-slider').value),e=Number($('exp-slider').value);text('rev-label',`${r>0?'+':''}${r}%`);text('exp-label',`${e>0?'+':''}${e}%`);let f=DATA.forecast[0];['rev-slider','exp-slider'].forEach(id=>$(id).disabled=!f);text('scenario-net',f?signed(f.cash_in*(1+r/100)-f.cash_out*(1+e/100)):'Not available')}
async function boot(){try { const status=await getJSON('/api/health');serverHasPDF=Boolean(status.pdf_support);window.FINOVAPdf?.setCapabilities(status.pdf_support);text('pdf-support-note',!serverHasPDF?'Restart the FINOVA server and reload this page to enable PDF uploads.':!window.FINOVAPdf?'Reload this page to load the PDF upload interface.':status.pdf_support.text?'PDF extraction is available on this server.':'PDF extraction needs server setup; CSV and Excel are ready.');text('ai-connection',status.akamai_key_loaded?'Akamai key loaded (verify connection)':'Offline financial analysis ready');text('akamai-status',status.akamai_key_loaded?'Akamai team key loaded. Click Test Akamai connection to verify live access.':'Offline mode: configure your Akamai team key in finova/.env to generate AI artwork. The animated video works without a key.');DATA=await getJSON('/api/dashboard');if(DATA.import_source)text('loaded-file',DATA.import_source.filename);render();} catch(e){notify(e.message,true)}}
function applyImport(summary,filename){DATA=summary;window.FINOVAStory.resetArt();text('loaded-file',filename);render();switchPage('overview');notify(DATA.analysis_kind==='invoices'?`Analyzed ${DATA.invoice_count} reviewed customer invoices.`:`Analyzed ${DATA.transaction_count.toLocaleString()} financial transactions successfully.`)}
async function uploadFile(file,forceOCR=false){if(!file)return;if(!/\.(csv|xlsx|pdf)$/i.test(file.name)){notify('Choose a .xlsx, .csv or .pdf file.',true);return}if(file.size>12*1024*1024){notify('File too large for this demo.',true);return}
 const isPDF=/\.pdf$/i.test(file.name);let progressTimer;
 $('upload-error')?.classList.add('hidden');
 try{
  if(isPDF&&(serverHasPDF===false||!window.FINOVAPdf))throw new Error('PDF uploads need the updated FINOVA server. Stop the server with Ctrl+C, run python3 run.py again, then reload this page.');
  $('loading').style.display='block';text('loading',isPDF?'Extracting PDF records for review…':'Reading your financial records…');
  window.FINOVAPdf?.setBusy(true);$('file-input').disabled=true;$('reset-btn').disabled=true;
  if(isPDF){const started=Date.now();progressTimer=setInterval(()=>{const elapsed=Math.floor((Date.now()-started)/1000);text('loading',`Extracting PDF records for review… ${elapsed}s elapsed. Scanned pages can take longer.`)},1000);}
  const fd=new FormData();fd.append('file',file);if(forceOCR)fd.append('ocr','true');
  const response=await getJSON('/api/upload',{method:'POST',body:fd,timeoutMs:isPDF?75000:45000,timeoutMessage:isPDF?'PDF extraction timed out. Restart FINOVA and try a smaller PDF.':'Upload timed out. Check that FINOVA is running and try again.'});
  if(response.review_required){window.FINOVAPdf.show(response,file);notify('PDF extracted. Check the records and confirm before analysis.')}
  else{window.FINOVAPdf?.clear();applyImport(response.summary,file.name)}
 }catch(e){if($('upload-error')){text('upload-error',e.message);$('upload-error').classList.remove('hidden')}notify(e.message,true)}
 finally{clearInterval(progressTimer);$('loading').style.display='none';$('file-input').value='';window.FINOVAPdf?.setBusy(false);$('file-input').disabled=false;$('reset-btn').disabled=false;}
}
async function ask(question){
 const output=$('ai-answer');output.textContent='FINOVA is analyzing the figures…';
 try{
  const res=await getJSON('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  output.textContent=res.answer;text('ai-source',res.source);
  const mode=$('ai-mode');
  if(res.mode==='local'){
    mode.textContent=(res.warning?`Akamai unavailable: ${res.warning} `:'')+'Showing evidence-based local analysis.';
    mode.classList.add('is-local');text('ai-connection','FINOVA local analysis active');
  } else {mode.textContent='Akamai AI connected · Answer grounded in verified FINOVA calculations.';mode.classList.remove('is-local');text('ai-connection','Akamai AI connected');}
 }catch(e){output.textContent='FINOVA could not answer: '+e.message;}
}
window.addEventListener('DOMContentLoaded',()=>{
 initFinancialCards();
 document.querySelectorAll('.nav-link').forEach(b=>b.addEventListener('click',()=>switchPage(b.dataset.view)));
 $('file-input').addEventListener('change',e=>uploadFile(e.target.files[0]));
 window.FINOVAPdf?.init({getJSON,notify,reupload:uploadFile,onImport:applyImport});
 $('reset-btn').addEventListener('click',async()=>{try{const res=await getJSON('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});window.FINOVAPdf?.clear();$('upload-error')?.classList.add('hidden');DATA=res.summary;text('loaded-file','Demo workbook: finova.xlsx');window.FINOVAStory.resetArt();render();switchPage('overview');notify('Demo workbook restored.')}catch(e){notify(e.message,true)}});
 $('transaction-search').addEventListener('input',renderTransactions);
 $('view-all-anomalies').addEventListener('click',()=>openAnomaly(null));
 document.querySelectorAll('.anomaly-filter').forEach(b=>b.addEventListener('click',()=>{
  anomalyFilter=b.dataset.filter;selectedAnomaly=null;
  document.querySelectorAll('.anomaly-filter').forEach(x=>x.classList.toggle('active',x===b));renderAnomalies();
 }));
 ['rev-slider','exp-slider'].forEach(id=>$(id).addEventListener('input',updateScenario));
 document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.dataset.prompt;ask(b.dataset.prompt)}));
 $('ask-form').addEventListener('submit',e=>{e.preventDefault();let q=$('question').value.trim();if(q)ask(q)});
 window.FINOVAStory.init();
 $('akamai-test').addEventListener('click',async()=>{
   const btn=$('akamai-test');btn.disabled=true;text('akamai-status','Testing your live Akamai workshop access…');
   try{const res=await getJSON('/api/akamai-test');text('akamai-status',res.message);$('akamai-status').classList.remove('is-error');text('ai-connection','Akamai API access verified');text('ai-mode','Akamai API verified. Ask FINOVA to generate an AI explanation.');}
   catch(e){text('akamai-status',e.message);$('akamai-status').classList.add('is-error')}
   finally{btn.disabled=false}
 });
 $('cover-btn').addEventListener('click',async()=>{
   const btn=$('cover-btn');btn.disabled=true;btn.textContent='Generating Akamai art…';
   text('akamai-status','Requesting artwork from Akamai. This can take a little time.');
   try{const res=await getJSON('/api/cover',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',timeoutMs:120000});
     window.FINOVAStory.setArt(res.image);text('akamai-status','Akamai artwork received and added to the story. Play or export it now!');$('akamai-status').classList.remove('is-error');
   }catch(e){text('akamai-status',e.message+' · Your FINOVA Wrapped animation still works without this image.');$('akamai-status').classList.add('is-error')}
   finally{btn.disabled=false;btn.textContent='✦ Generate Akamai artwork'}
 });
 boot();
});
