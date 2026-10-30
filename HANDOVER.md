# Handover — 26 Oct 2026, 01:30

## What this is

A single-page consent-form builder in Rust/Yew compiled to WebAssembly. The clinician
picks a therapy (SACT or radiotherapy), a tumour site and a regimen; the side effects are
loaded from the national consent form; they tick what was discussed, add free text, sign
on a canvas, and the app **writes those answers into the official PDF** and opens it for
printing or emailing.

Nothing leaves the browser: no backend, no API, no analytics, no storage.

## Run it

**For a restricted machine, ship the single file:**

```powershell
python tools/bundle_single_file.py     # -> dist/DPSOncconsent.html (about 2.8 MB)
```

That one file contains the HTML, CSS, JS and the wasm (base64), so it opens by
double-click from a USB stick with **no server, no install, no Python at runtime** and no
network request of any kind. Verified from `file://`: app loads, ticking, declarations,
signature, PDF download and "Open filled form" all work.

**Or serve the normal Trunk output:**

```powershell
python tools/serve_dist.py --port 8080     # serves dist/ with the right wasm MIME type
```

A server instance was left running at <http://127.0.0.1:8080> while this was written.
Stop it with `Get-Process python | Stop-Process`.

Rebuild after changes:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
cargo test
trunk build --release
```

`trunk serve` also works, but it rebuilds the dev profile and the CSP blocks its
autoreload websocket, so the static server above is the quicker loop.

## Verified in a browser (Playwright, release build)

- Landing → SACT → Breast → AC-Docetaxel loads 29 side effects in the form's own
  three headings, tally "0 of 29 ticked".
- Ticking three items updates the tally, reveals a note box per ticked row, and
  "Still blank: …" updates as fields are filled.
- The **Health professional statement** block lists the form's own declarations
  (2 on CRUK page 1, 5 on CRUK page 4, 3 on RCR), tickable, with a "3 of 7 confirmed"
  tally; each tick prints beside the matching statement.
- Rendered-pixel check of the filled PDF confirms each page gained ink: page 1 +1850
  (details and two declarations), page 2 +1510 (side-effect boxes and ticks), page 3 +324,
  page 4 +350 (declaration and notes), page 5 +952 (signature), page 6 unchanged.
- NHS number checksum and date-of-birth age hints appear as you type.
- Signature: pointer strokes register (2 SVG paths, 915 painted pixels), the Email button
  unlocks only once a stroke exists.
- **Open filled form** opens the filled PDF in a new tab (blob URL).
- **Email PDF copy** downloads `DPSOncconsent-ac-docetaxel-2026-10-26-v4.pdf` and opens
  the mail client with subject and body prefilled.
- Preview pane removed: the form opens with **Open filled form**, in a new tab. Ticks and
  declarations are drawn as ticks only — no boxes, no per-row note fields — on the text
  baseline, over the form's own bullet. Measured on the Temozolomide form: four ticks all
  at x = 60–69 pt with **0.0 pt spread**, 8 pt tall.
- The free-text box only appears for forms that actually have a free-text area on the
  paper form; the RCR forms say so explicitly instead of offering a field that goes nowhere.
- Rendered-pixel check of the filled PDF vs the original: page 1 +1530 dark pixels
  (patient details), page 2 +1638 (checkboxes and ticks), page 3 +324, page 4 +874
  (free text), page 5 +948 (signature), page 6 unchanged.

## How the filling works

| Piece | Where |
|---|---|
| Original PDFs, compiled in | `sources/pdf/*.pdf` via `include_bytes!` in `src/overlay.rs` |
| **Per-form coordinate files** | `assets/form_fields/<id>.json` — one per form, no shared rules |
| Drafter for those files | `tools/draft_form_fields.py` |
| Overlay engine | `src/overlay.rs` (lopdf content streams) |
| Open / email | `src/email.rs` |

Coordinates are deliberately per form. The tick **x belongs to a column**, not to each
item, so every tick on a page shares one gutter; the drafter checks that gutter against
every word on the page and pulls it left until nothing collides. A unit test
(`no_tick_can_reach_the_text`) then asserts, for all eight forms, that no tick's right edge
comes within 1 pt of the printed text.

The map is built by locating printed labels ("Date of birth:", "Patient's signature:")
with pdfplumber and writing on the printed rule beside them. Ticks are located by matching
the first few words of each side effect.

Two PDF quirks cost real time and are worth remembering:

1. **Pages 2–6 of every CRUK form leave an unbalanced `q` in their content stream**, so
   anything appended inherits a leftover clip and vanishes. The fix is to emit several
   `Q` operators before drawing — see `operations_for`.
2. **Resources are a mix of direct and indirect objects.** Appending a `/Fapp` entry to
   the existing dictionary works on some pages and not others; rebuilding the resources
   as owned dictionaries (`ensure_font`) works everywhere.

## Known approximations

- **CRUK page 1 is narrow.** The patient block is a right-hand column with ~60–140 pt
  cells, so values are written at 6.8–8 pt. The full name goes on the "first name(s)"
  rule; the surname cell is left blank.
- **RCR forms have no "other risks" area**, so free text is written above the signature.
- **The margin checkboxes are ours, not theirs.** Every side effect gets an 8 pt box in
  the margin; only discussed ones are ticked. CRUK and RCR print bullets, not boxes.
- **11 items in the LDR brachytherapy form get no box** (long items wrap and the
  first-four-words match fails). Everything else matched.
- **No dual-copy PDF.** The form is A4 and lays itself out; two copies are the print
  dialog's job. The old labelled "record copy / patient copy" pages were removed when the
  real form became the output.
- **Email cannot attach automatically.** `mailto:` has no attachment mechanism, so the
  PDF is saved to Downloads and the mail client opens for the clinician to attach it.

## Data and provenance

8 forms, 246 side effects, transcribed by hand from the PDFs into
`sources/content.json` and merged with URL/SHA-256/version by `tools/build_dataset.py`.

To update a form: `python tools/fetch_forms.py --force`, read `sources/clean/<id>.txt`,
edit `sources/content.json`, `python tools/build_dataset.py`,
`python tools/build_form_maps.py`, then `cargo test`.

## Not done

- Not committed to git (working agreement: no commits without asking).
- No automated test for the browser flow — the Playwright pass above was run by hand.
- The print CSS now hides the app and prints a one-line instruction, because printing the
  app would no longer produce the form.

## Update — 27 Oct 2026, late

**Chemotherapy only.** All four radiotherapy forms are out of the app: `build_dataset.py`
filters on `therapy == "sact"`, and the app skips the landing screen when one library is
present. Their PDFs, coordinate files and content stay on disk; delete the filter to
bring them back.

**Single-file delivery.** `python tools/bundle_single_file.py` writes
`dist/DPSOncconsent.html` (~2.8 MB): HTML, CSS, JS and the wasm base64-encoded, with
`connect-src 'none'`. Verified from `file://` — it opens by double-click with no server,
no install and no Python, and the PDF still downloads with the expected name.

**Ticks now sit inside the form's own checkbox.** The CRUK "checkbox" is not a vector
rectangle, it is a symbol-font glyph at the start of each line (11 pt wide at x = 48).
The drafter now anchors on that glyph and centres the tick in it:

| Form | Side effects | Ticks placed in the printed box |
|---|---|---|
| AC-Docetaxel | 29 | 29 |
| EC (Epirubicin-Cyclophosphamide) | 23 | 23 |
| Temozolomide | 30 | 30 |
| Docetaxel with Prednisolone | 27 | 27 |

Two bugs found on the way, both now fixed: rows were being grouped across the full page
width, so the last item in the left column merged with the footer ("Continue on to the next
page"); and an item's fallback match could steal a line that a later item needed, so the
exact pass now runs over every item before any fallback runs.

## Update — 30 Oct 2026 — library complete and proven

**520 forms**, served on demand. Five independent checks, all green:

| Check | Tool | Result |
|---|---|---|
| structure, wording, position | `verify_forms.py` | 520 / 520 |
| every tick sits on a printed checkbox | `verify_boxes.py` | 18 748 ticks, 520 / 520 |
| every printed checkbox is ticked | `verify_all_ticked.py` | 13 871 boxes, 520 / 520 |
| ink lands inside the box, nothing stray | `verify_renders.py` | 520 / 520 |
| word-for-word coverage | `verify_coverage.py` | 98.6 % |

`verify_all_ticked` is the mechanical form of the eye test: the proofs tick every side effect, so
any printed box left empty means a side effect the app does not know about. Run it before every
release — it is what caught a stray full stop being read as a checkbox.

**Statement extraction on the legacy forms.** Fifteen older forms print the declaration on one
line and its box on the next, and print a ✓ inside the prose ("CURATIVE ✓ to give you the best
possible chance"). Both were being read as declarations, producing four phantom rows per form.
`build_statements()` now ignores inline tick marks, attaches a box on the following line to the
sentence above it, stops at "Where the treatment will be given", and reads vector boxes as boxes
rather than dropping the first word of the line.

**Declarations were cut at the first line.** Every declaration wraps over three or four printed
lines, and only the line carrying the checkbox was being captured, so the app showed
"I have discussed the intended benefit and risks" and stopped. A declaration is now taken as the
block of lines that runs from its box to the next box, staying in the same column — the words
are complete, and the number of declarations per form is unchanged.

**Upload.** `site/consent.html` plus the whole `site/consent/` folder (77 MB, 520 bundles and
520 PDFs). Nothing else changes on the server.


**All CRUK SACT forms imported.** 517 bundles + PDFs (about 75 MB) served on demand from
`consent/forms/<id>.{json,pdf}`; nothing is embedded in the wasm.

**Keyword search.** A `Search` panel under the regimen picker matches drug names, regimen
names and tumour sites. Every result is labelled `filed under <site>` and clicking one sets
both the tumour-site and regimen selectors, so a search jumps straight to the form.

**Three extraction bugs, all found by the verifier rather than by eye:**

1. **Two-letter words were being deleted.** The printed checkbox extracts as the letter `c`,
   so the drafter treated *any* word of two characters or fewer at the start of a line as a
   tick box and dropped it. "of", "to", "by", "in", "or", "if" vanished from the side-effect
   text — 500+ losses in the first 40 forms. The test now requires the token to contain no
   letter or digit once the `c` is removed.
2. **Wrapped lines became phantom side effects.** A continuation line starting with a glyph
   ("nurse.", "temporary.)") was promoted to its own entry; it now folds into the previous
   side effect.
3. **A section could swallow the document.** One form produced 380 items from a lost heading;
   sections now cap at 60 entries and stop at the next heading.

**The importer resumes.** `import_all.py` skips any bundle already on disk unless `--force`
is passed, so a fix to the drafter silently applies to *new* forms only. After changing
`draft_form_fields.py`, delete `forms/*.json` (the PDF cache under `forms/*.pdf` and
`sources/forms/` is kept) before re-running, or the new code never touches old bundles.

**Verification harness** — four independent checks, because each catches a different fault:
| Check | Tool | What it proves |
|---|---|---|
| A structure | `tools/verify_forms.py` | groups, one tick per side effect, indexes, statements |
| B fidelity | `tools/verify_forms.py` | every item is verbatim in the PDF; every printed bullet is in the bundle; no duplicates; no mangled characters |
| C position | `tools/verify_forms.py` | each tick lies on the row whose wording is that side effect's |
| D render | `tools/verify_renders.py` | the ink actually lands inside the printed box (pixel proof per tick) |
| E box exists | `tools/verify_boxes.py` | a checkbox is really printed at that exact coordinate — a tick on blank paper fails |
| F human eyes | `tools/contact_sheets.py` | every form's side-effect page on a contact sheet, for review by a person |

**Bullet characters.** A bullet that marks a sub-item inside a wrapped line extracts as "•"
and used to land mid-sentence: "unwell (even with a • normal temperature)". `clean_text()`
in `import_all.py` now drops it, and `tools/clean_bundles.py` repairs bundles written before
that fix without re-parsing the PDFs.

**Two-column pages and the verifier.** The position check compared a tick against the
nearest row on the page, which on a two-column page can be the *other* column's row at
almost the same height — a correct tick was reported as being on the wrong line. The
comparison is now restricted to the tick's own column.

**Vector checkboxes.** A handful of older forms draw the tick box as a small square instead
of using the symbol font (Bexarotene, Interferon alfa-2a). Rows without a glyph now take the
nearest small square to their left, level with the wording. `page_rows()` is the single
source of truth: `import_all.py`, `draft_form_fields.py` and `verify_forms.py` all call it.

**Print a blank form.** A checkbox on the landing screen (and again in the print panel)
prints the form with nothing drawn on it — `document::build_blank_with_patient_copy()` returns
the original bytes untouched and stamps the second copy. Two unit tests hold it: the blank
print must equal the original byte for byte, and must still produce two copies.

**Keyword search.** A `Search` panel under the regimen picker matches drug names, regimen
names and tumour sites; every result is labelled `filed under <site>` and opening one sets
both selectors.

**Library: 519 forms.** Four regimens that the first import dropped are back — Bexarotene,
Interferon alfa-2a, Ipilimumab and Ipilimumab-Nivolumab — after two further template
discoveries: some older forms draw the tick box as a *vector square* rather than a symbol
glyph, and the immunotherapy forms list side effects under a single lead-in ("You may have
one or more of the side effects listed") instead of the usual three headings. Two documents
remain out on purpose: `open-to-read-faqs-in-this-document` is a FAQ page, not a consent
form, and `children-and-young-people-all-in-...` is an index of children's forms rather than
a single regimen.

**Targeted re-import.** `python tools/import_all.py --only <id fragment>` re-imports just the
matching forms and merges them into the existing catalogue, so a single fix no longer costs a
90-minute full pass.

**The bug only the eye found (30 Oct).** Looking at rendered pages — not just the pixel diff —
showed side effects missing from the right-hand column of two-column forms. Rows are read
column by column, so the left column's footer ("To be retained in patient notes", "Checked by
…") arrived *before* the right column's text; it was treated as the end of the section and
everything printed to its right was dropped, silently. Every automated check shared that blind
spot, because they all walked the same row order. Rows in the bottom 95 pt of a page are now
ignored as page furniture, in both the importer and the verifier. Only a human — or a vision
pass over rendered pages — catches a fault that the model of the document itself gets wrong.


