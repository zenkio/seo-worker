from __future__ import annotations
import argparse
import signal
import sys
import time
from pathlib import Path
from .core import run


def main() -> None:
    p=argparse.ArgumentParser(prog="seo-worker",description="Polite, deterministic SEO audits with local reports and history")
    p.add_argument("--config",default="site.yml",help="Site YAML config")
    p.add_argument("--output",default="reports/latest",help="Report output directory")
    p.add_argument("--repo",help="Optional local repository for patch suggestions")
    p.add_argument("--apply",action="store_true",help="Enable local-repository apply workflow (never changes live sites)")
    p.add_argument("--daemon",action="store_true",help="Run repeatedly using interval_seconds from config")
    args=p.parse_args()
    config=Path(args.config).expanduser().resolve(); output=Path(args.output).expanduser().resolve()
    repo=Path(args.repo).expanduser().resolve() if args.repo else None
    if args.apply and (repo is None or not repo.is_dir()): p.error("--apply requires --repo pointing to an existing local repository")
    if args.apply:
        print("Apply mode can add missing canonical tags to exact-match static HTML files in --repo. Review local changes before keeping them; no live site is changed.",file=sys.stderr)
    while True:
        try:
            result=run(config,output,repo,args.apply)
            print(f"Run {result['run_id']}: {len(result['pages'])} pages, {len(result['issues'])} findings. Reports: {output}")
        except Exception as exc:
            print(f"SEO run failed: {exc}",file=sys.stderr)
            if not args.daemon: raise
        if not args.daemon: break
        import yaml
        with config.open(encoding="utf-8") as f: cfg=yaml.safe_load(f) or {}
        interval=int(cfg.get("schedule",{}).get("interval_seconds",86400))
        time.sleep(max(60,interval))

if __name__ == "__main__": main()
