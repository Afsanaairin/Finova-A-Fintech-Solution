'use strict';
let DATA = null;
const $ = id => document.getElementById(id);
const fmt = x => '$' + Math.abs(Number(x||0)).toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0});
const signed = x => (Number(x)<0 ? '−' : '') + fmt(x);
const text = (id,value) => {$(id).textContent = String(value)};
const friendlyMonth = iso => new Date(iso+'-01T00:00:00').toLocaleString('en-US',{month:'short',year:'numeric'});
const escapeHTML = value => String(value??'').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
function notify(message, bad=false) { const box=$('alert');box.textContent=message;box.classList.remove('hidden');box.classList.toggle('error',bad);setTimeout(()=>box.classList.add('hidden'),7000);}
const pageInfo = {overview:['Overview','A clearer picture of your business.','From transactions to foresight. Understand what changed, what matters, and what comes next.'],forecast:['Forecast & Scenarios','Plan for what comes next.','Explore the cash implications of tomorrow’s decisions.'],subscriptions:['Subscriptions','Make every recurring dollar count.','Understand recurring expenses and price changes.'],transactions:['Transactions','Your money, line by line.','Transparent transaction analysis with an audit trail.'],wrapped:['Business Wrapped','Your financial story, reimagined.','FINOVA turns numbers into a meaningful business recap.']};
function switchPage(id){
 document.querySelectorAll('.page').forEach(el=>el.classList.toggle('hidden',el.id!==id));
 document.querySelectorAll('.nav-link').forEach(el=>el.classList.toggle('active',el.dataset.view===id));
 const [name,title,sub] = pageInfo[id];text('page-crumb',name);text('page-title',title);text('page-subtitle',sub);
 if(id==='overview'||id==='forecast') requestAnimationFrame(drawCharts);
 window.scrollTo({top:0,behavior:'smooth'});
}
async function getJSON(url,options){const r=await fetch(url,options);let d;try{d=await r.json()}catch{throw new Error('Server returned a non-JSON response.')}if(!r.ok)throw new Error(d.error||'Request failed');return d;}
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
function drawCharts(){if(!DATA)return;lineChart('cash-chart',DATA.monthly.slice(-12));lineChart('forecast-chart',[...DATA.monthly.slice(-6),...DATA.forecast],true)}
function render(){if(!DATA)return;
 const d=DATA,t=d.totals; text('company-title',d.company);text('report-date',`${d.reporting_period} · ${d.transaction_count.toLocaleString()} transactions · ${d.months_count} months`);
 text('billed-revenue',t.last_month_invoiced_revenue===null?'Not provided':fmt(t.last_month_invoiced_revenue));text('metric-income',fmt(t.last_month_cash_in));text('metric-expenses',fmt(t.last_month_cash_out));text('metric-net',signed(t.last_month_net));text('metric-balance',signed(t.closing_cash));
 text('income-trend',t.cash_in_change_pct===null?'Cash receipts, not sales revenue':`${t.cash_in_change_pct>0?'+':''}${t.cash_in_change_pct}% vs previous month`);
 text('expense-trend',t.expense_change_pct===null?'Includes payroll & subscriptions':`${t.expense_change_pct>0?'+':''}${t.expense_change_pct}% vs previous month`);
 const biggest=Math.max(...d.categories.map(c=>c.amount),1);
 $('category-bars').innerHTML=d.categories.slice(0,6).map(c=>`<div><div class="bar-label"><span>${escapeHTML(c.category)}</span><b>${fmt(c.amount)}</b></div><div class="bar-bg"><div class="bar-fill" style="width:${Math.max(1,100*c.amount/biggest)}%"></div></div></div>`).join('')||'<p>No expense categories found.</p>';
 $('insight-list').innerHTML=d.anomalies.slice(0,4).map(a=>`<div class="insight"><div class="insight-icon">!</div><div><strong>${escapeHTML(a.type)} · ${escapeHTML(a.category)}</strong><p>${escapeHTML(a.message)}</p></div></div>`).join('')||'<p>No notable anomalies detected.</p>';
 const future=d.forecast[0];text('predicted-sales',future.invoiced_revenue===null?'Not provided':fmt(future.invoiced_revenue));text('future-in',fmt(future.cash_in));text('future-out',fmt(future.cash_out));text('future-net',signed(future.net));text('future-ar',fmt(t.outstanding_invoices));
 $('invoice-list').innerHTML=d.overdue_invoices.slice(0,8).map(i=>`<div class="invoice"><div><strong>${escapeHTML(i.customer)}</strong> <span>· ${escapeHTML(i.invoice)} · due ${escapeHTML(i.due)}</span></div><b>${fmt(i.amount)} · ${i.overdue_days} days overdue</b></div>`).join('')||'<p>No overdue invoices in this dataset.</p>';
 text('sub-count',d.subscriptions.length);text('sub-monthly',fmt(t.subscription_monthly));text('sub-annual',fmt(t.subscription_annual));
 $('subscription-list').innerHTML=d.subscriptions.map(s=>`<div class="subscription-row"><div class="service-icon">${escapeHTML((s.name||'?').slice(0,1))}</div><div class="service-name">${escapeHTML(s.name)}<small>Recurring monthly · Usage not known</small></div><div class="service-amount">${fmt(s.monthly_cost)}<small>per month</small></div><div class="review-tag ${s.price_increase===0?'ok':''}">${s.price_increase>0?`↑ ${fmt(s.price_increase)} price rise`:'No price change detected'}</div></div>`).join('')||'<div class="callout">No subscription sheet present in this upload.</div>';
 text('wrap-income',fmt(d.wrapped.cash_in));text('wrap-expense',fmt(d.wrapped.cash_out));text('wrap-month',friendlyMonth(d.wrapped.biggest_expense_month));text('wrap-category',d.wrapped.largest_category);text('wrap-subs',fmt(d.wrapped.subscription_annual));
 renderTransactions();updateScenario();requestAnimationFrame(drawCharts);
}
function renderTransactions(){if(!DATA)return;const q=$('transaction-search').value.trim().toLowerCase();const trs=DATA.recent_transactions.filter(t=>[t.description,t.category,t.vendor,t.date].some(x=>String(x).toLowerCase().includes(q)));
 $('transaction-table').innerHTML=trs.map(t=>`<tr><td>${escapeHTML(t.date)}</td><td><strong>${escapeHTML(t.description)}</strong></td><td>${escapeHTML(t.category)}</td><td>${escapeHTML(t.type)}</td><td class="right ${t.signed<0?'negative':'positive'}">${signed(t.signed)}</td></tr>`).join('')||'<tr><td colspan="5">No matching transactions found.</td></tr>';
}
function updateScenario(){if(!DATA)return;let r=Number($('rev-slider').value),e=Number($('exp-slider').value);text('rev-label',`${r>0?'+':''}${r}%`);text('exp-label',`${e>0?'+':''}${e}%`);let f=DATA.forecast[0];text('scenario-net',signed(f.cash_in*(1+r/100)-f.cash_out*(1+e/100)))}
async function boot(){try { const status=await getJSON('/api/health');text('ai-connection',status.akamai_connected?'Akamai AI connected':'Offline financial analysis ready');DATA=await getJSON('/api/dashboard');render();} catch(e){notify(e.message,true)}}
async function uploadFile(file){if(!file)return;if(!/\.(csv|xlsx)$/i.test(file.name)){notify('Choose a .xlsx or .csv file.',true);return}if(file.size>12*1024*1024){notify('File too large for this demo.',true);return}
 $('loading').style.display='block';try{const fd=new FormData();fd.append('file',file);const response=await getJSON('/api/upload',{method:'POST',body:fd});DATA=response.summary;text('loaded-file',file.name);render();switchPage('overview');notify(`Analyzed ${DATA.transaction_count.toLocaleString()} financial transactions successfully.`)}catch(e){notify(e.message,true)}finally{$('loading').style.display='none';$('file-input').value=''}}
