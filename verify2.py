import py_compile
py_compile.compile('app.py', doraise=True)
print('app.py OK')
import os
for f in ['fix_step.py', 'fix_step2.py', 'fix_es.py']:
    if os.path.exists(f):
        os.remove(f)
print('cleaned')
