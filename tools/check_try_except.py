import sys
from collections import defaultdict
p = sys.argv[1] if len(sys.argv)>1 else r'd:\GitHub Local Repository\EOL-Host-Application\host_gui\main.py'
with open(p,'r',encoding='utf-8') as f:
    lines = f.readlines()
stack = []
problems=[]
for i,line in enumerate(lines, start=1):
    stripped=line.lstrip('\t')
    indent=len(line)-len(stripped)
    tok=line.strip()
    if tok.startswith('try:'):
        stack.append((i,indent))
    elif tok.startswith('except') or tok.startswith('finally'):
        if not stack:
            problems.append((i,'Unmatched except/finally'))
        else:
            # pop last try with indent <= current indent
            # find matching try with indent <= current
            for j in range(len(stack)-1,-1,-1):
                if stack[j][1]==indent:
                    stack.pop(j)
                    break
            else:
                # no matching indent-level try
                stack.pop() if stack else None

if stack:
    for t in stack:
        problems.append((t[0],'try without except/finally'))

if problems:
    for p in problems:
        print('Problem at line',p[0],p[1])
    sys.exit(1)
print('Try/except check OK')
