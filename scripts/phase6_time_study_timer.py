"""Record the next human-operated study condition; never generate invoice answers or timings."""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path


def stamp():
    return datetime.now(UTC).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worksheet", type=Path)
    parser.add_argument("--operator", required=True)
    args = parser.parse_args()
    worksheet = args.worksheet.resolve()
    lock = worksheet.with_suffix(".timer.lock")
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(stamp())
    try:
        data = json.loads(worksheet.read_text(encoding="utf-8"))
        if data.get("protocol_version") != "phase6-paired-v1":
            raise SystemExit("Unsupported study protocol")
        if data.get("operator_id") not in (None, args.operator):
            raise SystemExit("The frozen study operator cannot be changed")
        data["operator_id"] = args.operator
        if not data.get("operator_familiarity"):
            data["operator_familiarity"] = input("Pengalaman Anda dengan aplikasi dan ERPNext: ").strip()
            if not data["operator_familiarity"]:
                raise SystemExit("Operator familiarity must be recorded")
        scheduled = [(pair, run) for pair in data["pairs"] for run in pair["runs"]]
        pending = next(((pair, run) for pair, run in scheduled if run.get("elapsed_seconds") is None), None)
        if pending is None:
            print("Semua kondisi sudah dicatat. Selanjutnya verifikasi output dan scoring.")
            return
        pair, run = pending
        if run.get("attempt_started_at"):
            raise SystemExit("Attempt sebelumnya terputus; catat sebagai gagal sebelum melanjutkan agar denominator tetap utuh.")
        print(f"Invoice: {pair['document_id']} | Kondisi: {run['condition']}")
        print(f"PDF: {pair['source_pdf']}")
        print("Sumber ERP:", pair["procurement_sources"][run["condition"]])
        input("Tekan Enter sebelum mulai membaca invoice. ")
        run["attempt_started_at"] = stamp()
        worksheet.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        tick = time.perf_counter()
        interval_started = stamp()
        state = "active"
        intervals = []
        print("p = pause menunggu sistem, r = lanjut bekerja, done = outcome tercapai, skip = gagal/dilewati")
        while True:
            command = input("> ").strip().casefold()
            if command not in {"p", "r", "done", "skip"}:
                continue
            if (command == "p" and state == "waiting") or (command == "r" and state == "active"):
                continue
            now = time.perf_counter()
            intervals.append({"kind": state, "started_at": interval_started,
                              "ended_at": stamp(), "seconds": round(now - tick, 3)})
            tick, interval_started = now, stamp()
            if command in {"done", "skip"}:
                break
            state = "waiting" if command == "p" else "active"
        run["timer_intervals"] = intervals
        run["active_seconds"] = round(sum(row["seconds"] for row in intervals if row["kind"] == "active"), 3)
        run["elapsed_seconds"] = round(sum(row["seconds"] for row in intervals), 3)
        if command == "skip":
            run["terminal_outcome"] = "skipped"
        else:
            outcome = input("Outcome (posted_verified / exception_resolved / failed): ").strip()
            if outcome not in {"posted_verified", "exception_resolved", "failed"}:
                outcome = "failed"
            run["terminal_outcome"] = outcome
        run["erp_readback_reference"] = input("ID invoice ERP atau referensi bukti hold (kosong jika tidak ada): ").strip() or None
        run["operator_notes"] = input("Catatan/kendala (boleh kosong): ").strip() or None
        temporary = worksheet.with_suffix(".writing.json")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(worksheet)
        count = sum(item.get("elapsed_seconds") is not None for _, item in scheduled)
        print(f"Tercatat {count}/{len(scheduled)} kondisi. Output invoice dan read-back tetap harus diverifikasi sebelum scoring.")
    finally:
        lock.unlink()


if __name__ == "__main__":
    main()
