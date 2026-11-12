# Rules for loading books (agreed)

**Agreed by:** Student A, Colt Pingilley, and Student B, Claude, playing partner because no classmate was assigned. Both partners use this exact file.

**How we agreed:** We compared our two Module 3 rule sets decision by decision. The comparison is in this file's git history, as `rules-comparison.md`. There were 40 decisions: 19 agreed, 16 disagreed, and 5 were covered only by Student A. Colt settled every disagreement, and in each case chose Student A's rule. The decisions only Student A's rules covered were kept as written. The examples Student B used to show its different choices were added to the table in section 7, with the agreed outcomes.

These rules decide what happens to every row of a books CSV file when it is loaded into `books.db`. The kinds of problem they refer to are described in Module 3's `data-validation.md`.

## 1. What counts as a valid ISBN

- **ISBN-10:** exactly 10 characters. The first 9 are digits, and the last is a digit or an uppercase `X`. The check digit must be correct: weight the characters 10, 9, … 1 (`X` = 10), and the total must divide evenly by 11.
- **ISBN-13:** exactly 13 digits, starting with `978` or `979`. The check digit must be correct: weight the digits 1, 3, 1, 3, …, and the total must divide evenly by 10.
- Hyphens and spaces are not part of an ISBN.
- The database stores ISBNs as **text**, never as numbers, so leading zeros and `X` survive.
- Every book gets an **ISBN-13** when one can be found for certain. An ISBN-10 is converted to its ISBN-13 by putting `978` in front of its first 9 digits and recomputing the check digit. A 979 ISBN-13 has no ISBN-10, and that is not an error.

## 2. What happens to each kind of problem

There are three possible outcomes for a value:

- **Repair + warn.** The fix is certain because the check digit confirms it. Load the repaired value and log a warning showing the original value.
- **Load without that ISBN + warn.** Any fix would be a guess. Load the book, leave that ISBN empty, and log a warning showing the bad value, so a person can look it up. A wrong ISBN in the database is worse than an empty one, because it would make two different books look like the same book.
- **Reject.** The row is not loaded at all, and the reason goes in the log. This applies only to the cases in section 4.

