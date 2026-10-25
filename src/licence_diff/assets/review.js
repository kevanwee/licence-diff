const filter=document.querySelector('#filter');
filter.addEventListener('input',()=>{
 const query=filter.value.trim().toLocaleLowerCase();
 for(const row of document.querySelectorAll('[data-finding]'))row.hidden=!row.textContent.toLocaleLowerCase().includes(query);
});
const form=document.querySelector('#review');
if(form)form.addEventListener('submit',event=>{
 event.preventDefault();
 const actor=document.querySelector('#actor').value.trim(),basis=document.querySelector('#basis').value.trim();
 const findings={};let missing=false;
 for(const row of document.querySelectorAll('[data-finding]')){
  const disposition=row.querySelector('[data-disposition]').value;
  const note=row.querySelector('[data-note]').value.trim();
  const correction=row.querySelector('[data-correction]').value.trim()||null;
  if(!disposition||note.length<8||(disposition==='corrected'&&!correction))missing=true;
  findings[row.dataset.finding]={disposition,note,correction};
 }
 const status=document.querySelector('#status');
 if(missing||!actor||basis.length<8){status.textContent='Review every finding, add a note of at least eight characters, and provide the reviewer and basis. Corrected assessments need replacement text.';return;}
 const value={schema_version:'1',package_digest:packageInfo.digest,actor,basis,reviewed_at:new Date().toISOString(),synthetic:packageInfo.synthetic,findings};
 const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}));
 const link=document.createElement('a');link.href=url;link.download='review-decisions.json';link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 status.textContent='Decisions downloaded. Run finalize to validate the fingerprint and export the reviewed report. Original observations are preserved.';
});
