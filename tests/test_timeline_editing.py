import io
import subprocess
import threading

import imageio_ffmpeg
import pytest
from PIL import Image, ImageDraw, ImageStat

from studio.models import ProjectInput
from studio.renderer import caption_layer, render
from test_studio import client, payload


def test_caption_size_changes_visible_glyph_size():
    base = {'subtitle_style': 'clean', 'subtitle_x': .5, 'subtitle_y': .5}
    small = caption_layer({**base, 'subtitle_size': 24}, '크기를 바꿔요').getbbox()
    large = caption_layer({**base, 'subtitle_size': 96}, '크기를 바꿔요').getbbox()
    assert large[2]-large[0] > 3*(small[2]-small[0])
    assert large[3]-large[1] > 3*(small[3]-small[1])


@pytest.mark.parametrize('field,value', [('subtitle_size', 23), ('subtitle_size', 97), ('motion', 'invalid'), ('transition', 'invalid')])
def test_edit_setting_validation(client, field, value):
    assert client.post('/api/projects', json={**payload(), field:value}).status_code == 422


def decode(video, time):
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-ss', str(time),
                             '-i', str(video), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                            capture_output=True, check=True)
    return Image.open(io.BytesIO(result.stdout)).convert('RGB')


@pytest.mark.parametrize('kind,motion,transition', [('daily','pan-right','cut'), ('daily','zoom-out','fade'),
                                                    ('news','pan-left','cut'), ('news','zoom','fade'), ('news','still','cut')])
def test_motion_transition_and_scene_order_in_real_mp4(client, tmp_path, kind, motion, transition):
    photos=[]
    for color in ['#dc3434','#3446dc']:
        image=Image.new('RGB',(1080,1920),color); draw=ImageDraw.Draw(image)
        for x in range(0,1080,80): draw.rectangle((x,50,x+20,1200), fill='white')
        raw=io.BytesIO();image.save(raw,'PNG')
        photos.append(client.post('/api/photos?filename=scene.png',content=raw.getvalue()).json())
    scenes=[{'title':str(i),'narration':'','duration':2,'image_asset_id':p['asset_id']} for i,p in enumerate(photos)]
    project=ProjectInput(**{'title':'timeline','content_type':kind,'photos':photos if kind=='daily' else [],
                           'scenes':scenes,'motion':motion,'transition':transition,'music_id':''}).model_dump()
    project.update(id='test',revision=1)
    directory=tmp_path/'render'
    result=render(project,directory,None,{},threading.Event(),lambda *args:None,lambda *args:None,client.app.state.store.assets)
    video=directory/'video.mp4'
    first, later, second, boundary=(decode(video,t) for t in [.4,1.5,2.5,2.0])
    assert first.getpixel((500,1300))[0] > 150
    assert second.getpixel((500,1300))[2] > 150
    if motion == 'still': assert first.crop((0,100,1080,1000)).tobytes() == later.crop((0,100,1080,1000)).tobytes()
    else: assert first.crop((0,100,1080,1000)).tobytes() != later.crop((0,100,1080,1000)).tobytes()
    brightness=sum(ImageStat.Stat(boundary).mean)/3
    assert brightness < 5 if transition=='fade' else brightness > 60
    assert result['duration']==4 and result['layout_version']==3