| Problem | Outcome | Why |
|---|---|---|
| Leading zeros dropped from ISBN-10 (8 or 9 digits, or 7 or fewer) | Repair: add zeros on the left to make 10, **only if** the result passes the check digit | The check digit proves the repair is right |
| Lowercase `x` at the end | Repair: make it uppercase, only if the result passes | Same |
| Hyphens or spaces, inside or around the value | Repair: remove them, only if the result passes | Same; hyphens and spaces carry no meaning |
| A valid ISBN-13 in the ISBN-10 column | Repair: use it as the ISBN-13 | It passes the ISBN-13 check; it's just in the wrong column |
| ISBN-13 in scientific notation (e.g. `9.78043902348e+12`) **with** a valid ISBN-10 that matches it | Repair: build the ISBN-13 from the ISBN-10 | The ISBN-10 has every digit; the rounded value only confirms it |
| ISBN-13 in scientific notation **without** a valid ISBN-10 | Load without ISBN-13 + warn | The check digit is gone and the 12th digit may be rounded, so any rebuild is a guess. This includes the 55 rows where only one answer fits the rounding. Rebuilding those depends on assuming *how* the supplier rounded. |
| ISBN-13 with `978` cut off (10 digits that fail the ISBN-10 check but pass as `978` + value) | Load without ISBN + warn | It is very likely the right ISBN, but it is still an inference |
| Wrong check digit (ISBN-10 or ISBN-13) | Load without that ISBN + warn | At least one digit is wrong, and nothing says which |
| Letter in the middle (e.g. `04390A3483`) | Load without ISBN + warn | The obvious "fix" turns it into another book's ISBN |
| Wrong length after cleaning (e.g. 11 digits) | Load without ISBN + warn | The obvious "fix" turns it into another book's ISBN |
| Too short **and** fails the check after adding zeros | Load without ISBN + warn | Padding doesn't make it valid, so some digit is wrong |
| ISBN-10 and ISBN-13 are both valid but **disagree** (they aren't twins) | Load with **neither** ISBN + warn | They can't both belong to this book, and we can't tell which is right |
| `isbn13` holds something that is not an ISBN-13 at all: a UPC barcode, prefix other than 978/979, a truncated value, or a decimal like `195170342.0` | Ignore that value + warn. Still use a valid ISBN-10 from the same row. | It's a different kind of code, not a wrong ISBN, so it shouldn't cancel a good ISBN-10 |
| Both ISBN columns empty | Load without ISBN + warn | Many real books in the file have no ISBN; they are still books |

**When is a repair really a guess?** When more than one ISBN could be the "real" one, or when nothing (no check digit, no second column) confirms the fix. A repair is only certain when the repaired value passes its check digit **and** does not contradict the other ISBN column.

## 3. What makes two rows the same book

- **Two rows are the same book when they have the same ISBN-13** after the repairs in section 2.
- Rounded scientific-notation text is **never** compared as written. 262 different books share rounded values.
- **A book with no usable ISBN** is matched by its supplier `book_id` instead. Both deliveries come from the same supplier and use the same ids.
- **Conflicts:**
  - Same ISBN-13 as a book already in the database, but a **different book_id**, e.g. *Paper Moons* (10013) using *Angels & Demons'* ISBN. The ISBN can't belong to both, so load the new row **without** the ISBN and warn, naming the book that already has it.
  - Same book_id as a book in the database, but a **different valid ISBN-13**. Reject the row, with the reason "book_id already belongs to a different ISBN". A person has to decide which is right.
- **The same book twice in one file** (e.g. 10001): the first copy is loaded, and the second is treated like any book that "arrives again" (section 4).

## 4. When a book that is already in the database arrives again

- **Nothing changed:** skip the row and count it as *skipped – already exists*. Running the same file twice therefore loads nothing new the second time.
- **Something changed** (e.g. rating counts went up, or an ISBN that was broken is now valid): update the changed fields and count the row as *updated*.
- **Never downgrade an ISBN:** if the database already has a valid ISBN and the new row's ISBN is empty or unusable, keep the old ISBN, update the other changed fields, and warn. Example: *Harry Potter and the Deathly Hallows* (25) arrives in batch 2 with no ISBNs.
- **Never downgrade the title either:** an empty title never overwrites an existing title. That can't actually happen, because a row with an empty title is rejected. Only the ISBNs and the title are protected this way. Every other column takes the new value, even if it is empty.

**Rows that are rejected** (the only cases where a book is not loaded):

1. `book_id` is missing or not a whole number.
2. `title` is empty.
3. The book_id conflict in section 3.
4. The line can't be read as a row of the CSV, e.g. the wrong number of columns.

## 5. What the report must tell the person reading it the next morning

For each run, newest first:

1. **When** it ran and **which file**.
2. **The counts:** rows read, loaded (new), updated, skipped (already exist), rejected, and how many of the loaded or updated rows carry warnings.
3. **Did everything add up?** read = loaded + updated + skipped + rejected. If not, say so in red.
4. **A one-line verdict:**
   - "All rows accounted for, nothing rejected."
   - "N rows rejected: action needed."
   - "N rows loaded with warnings: review."
5. **Every rejected row:** line number, book_id, title, the value that caused it, the reason, and what to do. For example: *"Ask the supplier which ISBN is correct for book_id 10011."*
6. **Every row loaded with a warning:** line number, book_id, title, the original ISBN value, what the rules did (repaired → new value, or loaded without ISBN), and the reason.

## 6. Settled details

1. **Which columns `books.db` keeps:** all columns from the CSV. The `isbn` and `isbn13` columns are replaced by the cleaned `isbn10` and `isbn13`. "Something changed" means any stored column is different, so rating counts going up counts as a change.
2. **A valid ISBN-10, but a scientific-notation `isbn13` (978/979 prefix) that doesn't match it:** load with **neither** ISBN, and warn. It is treated like "both valid but disagree".
3. **A skipped row (already exists, unchanged) that also has an ISBN problem:** don't log the ISBN warning again. It was logged when the row was first loaded. The row is only counted as skipped.
4. **A known book whose only difference is a worse ISBN** (e.g. book 25 with empty ISBNs): count it as **skipped**, with a warning that the incoming ISBN was ignored and the existing one kept.
5. **The ISBN-10 column in the database** holds the cleaned ISBN-10 from the file's `isbn` column, and **only if the file gave one**. It is never calculated from an ISBN-13.
6. **Non-ISBN columns** (title, year, authors, ratings…) are stored **exactly as given**. No trimming and no number conversion. Only the ISBN rules change anything.
7. **Line numbers** in the log and report are the file's line numbers as a text editor shows them. The header is line 1.
8. **"When it ran"** is recorded in local time with the UTC offset, e.g. `2026-11-04T21:30:05-06:00`.
9. **One ISBN column valid, the other broken** (wrong check digit, wrong length, bad characters): keep the valid one, and warn about the broken one. If the kept one is an ISBN-10, the ISBN-13 is calculated from it. A broken value is not a "disagreement"; disagreement needs two valid values. A value that is not an ISBN at all is handled by the "not an ISBN-13" row in section 2.
10. **Skipped rows in the log:** only counted, not listed one by one. Every **rejected** row and every **warning** is listed individually.
11. **Where the files go:** `books.db` and `ingestion-log.json` are always created next to `ingest.py`, whichever folder the terminal is in.
12. **When a scientific-notation `isbn13` "matches" an ISBN-10:** the ISBN-13 calculated from the ISBN-10, rounded to **12 significant digits**, must equal the file's value. The supplier always kept 12 digits and dropped trailing zeros, so a value that shows fewer digits means the missing digits were zeros. Example: book 5998, `098870742X` with `9.7809887074e+12`, does **not** match, so it is loaded with neither ISBN and a warning.

## 7. Examples

| # | Column | Value | Other column | What the rules say | Stored ISBN-13 |
|---|---|---|---|---|---|
| 1 | isbn | `043965548X` | — | Valid ISBN-10. Load. | `9780439655484` |
| 2 | isbn | `439023483` | — | Leading zero dropped. Repair to `0439023483` + warn. | `9780439023481` |
| 3 | isbn | `61120081` | — | Two zeros dropped. Repair to `0061120081` + warn. | `9780061120084` |
| 4 | isbn | `031200009x` | — | Lowercase x. Repair to `031200009X` + warn. | `9780312000097` |
| 5 | isbn | `0-450-19827-8` | — | Hyphens. Repair to `0450198278` + warn. | `9780450198274` |
| 6 | isbn | `␣162 001 4750␣` | — | Spaces. Repair to `1620014750` + warn. | `9781620014752` |
| 7 | isbn | `9781982147600` | isbn13 empty | Valid ISBN-13 in the wrong column. Move it + warn. ISBN-10 stays empty. | `9781982147600` |
| 8 | isbn13 | `9798351220413` | isbn empty | Valid 979 ISBN-13. Load; no ISBN-10 is expected. | `9798351220413` |
| 9 | isbn13 | `9.78043902348e+12` | isbn `439023483` | Scientific notation. Rebuild from the repaired ISBN-10 + warn. | `9780439023481` |
| 10 | isbn13 | `9.7804251888e+12` | isbn empty | Scientific notation, no ISBN-10 (two ISBN-13s fit). Load without ISBN + warn. | *(empty)* |
| 11 | isbn | `1854433017` | isbn13 empty | Wrong check digit. Load without ISBN + warn. | *(empty)* |
| 12 | isbn | `04390A3483` | isbn13 empty | Letter in the middle. Load without ISBN + warn. | *(empty)* |
| 13 | isbn | `15287463097` | isbn13 empty | 11 digits. Load without ISBN + warn. | *(empty)* |
| 14 | isbn + isbn13 | `1555550126` | `9781555550134` | Both valid but they disagree. Load with neither + warn. | *(empty)* |
| 15 | isbn | `1416913184` | — | ISBN-13 with 978 cut off. Load without ISBN + warn. | *(empty)* |
| 16 | isbn13 | `76783609419.0` | isbn `553609416` | Not an ISBN-13 (UPC barcode). Ignore it + warn; use the repaired ISBN-10. | `9780553609417` |
| 17 | both | empty, empty | — | No ISBN. Load + warn, matched by book_id. | *(empty)* |
| 18 | isbn | `1416524797` on book_id 10013 | — | Valid, but it already belongs to book_id 9. Load without ISBN + warn. | *(empty)* |
| 19 | isbn | `0306406152` (made up) | — | Valid ISBN-10. Load. | `9780306406157` |
| 20 | isbn13 | `9780306406158` (made up) | isbn empty | Wrong check digit. Load without ISBN + warn. | *(empty)* |
| 21 | — | book 25, both ISBNs empty in batch 2 | — | Already in the database with a valid ISBN. Keep the old ISBN; skip + warn. | *(unchanged)* |
| 22 | — | book 106, identical in both files | — | Already exists, nothing changed. Skip. | *(unchanged)* |
| 23 | isbn13 | `9.78067172365e+12` | isbn empty | Scientific notation, no ISBN-10; only one ISBN-13 fits, but it is still not rebuilt. Load without ISBN + warn. *(From Student B's examples.)* | *(empty)* |
| 24 | isbn + isbn13 | `098870742X` | `9.7809887074e+12` | Valid ISBN-10, but the rounded ISBN-13 doesn't match it at 12 digits. Load with neither + warn. *(From Student B's examples.)* | *(empty)* |
