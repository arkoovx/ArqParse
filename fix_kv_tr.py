import re

with open('arqparse/ui/gui.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace app.tr("key") with app.tr("key", app.lang) in KV strings
# Look for pattern: app.tr("...")
# Ensure we don't replace if it already has app.lang or other args
new_content = re.sub(r'app\.tr\((["\'][^"\']+["\'])\)', r'app.tr(\1, app.lang)', content)

with open('arqparse/ui/gui.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f"Replaced {len(re.findall(r'app\.tr\(([\"\'][^\"\']+[\"\'])\)', content))} occurrences in gui.py")
