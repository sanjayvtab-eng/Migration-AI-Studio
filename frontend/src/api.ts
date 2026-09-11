const API=import.meta.env.VITE_API_URL||'/api';
export const token=()=>localStorage.getItem('mf_token')||'';
export async function api<T>(path:string,init:RequestInit={}):Promise<T>{
  const h=new Headers(init.headers);
  if(!h.has('Content-Type')) h.set('Content-Type','application/json');
  if(token())h.set('Authorization',`Bearer ${token()}`);
  const r=await fetch(`${API}${path}`,{...init,headers:h});
  const payload=await r.json().catch(()=>({detail:r.statusText}));
  if(r.status===401){
    localStorage.removeItem('mf_token');
    window.dispatchEvent(new Event('auth_expired'));
  }
  if(!r.ok)throw new Error(payload.detail||r.statusText);
  return payload as T;
}
export async function downloadApi(path:string,filenameFallback='migration-log.csv'){
  const h=new Headers();
  if(token())h.set('Authorization',`Bearer ${token()}`);
  const r=await fetch(`${API}${path}`,{headers:h});
  if(!r.ok){
    const payload=await r.json().catch(()=>({detail:r.statusText}));
    throw new Error(payload.detail||r.statusText);
  }
  const blob=await r.blob();
  const cd=r.headers.get('content-disposition')||'';
  const m=cd.match(/filename="?([^";]+)"?/i);
  const name=m?.[1]||filenameFallback;
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();
  URL.revokeObjectURL(url);
}
