import json
r = json.load(open('_diag_result.json', encoding='utf-8'))
print('=== URL:', r['page_url'])
print('=== 标题框:', r['title_selector_found'])
print()

print(f'=== INPUTS ({len(r["inputs"])}) ===')
for i in r['inputs']:
    vis = '✅' if i.get('visible') else '❌'
    ph = i.get('placeholder','')[:50]
    t = i.get('type','')
    aria = i.get('aria','')[:30]
    role = i.get('role','')
    cls = i.get('cls','')[:100]
    bb = i.get('bbox')
    if bb:
        pos = f"x={bb['x']:.0f} y={bb['y']:.0f} w={bb['width']:.0f}"
    else:
        pos = 'no-bbox'
    print(f'  {vis} type={t:10s} ph={ph:50s} role={role:10s} [{pos}]')
    if cls:
        print(f'       cls={cls}')

print(f'\n=== TEXTAREAS ({len(r["textareas"])}) ===')
for t in r['textareas']:
    vis = '✅' if t.get('visible') else '❌'
    ph = t.get('placeholder','')[:50]
    aria = t.get('aria','')[:30]
    cls = t.get('cls','')[:100]
    bb = t.get('bbox')
    if bb:
        pos = f"x={bb['x']:.0f} y={bb['y']:.0f} w={bb['width']:.0f}"
    else:
        pos = 'no-bbox'
    print(f'  {vis} ph={ph:50s} [{pos}]')
    if cls:
        print(f'       cls={cls}')

print(f'\n=== CONTENTEDITABLE DIVS ({len(r["contenteditable_divs"])}) ===')
for d in r['contenteditable_divs']:
    vis = '✅' if d.get('visible') else '❌'
    role = d.get('role','')
    ph = d.get('placeholder','')[:50]
    aria = d.get('aria','')[:30]
    cls = d.get('cls','')[:100]
    bb = d.get('bbox')
    if bb:
        pos = f"x={bb['x']:.0f} y={bb['y']:.0f} w={bb['width']:.0f}"
    else:
        pos = 'no-bbox'
    print(f'  {vis} role={role:10s} ph={ph:50s} [{pos}]')
    if cls:
        print(f'       cls={cls}')

print('\n=== CLASS MATCHES ===')
for k, v in r['class_matches'].items():
    print(f'  class*={k:12s}: {v} 个')

print(f'\n=== VISIBLE BUTTONS ({len(r["buttons"])}) ===')
for b in r['buttons']:
    txt = b.get('text','')[:40]
    bb = b.get('bbox')
    if bb:
        pos = f"x={bb['x']:.0f} y={bb['y']:.0f} w={bb['width']:.0f}"
    else:
        pos = 'no-bbox'
    dis = 'DISABLED' if b.get('disabled') else ''
    cls = b.get('cls','')[:80]
    print(f'  [{pos}] {txt:40s} {dis}')
    if cls:
        print(f'       cls={cls}')
