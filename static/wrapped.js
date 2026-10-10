/* FINOVA Story Studio. Browser-native graphics and video; no video API needed.
   Financial values always originate in the verified server analytics response. */
(() => {
'use strict';
const $ = id => document.getElementById(id);
const palette = [
  ['#10193e','#127a83','#b5ffe8'], ['#141446','#6c2bc2','#d1b3ff'],
  ['#10294c','#108a86','#b8fff0'], ['#30133e','#a12d77','#ffbdd8'],
  ['#1b2045','#426bd5','#c5d4ff'], ['#142441','#ed9340','#ffe3ab'],
  ['#0a223d','#136f7f','#c2ffed'], ['#141b3b','#44329b','#d5c3ff']
];
const seconds = 3.8;
let data=null, art=null, playing=false, recording=false, raf=0, startTime=0;
let recorder=null, chunks=[], audioCtx=null, audioDestination=null, downloadURL=null;
const canvas=$('story-canvas'), ctx=canvas.getContext('2d',{alpha:false});
let size='portrait';
const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
const ease=t=>1-Math.pow(1-clamp(t),3);
const n=v=>Number(v||0);
const money=v=>'$'+Math.round(Math.abs(n(v))).toLocaleString('en-US');
const signMoney=v=>(n(v)<0?'−':'')+money(v);
const shortMonth=v=>{try{return new Date(v+'-01T00:00:00').toLocaleString('en-US',{month:'long',year:'numeric'})}catch{return String(v||'')}};
const line=(s,len=38)=>String(s||'').length>len?String(s).slice(0,len-1)+'…':String(s||'');
function dimensions(){const portrait=size==='portrait'; canvas.width=portrait?720:1280;canvas.height=portrait?1280:720;canvas.style.aspectRatio=portrait?'9 / 16':'16 / 9';}
function R(x,y,w,h,r=24){ctx.beginPath();ctx.roundRect(x,y,w,h,r)}
function text(str,x,y,font,color='#fff',align='left',alpha=1){ctx.save();ctx.globalAlpha*=alpha;ctx.font=font;ctx.textAlign=align;ctx.fillStyle=color;ctx.fillText(String(str),x,y);ctx.restore()}
function wrap(str,maxWidth,font,maxLines=3){ctx.font=font;const words=String(str).split(/\s+/);const lines=[];let curr='';for(const word of words){const next=(curr?curr+' ':'')+word;if(ctx.measureText(next).width>maxWidth&&curr){lines.push(curr);curr=word}else curr=next;}if(curr)lines.push(curr);return lines.slice(0,maxLines)}
function alphaFor(t){return Math.min(1,clamp(t/.4),clamp((seconds-t)/.35));}
function draw(t){
 if(!data)return;
 const scene=Math.min(7,Math.floor(t/seconds));const local=Math.max(0,t-scene*seconds);
 const W=canvas.width,H=canvas.height,P=W<H;
 const sx=W/720,sy=H/(P?1280:720),scale=P?sx:W/1280;
 const [dark,mid,accent]=palette[scene]; const g=ctx.createLinearGradient(0,0,W,H);
 g.addColorStop(0,dark);g.addColorStop(.68,mid);g.addColorStop(1,dark);ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
 // Akamai's generated artwork remains decorative and never contains factual numbers.
 if(art && (scene===0||scene===7)){
   ctx.save();ctx.globalAlpha=.18;ctx.filter='blur(8px)';const side=Math.max(W,H)*1.1;
   ctx.drawImage(art,(W-side)/2,(H-side)/2,side,side);ctx.restore();
 }
 ctx.save();ctx.globalAlpha=.12;
 for(let i=0;i<7;i++){
   const radius=(110+i*80)*scale; const x=W*(.78+Math.sin(t*.33+i)*.02);const y=H*(P?.24:.46);
   ctx.beginPath();ctx.arc(x,y,radius,0,Math.PI*2);ctx.strokeStyle=accent;ctx.lineWidth=2*scale;ctx.stroke();
 }
 ctx.restore();
 for(let i=0;i<45;i++){
   const x=((i*71.73+t*8*(i%3+1))%(W+25)),y=((i*i*43.87+Math.sin(t*1.2+i)*50)%(H+30));
   ctx.beginPath();ctx.arc(x,y,(i%3+1)*scale,0,Math.PI*2);ctx.fillStyle=accent;ctx.globalAlpha=.12+(i%4)*.04;ctx.fill();
 }ctx.globalAlpha=1;
 const inset=P?51*scale:70*scale, centerX=W/2;
 text('✦ FINOVA',inset,P?81*scale:53*scale,`900 ${P?24:21}PX Arial`.replace('PX','px'),'#fff');
 text('FINANCE INNOVATION',W-inset,P?81*scale:53*scale,`700 ${P?13:13}px Arial`,accent,'right');
 const progY=H-(P?72:48)*scale,availW=W-inset*2;
 for(let i=0;i<8;i++){
  const gap=7*scale,w=(availW-7*gap)/8,x=inset+i*(w+gap);
  R(x,progY,w,5*scale,3*scale);ctx.fillStyle='rgba(255,255,255,.24)';ctx.fill();
  if(i<=scene){R(x,progY,w*(i===scene?clamp(local/seconds):1),5*scale,3*scale);ctx.fillStyle=accent;ctx.fill();}
 }
 text('FINOVA BUSINESS WRAPPED  •  '+line(data.wrapped.period,38),inset,H-(P?36:19)*scale,`600 ${P?13:11}px Arial`,'#d4e3ef');
 const appear=alphaFor(local),come=ease(local/.68),dy=(1-come)*44*scale;
 const titleFont=`900 ${(P?70:70)*scale}px Arial`;
 const smallFont=`500 ${(P?27:25)*scale}px Arial`;
 const numericFont=`900 ${(P?88:105)*scale}px Arial`;
 const top=P?250*scale:176*scale;
 const left=inset;
 function overline(s){text(s.toUpperCase(),left,top-dy,`800 ${(P?21:18)*scale}px Arial`,accent,'left',appear)}
 function headline(s,y=top+100*scale,fs=P?66:66){let lines=wrap(s,W-left*2,`900 ${fs*scale}px Arial`,3);lines.forEach((l,i)=>text(l,left,y+i*fs*1.1*scale-dy,`900 ${fs*scale}px Arial`,'#fff','left',appear));return lines.length;}
 function detail(s,y){const lines=wrap(s,W-2*left,`500 ${(P?25:22)*scale}px Arial`,3);lines.forEach((l,i)=>text(l,left,y+i*(P?35:32)*scale,smallFont,'#edf5ff','left',appear))}
 function big(s,y){let size=P?99:112;while(size>52){ctx.font=`900 ${size*scale}px Arial`;if(ctx.measureText(String(s)).width<W-left*2)break;size-=4;}text(s,left,y-dy,`900 ${size*scale}px Arial`,accent,'left',appear)}
 const w=data.wrapped,forecast=data.forecast?.[0],totals=data.totals;
 ctx.save();ctx.globalAlpha=appear;
 switch(scene){
  case 0: {
    overline(line(data.company,27));headline('YOUR BUSINESS. YOUR STORY.',top+115*scale,P?70:75);
    detail('A financial year that finally makes sense.',P?top+425*scale:top+225*scale);
    const pulse=.87+.13*Math.sin(t*3);ctx.strokeStyle=accent;ctx.lineWidth=9*scale;
    ctx.beginPath();ctx.arc(P?W*.50:W*.82,P?H*.75:H*.56,110*scale*pulse,0,Math.PI*2);ctx.stroke();
    text('✦',P?W*.50:W*.82,P?H*.77:H*.60,`900 ${92*scale}px Arial`,'#d4fff3','center');
    break;
  }
  case 1: {
    overline('01  •  Revenue reality');headline('HERE’S WHAT CAME IN.');
    big(money(w.cash_in*ease(local/1.8)),top+(P?375:265)*scale);
    detail('Cash receipts, not necessarily billed revenue.',top+(P?465:355)*scale);
    break;
  }
  case 2: {
    overline('02  •  Cost of doing business');headline('EVERY DOLLAR OUT.');
    big(money(w.cash_out*ease(local/1.8)),top+(P?375:260)*scale);
    const net=n(w.cash_in)-n(w.cash_out);
    detail('Net cash movement over this period: '+signMoney(net),top+(P?485:345)*scale);
    break;
  }
  case 3: {
    overline('03  •  Your biggest month');headline('THE MONTH THAT STOOD OUT.');
    big(shortMonth(w.biggest_expense_month),top+(P?355:260)*scale);
    detail('Highest monthly outgoing cash: '+money(w.biggest_expense_month_amount),top+(P?460:355)*scale);
    break;
  }
  case 4: {
    overline('04  •  Where spending concentrates');headline('YOUR BIGGEST COST CENTER.');
    big(line(w.largest_category,26),top+(P?365:265)*scale);
    detail(money(w.largest_category_amount)+' spent across all uploaded history. Includes all payments in this category.',top+(P?465:356)*scale);
    break;
  }
  case 5: {
    overline('05  •  The subscription story');headline('THE QUIET RECURRING COST.');
    big(money(w.subscription_annual),top+(P?360:265)*scale);
    detail('Annualized subscription run rate. '+data.subscriptions.length+' services currently tracked; review actual usage before cancelling.',top+(P?468:350)*scale);
    break;
  }
  case 6: {
    overline('06  •  What deserves attention');headline('NEXT: LOOK BEYOND THE NUMBERS.');
    let items=[];
    if(totals.overdue_invoices)items.push(totals.overdue_invoices+' overdue customer invoice(s)');
    if(data.anomalies?.length)items.push(line(data.anomalies[0].category,26)+' may need review');
    if(forecast)items.push('Next month estimated net: '+signMoney(forecast.net));
    if(!items.length)items=['No major flagged financial issues','Keep reviewing your financial trends'];
    items.slice(0,3).forEach((s,i)=>{
       const x=left,y=top+(P?310:235)*scale+i*(P?120:86)*scale;
       ctx.fillStyle='rgba(255,255,255,.12)';R(x,y-48*scale,W-2*left,(P?91:67)*scale,18*scale);ctx.fill();
       text('✦  '+s,x+17*scale,y,`700 ${(P?23:24)*scale}px Arial`,'#fff');
    });break;
  }
  case 7: {
    overline('FINOVA  •  Finance Innovation');headline('KNOW YOUR NUMBERS. OWN YOUR NEXT MOVE.',top+105*scale,P?67:74);
    detail('Understand the past. Anticipate the future. Make better business decisions.',top+(P?435:300)*scale);
    text('FINOVA',W/2,H*(P?.73:.83),`900 ${(P?84:75)*scale}px Arial`,accent,'center');
    break;
  }
 }
 ctx.restore();
 // Animated bars are an additional evidence visualization; values come from historical monthly figures.
 if(scene===1||scene===2){
   const monthly=data.monthly.slice(-12),max=Math.max(1,...monthly.map(r=>scene===1?r.cash_in:r.cash_out));
   const barW=(W-left*2)/(monthly.length*1.5),base=H*(P?.81:.89),barMax=H*(P?.15:.23);
   monthly.forEach((row,i)=>{
    const val=scene===1?row.cash_in:row.cash_out;
    const ht=barMax*(val/max)*ease((local-.2)/2);const x=left+i*1.5*barW;
    ctx.fillStyle=accent;ctx.globalAlpha=.55+(i/monthly.length)*.4;
    R(x,base-ht,barW*.8,Math.max(0,ht),barW*.15);ctx.fill();
   });ctx.globalAlpha=1;
 }
}
function setStatus(s,isError=false){const target=$('story-status');target.textContent=s;target.classList.toggle('story-error',isError)}
function stopAudio(){if(audioCtx){audioCtx.close().catch(()=>{});audioCtx=null;audioDestination=null}}
function makeMusic(){
 if(!$('story-sound').checked)return null;
 try{
  audioCtx=new (window.AudioContext||window.webkitAudioContext)();audioDestination=audioCtx.createMediaStreamDestination();
  const master=audioCtx.createGain();master.gain.value=.21;master.connect(audioCtx.destination);master.connect(audioDestination);
  const now=audioCtx.currentTime+.08;
  const notes=[196,247,294,392,330,294,247,220,196,247,330,440,392,330,294,247];
  const total=seconds*8;
  for(let i=0;i<total/.4;i++){
   const when=now+i*.4,freq=notes[i%notes.length];
   const osc=audioCtx.createOscillator(),env=audioCtx.createGain();osc.type='triangle';osc.frequency.setValueAtTime(freq,when);
   env.gain.setValueAtTime(.0001,when);env.gain.exponentialRampToValueAtTime(.15,when+.025);
   env.gain.exponentialRampToValueAtTime(.0001,when+.28);
   osc.connect(env);env.connect(master);osc.start(when);osc.stop(when+.32);
   if(i%4===0){const bass=audioCtx.createOscillator(),bEnv=audioCtx.createGain();bass.type='sine';bass.frequency.setValueAtTime(110,when);bass.frequency.exponentialRampToValueAtTime(48,when+.19);
    bEnv.gain.setValueAtTime(.16,when);bEnv.gain.exponentialRampToValueAtTime(.001,when+.23);
    bass.connect(bEnv);bEnv.connect(master);bass.start(when);bass.stop(when+.24);
   }
  }
  return audioDestination.stream;
 }catch(e){stopAudio();return null}
}
function finalPlayback(){playing=false;$('story-play').disabled=false;$('story-export').disabled=false;$('story-play').textContent='▶ Play again';$('story-format').disabled=false;stopAudio();}
function renderLoop(now){
 const elapsed=(now-startTime)/1000,total=seconds*8;
 draw(Math.min(total-.001,elapsed));$('story-progress').value=Math.min(100,elapsed/total*100);
 if(elapsed<total&&playing){raf=requestAnimationFrame(renderLoop)}else{
  playing=false;cancelAnimationFrame(raf);
  if(recording&&recorder?.state==='recording')recorder.stop();else finalPlayback();
 }
}
async function play(exportVideo=false){
 if(!data||playing)return;
 if(downloadURL){URL.revokeObjectURL(downloadURL);downloadURL=null}
 size=$('story-format').value;dimensions();playing=true;recording=exportVideo;
 $('story-play').disabled=true;$('story-export').disabled=true;$('story-format').disabled=true;
 setStatus(exportVideo?'Recording FINOVA Wrapped in real time. Keep this tab visible…':'Now playing FINOVA Wrapped!');
 startTime=performance.now();
 let music=makeMusic();
 if(exportVideo){
   if(typeof MediaRecorder==='undefined'||!canvas.captureStream){recording=false;playing=false;stopAudio();setStatus('Video recording is not supported by this browser. Use Chrome or Edge, or enjoy the animated story.',true);finalPlayback();$('story-format').disabled=false;return}
   const mime=['video/webm;codecs=vp9,opus','video/webm;codecs=vp8,opus','video/webm','video/mp4'].find(s=>MediaRecorder.isTypeSupported(s));
   if(!mime){recording=false;playing=false;stopAudio();setStatus('No compatible browser video recording format. Try current Chrome or Edge.',true);finalPlayback();$('story-format').disabled=false;return}
   try{
     const combined=canvas.captureStream(30);
     if(music)music.getAudioTracks().forEach(track=>combined.addTrack(track));
     chunks=[];recorder=new MediaRecorder(combined,{mimeType:mime,videoBitsPerSecond:4000000});
     recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
     recorder.onerror=e=>setStatus('Video recorder error: '+(e.error?.message||'unknown error'),true);
     recorder.onstop=()=>{
       let blob=new Blob(chunks,{type:mime});if(blob.size<5000){setStatus('The recording was too small. Keep the tab visible and try again.',true)}
       else{
        downloadURL=URL.createObjectURL(blob);const extension=mime.includes('mp4')?'mp4':'webm';
        const a=document.createElement('a');a.href=downloadURL;a.download='FINOVA_Business_Wrapped.'+extension;document.body.appendChild(a);a.click();a.remove();
        setStatus('Video exported: FINOVA_Business_Wrapped.'+extension+' ('+(blob.size/1048576).toFixed(1)+' MB).');
       }
       finalPlayback();$('story-format').disabled=false;
     };
     recorder.start(250);
   }catch(e){recording=false;playing=false;setStatus('Recording could not start: '+e.message,true);finalPlayback();$('story-format').disabled=false;return}
 }
 raf=requestAnimationFrame(renderLoop);
}
function init(){
 dimensions();$('story-play').addEventListener('click',()=>play(false));$('story-export').addEventListener('click',()=>play(true));
 $('story-format').addEventListener('change',()=>{if(playing)return;size=$('story-format').value;dimensions();draw(.9)});
 document.addEventListener('visibilitychange',()=>{if(document.hidden&&recording)setStatus('Keep this browser tab visible during export for smooth video recording.',true)});
}
window.FINOVAStory={init,setData(d){data=d;draw(.9);setStatus('Ready · 8 scenes · 30 seconds. Choose Play or Export video.')},setArt(image){const img=new Image();img.onload=()=>{art=img;draw(.9)};img.onerror=()=>setStatus('Generated artwork could not be loaded.',true);img.src=image},setStatus,resetArt(){art=null;draw(.9)}};
})();
