/* PDF drafts stay separate from the dashboard until the user confirms them. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
let draft = null, callbacks = null, file = null, busy = false, ocrAvailable = false;
const fields = {
  transactions: [
    ['Date','Date','date',true], ['Description','Description','text',false],
    ['Type','Direction','direction',true], ['Category','Category','text',false],
    ['Amount_USD','Amount (USD)','number',true]
  ],
  invoices: [
    ['Invoice_ID','Invoice ID','text',true], ['Customer','Customer','text',true],
    ['Invoice_Date','Invoice date','date',false], ['Due_Date','Due date','date',false],
    ['Amount_USD','Invoice amount (USD)','number',true],
    ['Outstanding_USD','Outstanding (USD)','number',false], ['Status','Payment status','status',true]
  ]
};
function collect() {
  return [...$('pdf-review-rows').querySelectorAll('[data-record]')].map(element => {
    const row = {...draft.rows[draft.kind][Number(element.dataset.record)]};
    row.include = element.querySelector('[data-include]').checked;
    element.querySelectorAll('[data-field]').forEach(input => {row[input.dataset.field] = input.value;});
    return row;
  });
}
function updateCount() {
  const included = [...$('pdf-review-rows').querySelectorAll('[data-include]')].filter(input => input.checked).length;
  $('pdf-row-count').textContent = `${included} record(s) included · check for missing rows in the original PDF`;
}
function inputHTML(field, row) {
  const [name,label,type,required] = field;
  const value = row[name] ?? '';
  const attributes = `data-field="${name}" aria-label="${label}" ${required?'required':''} ${row.include===false?'disabled':''}`;
  if (type === 'direction' || type === 'status') {
    const options = type === 'direction' ? [['','Choose…'],['Income','Income'],['Expense','Expense']] : [['Unknown','Unknown'],['Unpaid','Unpaid'],['Partial','Partially paid'],['Paid','Paid']];
    return `<select ${attributes}>${options.map(([key,text]) => `<option value="${key}" ${value===key?'selected':''}>${text}</option>`).join('')}</select>`;
  }
  return `<input ${attributes} type="${type}" value="${escape(value)}" ${type==='number'?'step="0.01" min="0" max="1000000000000"':type==='text'?'maxlength="200"':'min="1900-01-01" max="2100-12-31"'}>`;
}
function renderRows() {
  const definition = fields[draft.kind];
  $('pdf-review-head').innerHTML = `<tr><th>Include</th>${definition.map(field => `<th>${field[1]}</th>`).join('')}<th>Source / checks</th></tr>`;
  $('pdf-review-rows').innerHTML = draft.rows[draft.kind].map((row,index) => `<tr data-record="${index}">
    <td><input type="checkbox" data-include aria-label="Include record ${index+1}" ${row.include===false?'':'checked'}></td>
    ${definition.map(field => `<td>${inputHTML(field,row)}</td>`).join('')}
    <td class="pdf-record-source">${row.Source_Page?`Page ${escape(row.Source_Page)}`:'Added manually'}<small>${escape(row.Source_Text || '')}</small><strong>${escape((row.issues || []).join(' '))}</strong></td>
  </tr>`).join('') || `<tr><td colspan="${definition.length+2}">No records were recognized in this layout. Add records using the extracted source text, or try OCR.</td></tr>`;
  $('pdf-confirmed').checked = false;
  updateCount();
}
function updateSettings() {
  const invoices = draft.kind === 'invoices';
  $('pdf-scope-field').classList.toggle('hidden',invoices);
  $('pdf-opening-field').classList.toggle('hidden',invoices || $('pdf-scope').value !== 'complete');
  $('pdf-as-of-field').classList.toggle('hidden',!invoices);
  $('pdf-as-of').required = invoices;
  if (invoices || $('pdf-scope').value !== 'complete') $('pdf-opening').value = '';
}
function error(message) {
  $('pdf-review-error').textContent = message;
  $('pdf-review-error').classList.remove('hidden');
}
function setBusy(value) {
  if(busy===value) return;
  busy = value;
  $('pdf-review-form').querySelectorAll('input,select').forEach(input=>{
    if(value){input.dataset.wasDisabled=String(input.disabled);input.disabled=true;}
    else if(input.dataset.wasDisabled!==undefined){input.disabled=input.dataset.wasDisabled==='true';delete input.dataset.wasDisabled;}
  });
  $('pdf-review-form').querySelectorAll('button').forEach(button => {button.disabled = value;});
  $('pdf-retry-ocr').disabled = value || !ocrAvailable;
  $('file-input').disabled = value;
}
function clear() {
  draft = null; file = null;
  $('pdf-review').classList.add('hidden');
  $('pdf-review-rows').replaceChildren();
  $('pdf-source-text').textContent = '';
  $('pdf-company').value = '';
  $('pdf-confirmed').checked = false;
  setBusy(false);
}
function show(response, uploadedFile) {
  file = uploadedFile;
  const document = response.document;
  draft = {token:response.review_token, kind:document.kind,
           rows:{transactions:document.transaction_rows.map(row=>({...row})), invoices:document.invoice_rows.map(row=>({...row}))}};
  $('pdf-kind').value = draft.kind;
  $('pdf-scope').value = 'selected';
  $('pdf-opening').value = '';
  const today = new Date();
  $('pdf-as-of').value = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  $('pdf-review-description').textContent = `${document.filename} · ${document.pages} page(s) · ${document.used_ocr?'Includes OCR from scanned pages':'Text extracted locally'}`;
  $('pdf-review-warnings').textContent = document.warnings.join(' ');
  $('pdf-source-text').textContent = document.source_text;
  $('pdf-review-error').classList.add('hidden');
  $('pdf-review').classList.remove('hidden');
  updateSettings(); renderRows(); setBusy(false);
  $('pdf-review').scrollIntoView({behavior:'smooth',block:'start'});
}
function init(options) {
  callbacks = options;
  $('pdf-kind').addEventListener('change',()=>{
    if (!draft || busy) return;
    draft.rows[draft.kind] = collect(); draft.kind = $('pdf-kind').value;
    updateSettings(); renderRows();
  });
  $('pdf-scope').addEventListener('change',()=>{if(draft) updateSettings();});
  $('pdf-add-row').addEventListener('click',()=>{
    if (!draft || busy) return;
    draft.rows[draft.kind] = collect();
    if (draft.rows[draft.kind].length >= 1000) {error('A PDF import supports up to 1,000 records.');return;}
    draft.rows[draft.kind].push({Type:'',Category:'Uncategorized',Status:'Unknown',issues:[],include:true});
    renderRows();
  });
  $('pdf-review-form').addEventListener('input',event=>{
    if (event.target.id !== 'pdf-confirmed') $('pdf-confirmed').checked = false;
    if (event.target.matches('[data-include]')) {
      event.target.closest('[data-record]').querySelectorAll('[data-field]').forEach(input=>{input.disabled=!event.target.checked;});
      updateCount();
    }
    $('pdf-review-error').classList.add('hidden');
  });
  $('pdf-cancel').addEventListener('click',async()=>{
    if (!draft || busy) return;
    setBusy(true);
    try {
      await callbacks.getJSON('/api/pdf/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({review_token:draft.token})});
      clear(); callbacks.notify('PDF import cancelled.');
    } catch (exception) {error(exception.message);setBusy(false);}
  });
  $('pdf-retry-ocr').addEventListener('click',async()=>{
    if (!file || busy) return;
    setBusy(true);
    try {await callbacks.reupload(file,true);} finally {setBusy(false);}
  });
  $('pdf-review-form').addEventListener('submit',async event=>{
    event.preventDefault(); if (!draft || busy) return;
    const payload = {review_token:draft.token,kind:draft.kind,rows:collect().filter(row=>row.include!==false),
                     company:$('pdf-company').value,scope:$('pdf-scope').value,opening_cash:$('pdf-opening').value,
                     as_of:$('pdf-as-of').value,confirmed:$('pdf-confirmed').checked};
    setBusy(true);
    try {
      const response = await callbacks.getJSON('/api/pdf/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      const filename = file.name; clear(); callbacks.onImport(response.summary,filename);
    } catch (exception) {error(exception.message);setBusy(false);}
  });
}
window.FINOVAPdf = {init,show,clear,setBusy,setCapabilities(capabilities){ocrAvailable=Boolean(capabilities?.ocr);$('pdf-retry-ocr').disabled=busy||!ocrAvailable;}};
})();
