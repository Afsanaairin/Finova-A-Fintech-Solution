'use strict';
// Download the selected Anomaly Explorer investigation from verified source records.
window.FINOVAReports=(()=>{
  let api,notify,data=null,revision=0;

  function init(dependencies){
    api=dependencies.getJSON;notify=dependencies.notify;
  }
  function setData(summary){
    revision++;data=summary;
  }
  function reset(){
    revision++;data=null;
  }
  async function downloadAnomaly(id,button){
    if(!api||!data||button.disabled)return;
    const version=revision,original=button.textContent;
    button.disabled=true;button.textContent='Preparing PDF…';
    try{
      const result=await api('/api/reports/download',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report_type:'anomaly',anomaly_id:id}),responseType:'pdf'
      });
      if(version!==revision)return;
      const url=URL.createObjectURL(result.blob),link=document.createElement('a');
      link.href=url;link.download=result.filename;document.body.append(link);link.click();link.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
      notify('Investigation report downloaded.');
    }catch(error){if(version===revision)notify(error.message,true);}
    finally{if(button.isConnected){button.textContent=original;button.disabled=false;}}
  }
  return {init,setData,reset,downloadAnomaly};
})();