async function ask(question){const output=$('ai-answer');output.textContent='FINOVA is analyzing the figures…';try{const res=await getJSON('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});output.textContent=res.answer;text('ai-source',res.source)}catch(e){output.textContent=e.message}}
window.addEventListener('DOMContentLoaded',()=>{
 document.querySelectorAll('.nav-link').forEach(b=>b.addEventListener('click',()=>switchPage(b.dataset.view)));
 $('file-input').addEventListener('change',e=>uploadFile(e.target.files[0]));
 $('reset-btn').addEventListener('click',async()=>{try{const res=await getJSON('/api/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});DATA=res.summary;text('loaded-file','Demo workbook: finova.xlsx');$('cover-image').classList.add('hidden');render();notify('Demo workbook restored.')}catch(e){notify(e.message,true)}});
 $('transaction-search').addEventListener('input',renderTransactions);
 ['rev-slider','exp-slider'].forEach(id=>$(id).addEventListener('input',updateScenario));
 document.querySelectorAll('[data-prompt]').forEach(b=>b.addEventListener('click',()=>{text('question',b.dataset.prompt);ask(b.dataset.prompt)}));
 $('ask-form').addEventListener('submit',e=>{e.preventDefault();let q=$('question').value.trim();if(q)ask(q)});
 $('cover-btn').addEventListener('click',async()=>{const btn=$('cover-btn');btn.disabled=true;btn.textContent='Generating artwork…';try{const res=await getJSON('/api/cover',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});$('cover-image').src=res.image;$('cover-image').classList.remove('hidden');notify('Cover created by Akamai image generation.')}catch(e){notify(e.message,true)}finally{btn.disabled=false;btn.textContent='✦ Generate Akamai cover'}});
 boot();
});
