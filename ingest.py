"""Student B's ingestion (written by Claude as Colt's partner), built from the agreed rules.md.

Usage:  python ingest.py <books.csv>

Writes books.db and ingestion-log.json next to this file. Standard library only.
"""
import csv
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
DATABASE = FOLDER / "books.db"
LOGFILE = FOLDER / "ingestion-log.json"

SCI = re.compile(r"^\d(?:\.\d+)?[eE]\+?\d+$")


# ----- ISBN arithmetic (rules.md section 1) ---------------------------------

def check10(isbn):
    if len(isbn) != 10 or not isbn[:9].isdigit() or not (isbn[9].isdigit() or isbn[9] == "X"):
        return False
    values = [int(ch) for ch in isbn[:9]] + [10 if isbn[9] == "X" else int(isbn[9])]
    return sum(v * w for v, w in zip(values, range(10, 0, -1))) % 11 == 0


def check13(isbn):
    if len(isbn) != 13 or not isbn.isdigit() or isbn[:3] not in ("978", "979"):
        return False
    return sum(int(ch) * (3 if i % 2 else 1) for i, ch in enumerate(isbn)) % 10 == 0


def ten_to_thirteen(isbn10):
    body = "978" + isbn10[:9]
    s = sum(int(ch) * (3 if i % 2 else 1) for i, ch in enumerate(body))
    return body + str(-s % 10)


def rounds_to(isbn13, sci_text):
    """Settled detail 12: equal after rounding to 12 significant digits."""
    return float(f"{int(isbn13):.11e}") == float(sci_text)


# ----- One cell at a time ---------------------------------------------------
# Each returns (kind, value, note):
#   kind "none"    -> nothing there
#   kind "ok10"    -> valid ISBN-10 in value
#   kind "ok13"    -> valid ISBN-13 in value
#   kind "sci"     -> scientific-notation 978/979 value (incomplete)
#   kind "bad"     -> looks like an ISBN but is wrong; note says why
#   kind "foreign" -> isbn13 cell holding a code that isn't an ISBN-13 at all
# note on ok10/ok13 lists the certain repairs made (empty if none).

def read_isbn10_cell(text):
    if text.strip() == "":
        return "none", None, ""
    fixes = []
    v = text.replace(" ", "").replace("-", "").replace("\t", "")
    if v != text:
        fixes.append("removed hyphens/spaces")
    if len(v) == 13 and v.isdigit():
        if check13(v):
            fixes.append("ISBN-13 was in the ISBN-10 column")
            return "ok13", v, "; ".join(fixes)
        return "bad", None, "13 digits but not a valid ISBN-13"
    if v.endswith("x") and v[:-1].isdigit():
        v = v[:-1] + "X"
        fixes.append("uppercased x")
    if not re.fullmatch(r"\d*[\dX]", v):
        return "bad", None, "has characters that can't be in an ISBN"
    if len(v) > 10:
        return "bad", None, f"{len(v)} characters, too long"
    if len(v) < 10:
        padded = v.zfill(10)
        if check10(padded):
            fixes.append(f"restored {10 - len(v)} leading zero(s)")
            return "ok10", padded, "; ".join(fixes)
        return "bad", None, "too short, and adding zeros doesn't make it valid"
    if check10(v):
        return "ok10", v, "; ".join(fixes)
    if v.isdigit() and check13("978" + v):
        return "bad", None, "looks like an ISBN-13 with 978 cut off (not repaired: inference)"
    return "bad", None, "check digit is wrong"


