import sys
p = sys.argv[1] if len(sys.argv)>1 else r"d:\GitHub Local Repository\EOL-Host-Application\host_gui\main.py"
start = int(sys.argv[2]) if len(sys.argv)>2 else 1728
end = int(sys.argv[3]) if len(sys.argv)>3 else 1752
with open(p, 'rb') as f:
    lines = f.read().splitlines()
for i in range(start-1, min(end, len(lines))):
    print(f"{i+1:5d}: {lines[i].decode('utf-8', errors='replace')!r}")
