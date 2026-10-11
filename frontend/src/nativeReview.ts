import {api} from './api'
// Preserve mount/unmount ordering and use the authenticated local server;
// video rendering must never depend on the native JavaScript bridge.
let pending:Promise<unknown>=Promise.resolve()
export function syncNativeReview(reviewing:boolean):Promise<unknown>{
 pending=pending.catch(()=>{}).then(()=>api('/video-review','POST',{reviewing})).catch(()=>{})
 return pending
}