def read_isbn13_cell(text):
    if text.strip() == "":
        return "none", None, ""
    v = text.replace(" ", "").replace("-", "").replace("\t", "")
    fixes = "removed hyphens/spaces" if v != text else ""
    if SCI.match(v):
        n = float(v)
        digits = f"{n:.0f}"
        if n == int(n) and len(digits) == 13 and digits[:3] in ("978", "979"):
            return "sci", v, ""
        return "foreign", None, "scientific-notation code that isn't a 978/979 ISBN-13"
    if v.isdigit() and len(v) == 13:
        if v[:3] not in ("978", "979"):
            return "foreign", None, "13-digit code without a 978/979 prefix"
        if check13(v):
            return "ok13", v, fixes
        return "bad", None, "check digit is wrong"
    return "foreign", None, "not a 13-digit ISBN (decimal, truncated or another barcode)"


def decide_isbns(raw10, raw13):
    """Rules section 2 + settled details 2, 5, 9, 12. Returns (isbn10, isbn13, problems)."""
    k10, v10, n10 = read_isbn10_cell(raw10)
    k13, v13, n13 = read_isbn13_cell(raw13)
    problems = []

    if k10 in ("ok10", "ok13") and n10:
        problems.append(("repaired", "isbn", raw10, n10))
    if k10 == "bad":
        problems.append(("isbn left out", "isbn", raw10, n10))
    if k13 == "ok13" and n13:
        problems.append(("repaired", "isbn13", raw13, n13))
    if k13 == "bad":
        problems.append(("isbn left out", "isbn13", raw13, n13))
    if k13 == "foreign":
        problems.append(("ignored", "isbn13", raw13, n13))

    stored10 = v10 if k10 == "ok10" else None
    proposals = set()
    if k10 == "ok10":
        proposals.add(ten_to_thirteen(v10))
    if k10 == "ok13":
        proposals.add(v10)
    if k13 == "ok13":
        proposals.add(v13)

    def neither(why):
        kept = [p for p in problems if p[0] != "repaired"]
        return None, None, kept + [("isbn left out", "isbn + isbn13", f"{raw10} | {raw13}", why)]

    if len(proposals) > 1:
        return neither("ISBN-10 and ISBN-13 are both valid but are different books")
    stored13 = proposals.pop() if proposals else None

    if k13 == "sci":
        if stored13 is None:
            problems.append(("isbn left out", "isbn13", raw13,
                             "scientific notation without a valid ISBN-10; rebuilding would be a guess"))
        elif rounds_to(stored13, v13):
            problems.append(("repaired", "isbn13", raw13, f"rebuilt from the ISBN-10 as {stored13}"))
        else:
            return neither("rounded ISBN-13 does not match the ISBN-10")

    if k10 == "none" and k13 == "none":
        problems.append(("no isbn", "isbn + isbn13", "", "no ISBN in either column"))
    return stored10, stored13, problems


# ----- Database --------------------------------------------------------------

def connect(header):
    columns = ["isbn10" if h == "isbn" else h for h in header]
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE IF NOT EXISTS books ("
        + ", ".join("book_id INTEGER PRIMARY KEY" if c == "book_id" else f'"{c}" TEXT' for c in columns)
        + ", loaded_at TEXT, updated_at TEXT)"
    )
    return db, columns


# ----- The run ---------------------------------------------------------------

def run(path):
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    report = {"timestamp": started, "source_file": Path(path).name, "rows_read": 0, "loaded": 0,
              "updated": 0, "skipped": 0, "rejected": 0, "not_loaded": [], "warnings": []}

    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        db, columns = connect(header)
        prev_end = reader.line_num
        for cells in reader:
            line = prev_end + 1
            prev_end = reader.line_num
            if not cells:
                continue
            report["rows_read"] += 1
            handle_row(db, header, columns, cells, line, started, report)
        db.commit()
        db.close()

    total = report["loaded"] + report["updated"] + report["skipped"] + report["rejected"]
    report["counts_add_up"] = total == report["rows_read"]
    return report


