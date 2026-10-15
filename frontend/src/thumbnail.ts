export function remapThumbnail<T>(previous:T[],next:T[],index=0):number{
 const found=next.indexOf(previous[index])
 return found>=0?found:Math.max(0,Math.min(index,next.length-1))
}
