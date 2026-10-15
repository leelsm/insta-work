from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator

Provider = Literal['openai', 'anthropic', 'compatible', 'ollama', 'freellmapi', 'opencode']


class Scene(BaseModel):
    title: str = Field(min_length=1, max_length=90)
    body: str = Field(default='', max_length=500)
    narration: str = Field(default='', max_length=700)
    duration: float = Field(default=6, ge=2, le=30)
    source_ids: list[int] = Field(default_factory=list, max_length=20)
    image_asset_id: str = Field(default='', pattern=r'^(|[a-f0-9]{32})$')
    image_search_query: str = Field(default='', max_length=300)
    image_title: str = Field(default='', max_length=300)
    image_author: str = Field(default='', max_length=300)
    image_license: str = Field(default='', max_length=100)
    image_license_url: str = Field(default='', max_length=1000)
    image_page_url: str = Field(default='', max_length=2000)


class Source(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=30000)
    url: str = Field(default='', max_length=2000)
    published_at: str = Field(default='', max_length=100)
    rights: str = Field(default='', max_length=500)
    kind: str = Field(default='manual', max_length=30)


class Photo(BaseModel):
    asset_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    filename: str = Field(default='사진', max_length=150)
    fit: Literal['cover', 'contain'] = 'cover'
    position_x: float = Field(default=0.5, ge=0, le=1)
    position_y: float = Field(default=0.5, ge=0, le=1)


class ProjectInput(BaseModel):
    content_type: Literal['news', 'daily'] = 'news'
    photos: list[Photo] = Field(default_factory=list, max_length=10)
    mood: str = '일상'
    description: str = Field(default='', max_length=2000)
    music_id: str = 'slow-morning'
    music_asset_id: str = Field(default='', pattern=r'^(|[a-f0-9]{32})$')
    music_filename: str = Field(default='', max_length=150)
    music_volume: float = Field(default=0.35, ge=0, le=1)
    music_offset: float = Field(default=0, ge=0, le=30)
    motion: Literal['still', 'zoom', 'zoom-out', 'pan-left', 'pan-right'] = 'zoom'
    transition: Literal['cut', 'fade'] = 'fade'
    subtitle_style: Literal['box', 'clean'] = 'box'
    subtitle_position: Literal['bottom', 'center'] = 'bottom'
    subtitle_x: float = Field(default=0.5, ge=0, le=1)
    subtitle_y: float | None = Field(default=None, ge=0, le=1)
    subtitle_font_id: str = Field(default='', pattern=r'^(|[a-f0-9]{32})$')
    subtitle_size: int = Field(default=50, ge=24, le=96)
    subtitle_font_name: str = Field(default='', max_length=150)

    title: str = Field(min_length=1, max_length=150)
    sources: list[Source] = Field(default_factory=list, max_length=20)
    scenes: list[Scene] = Field(min_length=1, max_length=12)
    thumbnail_scene: int = Field(default=0, ge=0, le=11)
    caption: str = Field(default='', max_length=2200)
    account_id: str = Field(default='', max_length=100)
    template: Literal['ink', 'paper'] = 'ink'
    accent: str = Field(default='#b8f569', pattern=r'^#[0-9a-fA-F]{6}$')
    brand: str = Field(default='STUDIO', max_length=30)
    logo: str = Field(default='', max_length=350000)
    voice: bool = False
    tone: str = Field(default='간결하고 사실 중심', max_length=150)

    @field_validator('music_id')
    @classmethod
    def valid_music(cls, value):
        from .music import MUSIC
        if value and value not in {t['id'] for t in MUSIC}:
            raise ValueError('앱 음악 목록에서 곡을 선택하세요.')
        return value

    @field_validator('mood')
    @classmethod
    def valid_mood(cls, value):
        from .music import MOODS
        if value not in MOODS:
            raise ValueError('지원하는 분위기를 선택하세요.')
        return value

    @field_validator('logo')
    @classmethod
    def valid_logo(cls, value):
        if not value:
            return ''
        import base64
        import io
        from PIL import Image
        try:
            header, data = value.split(',', 1)
            if header not in ('data:image/png;base64', 'data:image/jpeg;base64'):
                raise ValueError()
            im = Image.open(io.BytesIO(base64.b64decode(data, validate=True)))
            if im.width > 4096 or im.height > 4096 or im.format not in ('PNG', 'JPEG'):
                raise ValueError()
            im = im.convert('RGBA'); im.thumbnail((240, 240))
            output = io.BytesIO(); im.save(output, 'PNG')
            return 'data:image/png;base64,' + base64.b64encode(output.getvalue()).decode()
        except Exception:
            raise ValueError('로고는 4096px 이하 PNG/JPEG 이미지여야 합니다.') from None

    @model_validator(mode='after')
    def check_sources(self):
        if self.thumbnail_scene >= len(self.scenes):
            raise ValueError('썸네일로 사용할 장면을 선택하세요.')
        if self.content_type == 'daily':
            if not 1 <= len(self.photos) <= 10 or len(self.photos) != len(self.scenes):
                raise ValueError('일상 영상은 사진 1~10장과 같은 수의 장면이 필요합니다.')
            if self.voice or any(s.source_ids for s in self.scenes):
                raise ValueError('일상 영상은 음악과 직접 편집 가능한 자막을 사용합니다.')
            if sum(s.duration for s in self.scenes) > 180:
                raise ValueError('일상 영상은 180초 이하여야 합니다.')
        elif self.photos:
            raise ValueError('사진은 일상 영상에 추가하세요.')
        for scene in self.scenes:
            if any(i < 0 or i >= len(self.sources) for i in scene.source_ids):
                raise ValueError('카드의 출처 번호가 올바르지 않습니다.')
        return self


