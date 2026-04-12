import re

with open('db.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Add imports
if 'from app_cache import' not in code:
    code = code.replace('import json', 'import json\nfrom app_cache import ttl_cache, invalidate_cache')

def decorate_and_invalidate(getter, setters, getters_to_invalidate=None):
    global code
    if getters_to_invalidate is None:
        getters_to_invalidate = [getter]
        
    pattern_getter = r'(async def ' + getter + r'\()'
    if f'@ttl_cache' not in code.split('async def ' + getter + '(')[0][-50:]:
        code = re.sub(pattern_getter, r'@ttl_cache(ttl_seconds=60)\n\1', code, count=1)
        
    for setter in setters:
        setter_sig = f'async def {setter}('
        if setter_sig in code:
            parts = code.split(setter_sig)
            pre = parts[0]
            rest = parts[1]
            
            lines = rest.split('\n')
            new_lines = []
            for i, line in enumerate(lines):
                if line.startswith('async def'):
                    new_lines.extend(lines[i:])
                    break
                if line.strip().startswith('return '):
                    indent = line[:len(line) - len(line.lstrip())]
                    for g in getters_to_invalidate:
                        new_lines.append(f'{indent}invalidate_cache({g}, chat_id)')
                new_lines.append(line)
            code = pre + setter_sig + '\n'.join(new_lines)


decorate_and_invalidate('get_notification_mode', ['set_notification_mode'])
decorate_and_invalidate('get_tg_notification_mode', ['set_tg_notification_mode'])
decorate_and_invalidate('get_tg_activity_notification_enabled', ['set_tg_activity_notification_enabled', 'toggle_tg_activity_notification'])
decorate_and_invalidate('get_tg_change_notification_settings', ['set_tg_change_notification_enabled', 'toggle_tg_change_notification'])
decorate_and_invalidate('get_change_notification_settings', ['set_change_notification_enabled', 'toggle_change_notification'])

with open('db.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Patch applied')
