"""Model status uses saved metadata only; never retrieves API credentials."""
from .llm import PROVIDERS
from .models import SettingsInput
from .storage import new_id, now

FIELDS = {'openai': ('model', None, 'openai_key'),
          'anthropic': ('anthropic_model', None, 'anthropic_key'),
          'compatible': ('compatible_model', 'compatible_url', 'compatible_key'),
          'freellmapi': ('freellmapi_model', 'freellmapi_url', 'freellmapi_key'),
          'opencode': ('opencode_model', None, None),
          'ollama': ('ollama_model', 'ollama_url', None)}


def effective(settings):
    return {**SettingsInput().model_dump(exclude={'secrets'}), **settings}


def signature(settings, provider):
    s = effective(settings)
    model, endpoint, _ = FIELDS[provider]
    address = s[endpoint] if endpoint else ''
    if provider == 'opencode' and s[model].startswith('freellmapi/'):
        address = s['freellmapi_url'] + ':' + s.get('_llm_revisions', {}).get('freellmapi', '')
    return [s[model], address, s.get('_llm_revisions', {}).get(provider, '')]


def invalidate(old, updated, changed_secrets):
    revisions = dict(old.get('_llm_revisions', {}))
    checks = dict(old.get('_llm_checks', {}))
    for provider, (_, _, key) in FIELDS.items():
        if signature(old, provider)[:2] != signature(updated, provider)[:2] or key in changed_secrets:
            revisions[provider] = new_id()
            checks.pop(provider, None)
    return {**updated, '_llm_revisions': revisions, '_llm_checks': checks}


def record_check(store, provider, snapshot, result):
    with store.lock:
        current = store.settings()
        if signature(current, provider) != signature(snapshot, provider):
            return False
        checks = dict(current.get('_llm_checks', {}))
        checks[provider] = {'signature': signature(snapshot, provider), 'result': result, 'tested_at': now()}
        store.save_settings({**current, '_llm_checks': checks})
        return True


def statuses(settings, flags):
    s = effective(settings)
    rows = []
    for provider, (model, endpoint, key) in FIELDS.items():
        configured = bool(s[model].strip()) and (not endpoint or bool(s[endpoint].strip()))
        key_present = bool(flags.get(key, False)) if key else None
        missing = []
        if not s[model].strip(): missing.append('모델 이름')
        if endpoint and not s[endpoint].strip(): missing.append('로컬 API 주소' if provider == 'ollama' else 'API 기본 주소')
        if key and not key_present: missing.append('API 키')
        if provider == 'opencode':
            from .opencode import executable
            if not executable(): missing.append('OpenCode CLI 설치')
            if '/' not in s[model] or not all(s[model].split('/', 1)): missing.append('provider/model 형식')
            if s[model].startswith('freellmapi/'):
                if not s['freellmapi_url'].strip(): missing.append('FreeLLMAPI 주소')
                if not flags.get('freellmapi_key'): missing.append('FreeLLMAPI 키')
        check = s.get('_llm_checks', {}).get(provider)
        if check and check.get('signature') != signature(s, provider):
            check = None
        rows.append({'provider': provider, 'label': PROVIDERS[provider], 'model': s[model],
                     'selected': provider == s['llm_provider'], 'configuration_complete': configured,
                     'key_registered': key_present, 'missing_fields': missing, 'blocked': s['privacy_mode'] == 'local_only' and provider != 'ollama',
                     'test_result': check['result'] if check else 'untested',
                     'tested_at': check['tested_at'] if check else None})
    return rows


def generation_settings(settings, flags, provider=None, model=None):
    snapshot = effective(settings)
    selected = provider or snapshot['llm_provider']
    snapshot['llm_provider'] = selected
    if model is not None:
        snapshot[FIELDS[selected][0]] = model
    row = next(row for row in statuses(snapshot, flags) if row['provider'] == selected)
    if row['blocked']:
        raise ValueError('로컬 전용 모드에서는 로컬 Ollama를 선택하세요.')
    if row['missing_fields']:
        raise ValueError(row['label'] + ' 연결을 먼저 완료하세요: ' + ' · '.join(row['missing_fields']))
    return snapshot
