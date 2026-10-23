import ctypes as c,json,os,subprocess,sys,time
from ctypes import wintypes as w
from pathlib import Path
class Entry(c.Structure):
 _fields_=[('size',w.DWORD),('usage',w.DWORD),('pid',w.DWORD),('heap',c.c_size_t),('module',w.DWORD),('threads',w.DWORD),('parent',w.DWORD),('priority',w.LONG),('flags',w.DWORD),('exe',w.WCHAR*260)]
class Mem(c.Structure):
 _fields_=[('cb',w.DWORD),('faults',w.DWORD)]+[(n,c.c_size_t) for n in ('peak_ws','ws','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
k=c.WinDLL('kernel32',use_last_error=True);papi=c.WinDLL('psapi',use_last_error=True)
k.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];k.CreateToolhelp32Snapshot.restype=w.HANDLE
k.Process32FirstW.argtypes=[w.HANDLE,c.POINTER(Entry)];k.Process32NextW.argtypes=[w.HANDLE,c.POINTER(Entry)]
k.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];k.OpenProcess.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE];k.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
papi.GetProcessMemoryInfo.argtypes=[w.HANDLE,c.POINTER(Mem),w.DWORD]
def private(pid):
 h=k.OpenProcess(0x1000,False,pid)
 if not h:return 0
 try:
  m=Mem();m.cb=c.sizeof(m)
  return m.private if papi.GetProcessMemoryInfo(h,c.byref(m),m.cb) else 0
 finally:k.CloseHandle(h)
def descendants(root):
 h=k.CreateToolhelp32Snapshot(2,0)
 if h in (None,c.c_void_p(-1).value):raise OSError('process inventory unavailable')
 try:
  row=Entry();row.size=c.sizeof(row);pairs=[];ok=k.Process32FirstW(h,c.byref(row))
  while ok:pairs.append((row.pid,row.parent));ok=k.Process32NextW(h,c.byref(row))
 finally:k.CloseHandle(h)
 ids={root}
 while True:
  more={pid for pid,parent in pairs if parent in ids}-ids
  if not more:return ids
  ids.update(more)
root=Path.cwd();e=root/'docs/superpowers/records/MAIN-INFRA-1F-VALIDATE-RETAIN-VISIBLE-20261024';label=sys.argv[1];temp=Path('D:/TEMP/iv1f-retained')/label;temp.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONPATH=str(root),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',TEMP=str(temp),TMP=str(temp),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
py='D:/PROJECTS/UC MODEL FIXER/.venv/Scripts/python.exe'
cmd=[py,'-B','-m','pytest','tools/tests/test_main_infra_1f_retained_validation.py','-q','-p','no:cacheprovider','--basetemp',str(temp/'pytest')]
if len(sys.argv)>2:cmd+=['-k',sys.argv[2]]
if label=='shared-green':cmd=[py,'-B','-m','pytest','tools/tests/test_main_infra_2f_validation.py','tools/tests/test_main_infra_3f_validation.py','tools/tests/test_main_infra_1f_retained_validation.py','-q','-p','no:cacheprovider','--basetemp',str(temp/'pytest')]
if label=='terminal-static':cmd=[py,'-B','-m','data.tmp.attempt4_terminal_static']
if label.startswith('static-smoke'):cmd=[py,'-B','-m','data.tmp.attempt4_static_preparation']
if label=='cli-help':cmd=[py,'-B','-m','tools.main_infra_e7_independent_attempt4','--help']
with (e/(label+'.txt')).open('wb') as out,(e/(label+'-stderr.txt')).open('wb') as err:
 proc=subprocess.Popen(cmd,cwd=root,env=env,stdout=out,stderr=err);peak=obs_peak=0;peaks={};breach=False
 while proc.poll() is None:
  ids=descendants(proc.pid);current={pid:private(pid) for pid in ids};obs=private(os.getpid());peak=max(peak,sum(current.values()));obs_peak=max(obs_peak,obs)
  for pid,value in current.items():peaks[pid]=max(value,peaks.get(pid,0))
  if sum(current.values())+obs>250*1024*1024:
   breach=True
   for pid in ids:
    h=k.OpenProcess(1,False,pid)
    if h:k.TerminateProcess(h,99);k.CloseHandle(h)
   break
  time.sleep(.05)
 code=proc.wait()
result=dict(command=cmd,exit_code=code,test_tree_private_peak=peak,observer_private_peak=obs_peak,pid_private_peaks=peaks,cap_bytes=250*1024*1024,cap_exceeded=breach)
(e/(label+'-process.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));print((e/(label+'.txt')).read_text()[-9000:]);raise SystemExit(99 if breach else code)
