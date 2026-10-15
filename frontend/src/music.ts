import catalog from '../../resources/music/catalog.json'
import type {Project} from './types'

export const musicTracks = catalog.tracks
export const musicMoods = Object.keys(catalog.recommendations)
export function recommendedMusic(mood:string) {
 const ids = catalog.recommendations[mood as keyof typeof catalog.recommendations] || catalog.recommendations['일상']
 return ids.map(id=>musicTracks.find(t=>t.id===id)!).filter(Boolean)
}
export function musicCredit(project:Pick<Project,'music_id'|'music_asset_id'>) {
 return project.music_asset_id?'':musicTracks.find(t=>t.id===project.music_id)?.attribution||''
}
export function postingCaption(project:Pick<Project,'caption'|'music_id'|'music_asset_id'>) {
 const caption=project.caption.trim(),credit=musicCredit(project)
 return credit&&!caption.includes(credit)?[caption,credit].filter(Boolean).join('\n\n'):caption
}
