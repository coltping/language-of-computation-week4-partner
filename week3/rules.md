# Rules for loading books (Student B)

> Written by **Claude, playing Student B**, Colt Pingilley's Module 4 partner. No classmate was assigned. These rules were written separately from Colt's, as a second, reasonable point of view. Where a choice could go more than one way, they deliberately make a different choice from Colt's Module 3 rules, so that the comparison in Part 1 has something real to talk about.

These rules decide what happens to every row of a books CSV file when it is loaded into `books.db`.

## 1. Valid ISBNs

- **ISBN-10:** 9 digits plus a check character (0–9 or uppercase `X` for 10). The weighted sum (weights 10 down to 1) must divide evenly by 11.
- **ISBN-13:** 13 digits starting with `978` or `979`. The weighted sum (weights 1, 3, 1, 3, …) must divide evenly by 10.
- Hyphens and spaces are formatting only and are removed before checking.
- ISBNs are stored as text.
- The database keeps both forms. If a book has a 978 ISBN-13 but no ISBN-10, the ISBN-10 is **calculated** from it, so every 978 book has both. A 979 ISBN-13 has no ISBN-10.

## 2. My approach

A wrong ISBN should go back to the supplier, not into the catalogue. So:

- **Repair + warn** when the right value can be worked out with arithmetic and checked by a check digit.
- **Reject the row** when the ISBN is present but wrong and can't be worked out. The supplier fixes it and sends it again.
- **Load + warn** only when the ISBN is simply missing. A book with no ISBN is still a book.

## 3. Each kind of problem

| Problem | What happens |
|---|---|
| Leading zeros dropped from ISBN-10 | Repair (pad to 10) + warn, if the result passes the check |
| Lowercase `x` | Repair (uppercase) + warn |
| Hyphens / spaces | Repair (remove) + warn |
| Valid ISBN-13 in the ISBN-10 column | Repair (move it) + warn |
| ISBN-13 in scientific notation **with** a matching valid ISBN-10 | Repair (calculate from the ISBN-10) + warn |
| ISBN-13 in scientific notation with **no** ISBN-10, and **exactly one** ISBN-13 rounds to the shown value (12 significant digits) | Repair to that one ISBN-13 + warn. There is only one answer, so it isn't a guess. |
| ISBN-13 in scientific notation with **no** ISBN-10, and **two or more** ISBN-13s fit | Load without ISBN + warn. Nothing is wrong, the value just can't be pinned down. |
| Scientific-notation ISBN-13 that does **not** match the valid ISBN-10 | Keep the ISBN-10 and calculate the ISBN-13 from it. Ignore the rounded value + warn. The ISBN-10 is complete; the rounded value isn't. |
| ISBN-13 with `978` cut off (10 digits that fail as ISBN-10 but pass as `978` + value) | Repair to `978` + value + warn. The ISBN-13 check digit proves it. |
| Wrong check digit (ISBN-10 or ISBN-13) | **Reject** |
| Letter in the middle | **Reject** |
| Wrong length after cleaning | **Reject** |
| Too short and still fails after padding | **Reject** |
| ISBN-10 and ISBN-13 both valid but different books | **Reject.** The supplier must say which is right. |
| `isbn13` holds a non-ISBN code (UPC, prefix other than 978/979, decimal, truncated) | Ignore it + warn, and use the ISBN-10 if valid |
| Both ISBN columns empty | Load without ISBN + warn |

## 4. Same book

- **Two rows are the same book when they have the same `book_id`.** The supplier's id is the one thing that never changes in their files, and books without ISBNs still have one.
- An ISBN-13 that already belongs to a **different** book_id: **reject** the new row (e.g. *Paper Moons* using *Angels & Demons'* ISBN).

## 5. A book that arrives again

- Identical after cleaning: skip, count as *skipped – already exists*.
- Anything different: update **every** changed field, **including a different valid ISBN** (the newer file wins). Warn when the ISBN changes.
- Never overwrite a value with an empty or unusable one: keep the old value and warn. If nothing else changed, the row counts as *skipped*.
- An exact duplicate within the same file is skipped.

## 6. Other columns

- Leading and trailing spaces are removed from **every** text column (e.g. `The Kite Runner ` → `The Kite Runner`). Nothing else is changed. Years like `2011.0` stay as given.

## 7. Rejected rows (besides the ISBN cases above)

- `book_id` missing or not a whole number
- `title` empty
- Wrong number of columns

## 8. The report

For every run, newest first: when, which file, rows read / loaded / updated / skipped / rejected, whether those add up, and a list of every rejected row and every warning with line number, book_id, title, value, reason and what to do. Warnings are listed on **every** run in which they occur, including on skipped rows, so each run's report is complete on its own.

## 9. Examples

| # | Value (column) | Other column | Outcome | Stored ISBN-13 | Stored ISBN-10 |
|---|---|---|---|---|---|
| 1 | `043965548X` (isbn) | — | Valid, load | `9780439655484` | `043965548X` |
| 2 | `439023483` (isbn) | — | Repair + warn | `9780439023481` | `0439023483` |
| 3 | `031200009x` (isbn) | — | Repair + warn | `9780312000097` | `031200009X` |
| 4 | `0-450-19827-8` (isbn) | — | Repair + warn | `9780450198274` | `0450198278` |
| 5 | `9781982147600` (isbn) | isbn13 empty | Repair (moved) + warn | `9781982147600` | `1982147601` (calculated) |
| 6 | `9798351220413` (isbn13) | isbn empty | Valid, load | `9798351220413` | *(none, 979)* |
| 7 | `9.78043902348e+12` (isbn13) | isbn `439023483` | Repair from ISBN-10 + warn | `9780439023481` | `0439023483` |
| 8 | `9.78067172365e+12` (isbn13) | isbn empty | One candidate: repair + warn | `9780671723651` | `0671723650` |
| 9 | `9.7804251888e+12` (isbn13) | isbn empty | Two candidates: load without ISBN + warn | *(empty)* | *(empty)* |
| 10 | `1416913184` (isbn) | — | 978 cut off: repair + warn | `9781416913184` | `1416913181` (calculated) |
| 11 | `1854433017` (isbn) | isbn13 empty | Wrong check digit: **reject** | — | — |
| 12 | `04390A3483` (isbn) | isbn13 empty | Letter: **reject** | — | — |
| 13 | `15287463097` (isbn) | isbn13 empty | 11 digits: **reject** | — | — |
| 14 | `1555550126` (isbn) | `9781555550134` | Disagree: **reject** | — | — |
| 15 | `098870742X` (isbn) | `9.7809887074e+12` | Rounded value doesn't match: keep ISBN-10 + warn | `9780988707429` | `098870742X` |
| 16 | `1416524797` on book_id 10013 | — | Belongs to book 9: **reject** | — | — |
| 17 | empty, empty | — | Load without ISBN + warn | *(empty)* | *(empty)* |
| 18 | book 25 arrives with empty ISBNs | — | Keep old ISBNs, skip + warn | *(unchanged)* | *(unchanged)* |
