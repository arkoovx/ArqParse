import re

with open('arqparse/ui/gui.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace app.tr("key") with app.tr("key", app.lang) in KV strings
# Look for pattern: app.tr("...")
# Ensure we don't replace if it already has app.lang or other args
pattern = r'app\.tr\((["\'][^"\']+["\'])\)'
new_content = re.sub(pattern, r'app.tr(\1, app.lang)', content)

with open('arqparse/ui/gui.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

matches = re.findall(pattern, content)
print(f"Replaced {len(matches)} occurrences in gui.py")
