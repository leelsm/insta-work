import type {Project} from './types'
let token = sessionStorage.getItem('studio_token') || ''
export async function initialize(){
  const hash = new URLSearchParams(location.hash.slice(1))
  if(hash.get('session')) { token = hash.get('session')!; sessionStorage.setItem('studio_token',token); history.replaceState(null,'',location.pathname) }
  if(!token) throw new Error('앱에서 제공한 실행 주소로 접속하세요. 실행 주소는 로컬 콘솔 또는 앱 창에서 확인할 수 있습니다.')
  await api('/session','POST',{token})
}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
  const r = await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Studio-Token':token},body:body===undefined?undefined:JSON.stringify(body)})
  if(!r.ok) { let data; try{data=await r.json()}catch{data={detail:'요청에 실패했습니다.'}}; throw new Error(typeof data.detail==='string'?data.detail:'입력값을 확인하세요. 길이 또는 형식이 올바르지 않습니다.') }
  return r.json()
}
export async function speechSample(){
  const r = await fetch('/api/speech-test',{method:'POST',headers:{'X-Studio-Token':token}})
  if(!r.ok){ const data=await r.json();throw new Error(data.detail) }
  return URL.createObjectURL(await r.blob())
}
export async function restoreBackup(file:File){
  const r=await fetch('/api/restore',{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/zip'},body:file})
  const data=await r.json()
  if(!r.ok) throw new Error(typeof data.detail==='string'?data.detail:'백업 파일을 확인하세요.')
  return data
}
export function mediaPath(p:{id:string;render:null|{folder:string}},filename='video.mp4'){ return p.render?`/media/${p.id}/${p.render.folder}/${filename}`:'' }

export async function uploadPhoto(file:File){
 // Compress before upload, including high-resolution and large original files.
 let image:ImageBitmap|HTMLImageElement
 let objectURL=''
 if(typeof createImageBitmap==='function'){
  try{image=await createImageBitmap(file)}catch{image=await loadImage()}
 }else{image=await loadImage()}
 async function loadImage():Promise<HTMLImageElement>{
  objectURL=URL.createObjectURL(file)
  try{return await new Promise<HTMLImageElement>((resolve,reject)=>{
   const photo=new Image();photo.onload=()=>resolve(photo);photo.onerror=()=>reject(new Error('사진을 읽을 수 없습니다. 다른 사진을 선택해주세요.'));photo.src=objectURL
  })}catch(error){URL.revokeObjectURL(objectURL);throw error}
 }
 let upload:Blob
 try{
  const width=image instanceof HTMLImageElement?image.naturalWidth:image.width
  const height=image instanceof HTMLImageElement?image.naturalHeight:image.height
  if(!width||!height)throw new Error('사진을 읽을 수 없습니다.')
  const scale=Math.min(1,1920/Math.max(width,height)),canvas=document.createElement('canvas')
  canvas.width=Math.max(1,Math.round(width*scale));canvas.height=Math.max(1,Math.round(height*scale))
  const context=canvas.getContext('2d');if(!context)throw new Error('사진 크기를 조정할 수 없습니다.')
  context.drawImage(image,0,0,canvas.width,canvas.height)
  upload=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('사진을 압축하지 못했습니다.')),'image/jpeg',.82))
 }finally{
  if('close' in image)image.close()
  if(objectURL)URL.revokeObjectURL(objectURL)
 }
 const r=await fetch('/api/photos?'+new URLSearchParams({filename:file.name}),{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/octet-stream'},body:upload})
 const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'사진을 확인하세요.');return data
}
export const photoPath=(id:string)=>'/api/photos/'+id

export async function uploadMusic(file:File):Promise<{asset_id:string;filename:string;duration:number}>{
 if(file.size>25_000_000)throw new Error('음악 파일은 25MB 이하여야 합니다.')
 if(!/\.(mp3|m4a|wav)$/i.test(file.name))throw new Error('MP3, M4A, WAV 파일을 선택하세요.')
 const r=await fetch('/api/custom-music?'+new URLSearchParams({filename:file.name}),{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/octet-stream'},body:file})
 const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'음악 파일을 확인하세요.');return data
}
export const customMusicPath=(id:string)=>'/api/custom-music/'+id

export async function uploadFont(file:File):Promise<{asset_id:string;filename:string}>{
 if(file.size>20_000_000)throw new Error('폰트 파일은 20MB 이하여야 합니다.')
 if(!/\.(ttf|otf)$/i.test(file.name))throw new Error('TTF 또는 OTF 폰트 파일을 선택하세요.')
 const r=await fetch('/api/fonts?'+new URLSearchParams({filename:file.name}),{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/octet-stream'},body:file})
 const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'폰트 파일을 확인하세요.');return data
}
export const fontPath=(id:string)=>'/api/fonts/'+id

export async function importTransfer(file:File):Promise<import('./types').Project>{
 if(file.size>250_000_000)throw new Error('프로젝트 파일은 250MB 이하여야 합니다.')
 const r=await fetch('/api/projects/transfer',{method:'POST',headers:{'X-Studio-Token':token,'Content-Type':'application/json'},body:file})
 const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'프로젝트 파일을 확인하세요.');return data
}
export const transferPath=(id:string)=>'/api/projects/'+id+'/transfer'

export function isCurrentRender(p:{content_type:string;render:null|{layout_version?:number}}){return !!p.render&&(p.content_type==='daily'||(p.render.layout_version??0)>=2)}

export function thumbnailPath(p:Project){return mediaPath(p,p.render?.thumbnail?'thumbnail.jpg':`card-${String((p.thumbnail_scene??0)+1).padStart(2,'0')}.png`)}
