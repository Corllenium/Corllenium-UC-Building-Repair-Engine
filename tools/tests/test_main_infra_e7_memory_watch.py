import os
from pathlib import Path
import subprocess

import pytest


@pytest.mark.skipif(os.name != 'nt', reason='Windows resource counters')
def test_memory_watch_reads_global_and_worker_peaks_without_stopping_worker(tmp_path):
    script=Path(__file__).resolve().parents[2]/'docs/superpowers/records/scripts/main-infra/watch-e7-memory.ps1'
    assert script.is_file()
    out=tmp_path/'memory.jsonl'
    command=['pwsh','-NoProfile','-File',str(script),'-WorkerPid',str(os.getpid()),'-Output',str(out),'-MaxSamples','2','-IntervalMs','20']
    result=subprocess.run(command,capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr
    import json
    rows=[json.loads(line) for line in out.read_text(encoding='utf-8-sig').splitlines()]
    assert len(rows)==2 and all(row['worker_pid']==os.getpid() for row in rows)
    assert all(0<row['system_commit_bytes']<=row['system_commit_limit_bytes'] for row in rows)
    assert all(row['worker_peak_commit_bytes']>=row['worker_private_bytes']>0 for row in rows)
    assert all(row['worker_peak_working_set_bytes']>=row['worker_working_set_bytes']>0 for row in rows)
    second=subprocess.run(command,capture_output=True,text=True,timeout=25)
    assert second.returncode!=0
    assert len(out.read_text(encoding='utf-8-sig').splitlines())==2
    assert os.getpid()>0
