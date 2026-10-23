"""Prepare/execute a new conservative E7 subset with an external policy SHA pin."""
import argparse
from pathlib import Path

from tools import main_infra_e7_attempt3 as run
from tools.main_infra_e7_native_policy import RUN_ID
from engine.io.snapshot import sha256_file


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','execute'])
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--policy-sha256',required=True)
    args=parser.parse_args(argv)
    pin=dict(path=str(args.policy.resolve()),sha256=args.policy_sha256)
    if args.action=='prepare':
        if args.out is None:parser.error('prepare requires --out')
        value=run.prepare(run.legacy.real_paths(),run.real_donor(),run.DONOR_HASHES,args.plan,args.out,native_policy=pin)
        print(run._dump(dict(state=value['state'],run_id=RUN_ID,selected=value['selection']['selected'],plan_sha256=sha256_file(args.plan))))
    else:
        if not args.plan_sha256:parser.error('execute requires --plan-sha256')
        run.execute(args.plan,args.plan_sha256,native_policy=pin)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
