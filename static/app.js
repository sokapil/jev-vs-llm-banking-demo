let scenarios=[];let current='baseline';
const q=s=>document.querySelector(s), qa=s=>[...document.querySelectorAll(s)];
function money(x){return '$'+Number(x||0).toFixed(8).replace(/0+$/,'').replace(/\.$/,'')}
function ms(x){return (Number(x||0)/1000).toFixed(2)+'s'}
async function getJSON(url,opt){const r=await fetch(url,opt);const j=await r.json();if(!r.ok)throw new Error(j.detail||'Request failed');return j}
function renderFacts(){
 const s=scenarios.find(x=>x.id===current); if(!s)return;
 const f=s.facts; const rows=[['Amount',f.amount],['Destination',f.destination],['Beneficiary',f.beneficiary],['Relationship',f.customer_tenure],['KYC',f.kyc],['Typical size',f.normal_payment_size],['Device',f.device],['Time',f.time],['Recent behaviour',f.recent_behaviour],['Sanctions',f.sanctions],['Confirmation',f.confirmation]];
 q('#facts').innerHTML='<div class="facts">'+rows.map(([a,b])=>'<div class="fact"><span>'+a+'</span><strong>'+b+'</strong></div>').join('')+'</div>';
 qa('#variants button').forEach(b=>b.classList.toggle('active',b.dataset.id===current));
}
function metrics(r){return ['Latency|'+ms(r.latency_ms),'Input tokens|'+r.input_tokens,'Cost|'+money(r.cost_usd)].map(x=>{let[a,b]=x.split('|');return '<div class="metric"><span>'+a+'</span><strong>'+b+'</strong></div>'}).join('')}
function renderLLM(r){q('#llmOutput').className='';q('#llmOutput').innerHTML='<div class="assessment">'+(r.assessment||'Structured response returned.')+'</div>';q('#llmMetrics').innerHTML=metrics(r)}
function renderJEV(r){
 const n=r.normalized||{}; const items=[['Payment action',n.payment_action],['Fraud risk',n.fraud_risk],['Authentication',n.authentication],['Human review',n.human_review_required],['Route',n.route_to]];
 q('#jevOutput').className='';q('#jevOutput').innerHTML='<div class="signals">'+items.map(([label,x])=>{if(!x)return'';let p=x.probability_true??x.confidence??0;return '<div class="signal"><div><b>'+label+'</b><div>'+x.value+'</div></div><div class="bar"><i style="width:'+Math.round(p*100)+'%"></i></div><div class="score">'+Number(p).toFixed(2)+'</div></div>'}).join('')+'</div>';q('#jevMetrics').innerHTML=metrics(r)
}
async function runComparison(){
 const b=q('#runComparison');b.disabled=true;b.textContent='Running live comparison…';
 try{const body=JSON.stringify({variant:current});const [llm,jev]=await Promise.all([getJSON('/api/decision/llm',{method:'POST',headers:{'Content-Type':'application/json'},body}),getJSON('/api/decision/jev',{method:'POST',headers:{'Content-Type':'application/json'},body})]);renderLLM(llm);renderJEV(jev)}
 catch(e){alert(e.message)}finally{b.disabled=false;b.textContent='Run comparison'}
}
function benchCard(r){if(!r)return'';return '<div class="bench"><h3>'+r.provider.toUpperCase()+'</h3><table><tr><td>Successful cases</td><td>'+r.successful_cases+'/'+r.requested_cases+'</td></tr><tr><td>Wall time</td><td>'+ms(r.wall_time_ms)+'</td></tr><tr><td>Avg latency</td><td>'+ms(r.avg_latency_ms)+'</td></tr><tr><td>Throughput</td><td>'+r.throughput_per_sec+' cases/s</td></tr><tr><td>Input tokens</td><td>'+r.input_tokens+'</td></tr><tr><td>Output tokens</td><td>'+r.output_tokens+'</td></tr><tr><td>Provider cost</td><td>'+money(r.total_cost_usd)+'</td></tr></table></div>'}
async function runScale(){const b=q('#runScale');b.disabled=true;b.textContent='Running…';q('#scaleOutput').innerHTML='<p>Benchmark in progress…</p>';try{const j=await getJSON('/api/benchmark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cases:Number(q('#cases').value),provider:q('#provider').value})});q('#scaleOutput').innerHTML='<div class="bench-grid">'+benchCard(j.results.jev)+benchCard(j.results.llm)+'</div><p class="sub">'+j.warning+'</p>'}catch(e){q('#scaleOutput').innerHTML='<p style="color:#ff8b98">'+e.message+'</p>'}finally{b.disabled=false;b.textContent='Run scale test'}}
async function init(){
 const [sc,cfg]=await Promise.all([getJSON('/api/scenarios'),getJSON('/api/config')]);scenarios=sc.scenarios;
 q('#variants').innerHTML=scenarios.map(s=>'<button data-id="'+s.id+'">'+s.label+'</button>').join('');
 qa('#variants button').forEach(b=>b.onclick=()=>{current=b.dataset.id;renderFacts()});renderFacts();
 q('#mode').textContent=cfg.mock_mode?'MOCK MODE':'LIVE APIs';q('#mode').style.color=cfg.mock_mode?'#ffbf69':'#59e0ad';
 q('#runComparison').onclick=runComparison;q('#runScale').onclick=runScale;
 qa('.tab').forEach(t=>t.onclick=()=>{qa('.tab').forEach(x=>x.classList.remove('active'));qa('.panel').forEach(x=>x.classList.remove('active'));t.classList.add('active');q('#'+t.dataset.tab).classList.add('active')});
}
init().catch(e=>alert(e.message));