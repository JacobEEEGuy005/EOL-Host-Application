p = r'd:\GitHub Local Repository\EOL-Host-Application\host_gui\main.py'
with open(p,'rb') as f:
    lines = f.read().splitlines()
for i,line in enumerate(lines, start=1):
    s=line.decode('utf-8', errors='replace')
    if 'try:' in s or s.strip().startswith('except') or s.strip().startswith('finally'):
        indent = len(s) - len(s.lstrip(' '))
        print(f"{i:5d} indent={indent} -> {s.rstrip()}")