class ProjectUpdate(ProjectInput):
    revision: int = Field(ge=1)


class SettingsInput(BaseModel):
    theme: Literal['dark', 'light'] = 'dark'
    nav_collapsed: bool = False
    nav_groups: dict[Literal['workspace', 'content', 'api', 'accounts', 'preferences', 'help'], bool] = Field(default_factory=dict)
    llm_provider: Provider = 'openai'
    privacy_mode: Literal['cloud_ai', 'local_only'] = 'cloud_ai'
    allow_video_upload: bool = False
    anthropic_model: str = Field(default='claude-sonnet-4-6', max_length=100)
    compatible_model: str = Field(default='', max_length=100)
    compatible_url: str = Field(default='', max_length=500)
    ollama_model: str = Field(default='qwen3-vl:8b', max_length=100)
    ollama_url: str = Field(default='http://127.0.0.1:11434/v1', max_length=500)
    freellmapi_model: str = Field(default='auto', max_length=100)
    freellmapi_url: str = Field(default='http://127.0.0.1:3001/v1', max_length=500)
    opencode_model: str = Field(default='freellmapi/auto', max_length=100)

    @field_validator('freellmapi_url')
    @classmethod
    def gateway_endpoint(cls, value):
        from .llm import validate_gateway
        return validate_gateway(value) if value else value

    @field_validator('compatible_url', 'ollama_url')
    @classmethod
    def endpoint(cls, value, info):
        from .llm import validate_endpoint
        return validate_endpoint(value, info.field_name == 'ollama_url') if value else value

    naver_provider: Literal['hub', 'legacy'] = 'hub'
    model: str = Field(default='gpt-4.1-mini', pattern=r'^[a-zA-Z0-9._:-]{1,100}$')
    tts_model: str = Field(default='gpt-4o-mini-tts', pattern=r'^[a-zA-Z0-9._:-]{1,100}$')
    tts_voice: str = Field(default='alloy', pattern=r'^[a-zA-Z0-9_-]{1,50}$')
    s3_bucket: str = Field(default='', max_length=100)
    s3_region: str = Field(default='ap-northeast-2', pattern=r'^[a-z0-9-]{1,50}$')
    meta_version: str = Field(default='v25.0', pattern=r'^v\d+\.0$')
    secrets: dict[str, str] = Field(default_factory=dict)


class AccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    user_id: str = Field(pattern=r'^\d{1,30}$')
    token: str = Field(min_length=10, max_length=5000)


class RevisionInput(BaseModel):
    revision: int = Field(ge=1)


class GenerateInput(BaseModel):
    revision: int = Field(ge=1)
    cards: int = Field(default=5, ge=3, le=10)
    scene_index: int | None = Field(default=None, ge=0, le=9)
    provider: Provider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=100, pattern=r'^\S+$')


class ArticleSummaryInput(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)


class ImageSearchInput(BaseModel):
    query: str = Field(min_length=2, max_length=300)


class ImageSelectInput(BaseModel):
    image_url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(default='', max_length=300)
    license: str = Field(min_length=1, max_length=100)
    license_url: str = Field(default='', max_length=1000)
    page_url: str = Field(min_length=1, max_length=2000)


class AppearanceInput(BaseModel):
    theme: Literal['dark', 'light'] | None = None
    nav_collapsed: bool | None = None
    nav_groups: dict[Literal['workspace', 'content', 'api', 'accounts', 'preferences', 'help'], bool] | None = None
