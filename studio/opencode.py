"""Run a single content-generation request through the user's OpenCode CLI."""
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def executable():
    found = shutil.which('opencode')
    if found:
        return found
    # Finder-launched applications do not inherit the shell's PATH.
    for candidate in (Path.home()/'.opencode/bin/opencode', Path.home()/'.local/bin/opencode',
                      Path('/opt/homebrew/bin/opencode'), Path('/usr/local/bin/opencode')):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def environment(vault, settings):
    from .llm import validate_gateway
    model = settings.get('opencode_model', 'freellmapi/auto')
    if '/' not in model or not all(model.split('/', 1)):
        raise ValueError('OpenCode 모델은 provider/model 형식으로 입력하세요.')
    config = {'share': 'disabled', 'autoupdate': False,
              'agent': {'studio-content': {'mode': 'primary',
                         'description': 'Generate video scripts and captions as JSON only',
                         'permission': {'*': 'deny'}, 'tools': {'*': False}}}}
    env = dict(os.environ)
    env.pop('OPENCODE_AUTO_SHARE', None)
    if model.startswith('freellmapi/'):
        key = vault.get('freellmapi_key')
        if not key:
            raise ValueError('FreeLLMAPI 연결에서 통합 API 키를 먼저 저장하세요.')
        endpoint = validate_gateway(settings.get('freellmapi_url', 'http://127.0.0.1:3001/v1'))
        name = model.split('/', 1)[1]
        config['provider'] = {'freellmapi': {'npm': '@ai-sdk/openai-compatible',
            'name': 'FreeLLMAPI', 'options': {'baseURL': endpoint, 'apiKey': '{env:STUDIO_FREELLMAPI_KEY}'},
            'models': {name: {'name': name, 'modalities': {'input': ['text', 'image'], 'output': ['text']}}}}}
        env['STUDIO_FREELLMAPI_KEY'] = key
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(config)
    env['OPENCODE_DISABLE_AUTOUPDATE'] = 'true'
    env['OPENCODE_PERMISSION'] = '{"*":"deny"}'
    return env


def generate(vault, settings, prompt, content, schema):
    command = executable()
    if not command:
        raise ValueError('OpenCode CLI를 설치한 뒤 앱을 다시 실행하세요.')
    env = environment(vault, settings)
    cancel = settings.get('_cancel_event')
    track = settings.get('_process_callback', lambda p: None)
    with tempfile.TemporaryDirectory(prefix='studio-opencode-') as directory:
        env['PWD'] = directory
        args = [command, 'run', '--format', 'json', '--agent', 'studio-content',
                '--model', settings.get('opencode_model', 'freellmapi/auto')]
        texts = [prompt, 'Return only one JSON object matching this schema: '+json.dumps(schema, ensure_ascii=False)]
        for i, part in enumerate(content):
            if part['type'] == 'input_text':
                texts.append(part['text'])
            elif part['type'] == 'input_image':
                header, data = part['image_url'].split(',', 1)
                if header != 'data:image/jpeg;base64':
                    raise ValueError('OpenCode에는 JPEG 사진을 전달하세요.')
                image = Path(directory)/f'photo-{i}.jpg'
                image.write_bytes(base64.b64decode(data, validate=True))
                args.extend(['--file', str(image)])
                texts.append(f'첨부 사진: {image.name}')
        try:
            process = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        except OSError:
            raise ValueError('OpenCode를 실행하지 못했습니다. CLI 설치와 실행 권한을 확인하세요.') from None
        track(process)
        try:
            deadline = time.monotonic() + 180
            input_text = '\n\n'.join(texts)
            while True:
                if cancel and cancel.is_set():
                    raise InterruptedError('OpenCode 생성을 중단했습니다.')
                if time.monotonic() > deadline:
                    raise ValueError('OpenCode 응답 시간이 초과됐습니다. 연결과 모델을 확인하세요.')
                try:
                    stdout, _ = process.communicate(input=input_text, timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    input_text = None
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            track(None)
        if process.returncode:
            # Raw CLI errors can include credentials or the supplied source text.
            raise ValueError('OpenCode 생성 실패. OpenCode 로그인, 모델 ID, FreeLLMAPI 연결을 확인하세요.')
        return parse_events(stdout)


def models(vault, settings):
    command = executable()
    if not command:
        raise ValueError('OpenCode CLI를 설치하세요.')
    env = environment(vault, settings)
    with tempfile.TemporaryDirectory(prefix='studio-opencode-models-') as directory:
        env['PWD'] = directory
        try:
            result = subprocess.run([command, 'models'], cwd=directory, env=env, capture_output=True,
                                    text=True, encoding='utf-8', timeout=30, check=True)
        except (OSError, subprocess.SubprocessError):
            raise ValueError('OpenCode 모델 목록을 읽지 못했습니다. CLI 연결 설정을 확인하세요.') from None
    return sorted({line.strip() for line in result.stdout.splitlines()
                   if '/' in line and not any(c.isspace() for c in line.strip()) and len(line.strip()) <= 100})


def parse_events(stdout):
    text, usage = [], {}
    try:
        for line in stdout.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get('type') == 'error':
                raise ValueError()
            part = event.get('part', {})
            if event.get('type') == 'text':
                text.append(part['text'])
            elif event.get('type') == 'step_finish':
                usage = part.get('tokens', {})
        output = ''.join(text).strip()
        if output.startswith('```'):
            output = output.split('\n', 1)[1].rsplit('```', 1)[0]
        parsed = json.loads(output)
        if not isinstance(parsed, dict):
            raise ValueError()
        return parsed, usage
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ValueError('OpenCode가 올바른 JSON 초안을 반환하지 않았습니다. 기존 콘텐츠는 보존했습니다.') from None
