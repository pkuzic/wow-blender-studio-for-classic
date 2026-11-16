# Run the WBS GUI test suite:   py -3 tools/run_tests.py [name-filter ...] [--client PATH] [--blender EXE]
# Each tests/test_*.py runs in its own GUI Blender (needs OpenGL) with a fresh BLENDER_USER_CONFIG, placed on
# a second screen without taking focus. Prints a summary; exit code 1 when anything failed.
# Environment passed to each test: see tests/common.py (WBS_CLIENT, WBS_TEST_OUT, WBS_TEST_TMP, WBS_ADDON).
import os
import sys
import json
import glob
import time
import shutil
import argparse
import subprocess
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # the add-on folder
ADDON = os.path.basename(HERE)
SCRIPTS = os.path.dirname(os.path.dirname(HERE))                             # .../scripts (contains addons/)

ap = argparse.ArgumentParser()
ap.add_argument('filters', nargs='*')
ap.add_argument('--client', default=os.environ.get('WBS_CLIENT', r"G:\tw_experiment\benilla_local"))
ap.add_argument('--blender', default=os.environ.get('WBS_BLENDER', r"G:\blender\blender.exe"))
ap.add_argument('--timeout', type=int, default=1800)
ap.add_argument('--window', default='2580,123,1600,1000', help='x,y,w,h of the Blender window')
args = ap.parse_args()

tests = sorted(glob.glob(os.path.join(HERE, 'tests', 'test_*.py')))
if args.filters:
    tests = [t for t in tests if any(f.lower() in os.path.basename(t).lower() for f in args.filters)]
if not tests:
    sys.exit('no tests matched')

root = tempfile.mkdtemp(prefix='wbs_tests_')
x, y, w, h = args.window.split(',')
total_fail = 0
summary = []
for t in tests:
    name = os.path.splitext(os.path.basename(t))[0]
    work = os.path.join(root, name)
    os.makedirs(os.path.join(work, 'config'))
    out = os.path.join(work, 'result.json')
    env = dict(os.environ, BLENDER_USER_SCRIPTS=SCRIPTS, BLENDER_USER_CONFIG=os.path.join(work, 'config'),
               WBS_CLIENT=args.client, WBS_TEST_OUT=out, WBS_TEST_TMP=os.path.join(work, 'tmp'), WBS_ADDON=ADDON,
               PYTHONPATH=os.path.join(HERE, 'tests'))
    t0 = time.time()
    with open(os.path.join(work, 'stdout.txt'), 'w', encoding='utf-8', errors='replace') as log:
        try:
            subprocess.run([args.blender, '-noaudio', '--no-window-focus', '-p', x, y, w, h, '--python', t],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            pass
    try:
        with open(out, encoding='utf-8') as f:
            res = json.load(f)
    except Exception:
        res = {'name': name, 'passed': 0, 'failed': 1, 'checks': [], 'error': 'no result file (crash or timeout) - see '
               + os.path.join(work, 'stdout.txt')}
    total_fail += res['failed']
    summary.append((name, res['passed'], res['failed'], time.time() - t0))
    print('%-32s %3d passed  %3d failed  %5.0fs' % (name, res['passed'], res['failed'], time.time() - t0))
    for c in res.get('checks', []):
        if c['ok'] is False:
            print('    FAIL: ' + c['msg'])
    if res.get('error'):
        print('    ERROR: ' + res['error'].strip().splitlines()[-1])
print('-' * 60)
print('TOTAL: %d tests, %d failed checks. Logs: %s' % (len(summary), total_fail, root))
sys.exit(1 if total_fail else 0)