def handle_row(db, header, columns, cells, line, now, report):
    def reject(book_id, title, value, why, todo):
        report["rejected"] += 1
        report["not_loaded"].append({"line": line, "book_id": book_id, "title": title,
                                     "value": value, "reason": why, "what_to_do": todo})

    def warn(book_id, title, problems):
        for outcome, column, original, why in problems:
            report["warnings"].append({"line": line, "book_id": book_id, "title": title, "outcome": outcome,
                                       "column": column, "original": original, "reason": why})

    if len(cells) != len(header):
        return reject(None, None, f"{len(cells)} columns",
                      f"expected {len(header)} columns", "Fix this line in the file and send it again.")
    row = dict(zip(header, cells))
    if not re.fullmatch(r"\d+", row["book_id"]):
        return reject(row["book_id"], row["title"], row["book_id"], "book_id missing or not a whole number",
                      "Ask the supplier for the book_id.")
    book_id = int(row["book_id"])
    if row["title"].strip() == "":
        return reject(book_id, row["title"], "", "title is empty", "Ask the supplier for the title.")

    isbn10, isbn13, problems = decide_isbns(row["isbn"], row["isbn13"])

    # Section 3: same book = same ISBN-13; otherwise by book_id.
    if isbn13:
        holder = db.execute("SELECT book_id, title FROM books WHERE isbn13 = ?", (isbn13,)).fetchone()
        if holder and holder["book_id"] != book_id:
            problems.append(("isbn left out", "isbn + isbn13", f"{row['isbn']} | {row['isbn13']}",
                             f"ISBN-13 {isbn13} already belongs to book_id {holder['book_id']} ({holder['title']})"))
            isbn10 = isbn13 = None

    record = {c: row[h] for c, h in zip(columns, header)}
    record["book_id"] = book_id
    record["isbn10"] = isbn10
    record["isbn13"] = isbn13

    old = db.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
    if old is None:
        names = list(record) + ["loaded_at", "updated_at"]
        db.execute(f"INSERT INTO books ({', '.join(chr(34) + n + chr(34) for n in names)}) "
                   f"VALUES ({', '.join('?' * len(names))})", list(record.values()) + [now, None])
        report["loaded"] += 1
        warn(book_id, row["title"], problems)
        return

    if isbn13 and old["isbn13"] and isbn13 != old["isbn13"]:
        return reject(book_id, row["title"], isbn13, "book_id already belongs to a different ISBN",
                      f"Ask the supplier which ISBN is right for book_id {book_id}: "
                      f"{old['isbn13']} (database) or {isbn13} (file).")

    # Section 4: never downgrade the ISBNs (or the title; an empty title was already rejected).
    kept = []
    for c in ("isbn10", "isbn13"):
        if record[c] is None and old[c] is not None:
            record[c] = old[c]
            kept.append(c)
    keep_note = [("kept existing isbn", "isbn + isbn13", f"{row['isbn']} | {row['isbn13']}",
                  "incoming ISBN empty or unusable; kept " + ", ".join(f"{c} {old[c]}" for c in kept))] if kept else []

    changed = {c: v for c, v in record.items() if old[c] != v}
    if changed:
        sets = ", ".join(f'"{c}" = ?' for c in changed) + ", updated_at = ?"
        db.execute(f"UPDATE books SET {sets} WHERE book_id = ?", list(changed.values()) + [now, book_id])
        report["updated"] += 1
        warn(book_id, row["title"], problems + keep_note)
    else:
        report["skipped"] += 1
        warn(book_id, row["title"], keep_note)  # settled detail 3: don't repeat old warnings


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python ingest.py <file.csv>")
    history = json.loads(LOGFILE.read_text(encoding="utf-8")) if LOGFILE.exists() else []
    report = run(sys.argv[1])
    history.append(report)
    LOGFILE.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{report['source_file']}: read {report['rows_read']}, loaded {report['loaded']}, "
          f"updated {report['updated']}, skipped {report['skipped']}, rejected {report['rejected']}, "
          f"warnings {len(report['warnings'])}, add up: {report['counts_add_up']}")


if __name__ == "__main__":
    main()
