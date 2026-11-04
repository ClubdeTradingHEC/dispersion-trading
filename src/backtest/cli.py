"""Strict command-line QA using the team's preserved cost-reporting calculation."""
import argparse
import contextlib
import os
import json
from pathlib import Path
from src.data.validate_straddle_costs import validate_costs


# Keep the original reporting script unchanged; provide an automation-safe exit code.
def main(argv=None):
    parser=argparse.ArgumentParser(prog='dispersion-costs',description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    validate=sub.add_parser('validate',help='Offline: nonzero exit when any cost row fails QA')
    validate.add_argument('--input',required=True)
    args=parser.parse_args(argv)
    try:
        # The original report prints raw rows. Automated QA reports counts only.
        with open(os.devnull,'w',encoding='utf-8') as sink:
            with contextlib.redirect_stdout(sink):
                frame,_=validate_costs(Path(args.input))
        passed=int(frame.passes_qa.sum())
        failed=len(frame)-passed
        status='PASS' if len(frame)>0 and failed==0 else 'FAIL'
        print(json.dumps({'status':status,'rows':len(frame),'passed':passed,'failed':failed}))
        return 0 if status=='PASS' else 1
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'status':'FAIL','error_type':type(exc).__name__,
                          'hint':'Check the input path, required quote columns and numeric values'}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
