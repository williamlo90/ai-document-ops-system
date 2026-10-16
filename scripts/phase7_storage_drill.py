"""Verify a quiesced release volume's backup and restore without overwriting it."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

DRILL = r"""
import hashlib,json,shutil,sqlite3,uuid
from pathlib import Path
root=Path('/data'); saved=root/'backups'/('release-'+uuid.uuid4().hex[:10])
restored=root/'restore-drill'/saved.name
saved.mkdir(parents=True);restored.mkdir(parents=True)
source=sqlite3.connect(root/'invoice-review.sqlite3')
backup=sqlite3.connect(saved/'invoice-review.sqlite3');source.backup(backup);backup.close()
shutil.copytree(root/'uploads',saved/'uploads')
shutil.copy2(saved/'invoice-review.sqlite3',restored/'invoice-review.sqlite3')
shutil.copytree(saved/'uploads',restored/'uploads')
copy=sqlite3.connect(restored/'invoice-review.sqlite3')
assert copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert not copy.execute('PRAGMA foreign_key_check').fetchall()
tables=['documents','jobs','extractions','audit_events','ap_versions','ap_scope_locks']
def fingerprint(connection,table):
 rows=connection.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
 return len(rows),hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()
records={table:fingerprint(source,table) for table in tables}
assert records=={table:fingerprint(copy,table) for table in tables}
def objects(path):
 return {str(p.relative_to(path)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in path.rglob('*') if p.is_file()}
files=objects(root/'uploads');assert files==objects(restored/'uploads')
print(json.dumps({'status':'passed','integrity':'ok','foreign_key_errors':0,
 'tables':{k:{'rows':v[0],'sha256':v[1]} for k,v in records.items()},
 'upload_objects_verified':len(files),'original_volume_overwritten':False}))
copy.close();source.close()
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = subprocess.check_output(
        ["docker", "ps", "--format", "{{.Names}}"], text=True
    ).splitlines()
    if any(
        name in names
        for name in ("invoice-review-release-api-1", "invoice-review-release-worker-1")
    ):
        raise SystemExit("Stop release API and worker before copying database and uploads together")
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--read-only",
            "--memory",
            "128m",
            "--volumes-from",
            "invoice-review-release-api-1",
            "--entrypoint",
            "python",
            "invoice-review:phase7-local",
            "-",
        ],
        input=DRILL,
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
