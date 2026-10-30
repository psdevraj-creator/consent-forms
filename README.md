# Consent form builder

A browser tool that fills in Cancer Research UK's national SACT consent forms. The clinician
picks a regimen, ticks the side effects and declarations they discussed, and prints two
copies — one for the notes, one stamped **PATIENT COPY** for the patient.

The wording is never retyped. Every form is the official CRUK PDF, and the ticks are drawn
into that PDF at the coordinates of its own printed checkboxes.

**Live:** https://www.dpsoncology.com/consent.html

---

## The privacy rule

No patient details are collected, typed, stored or sent. Name, date of birth, NHS number and
signature are deliberately left blank and written by hand after printing.

Everything happens in the browser: the form data and PDF are fetched when a regimen is
chosen, the ticks are drawn in WebAssembly, and the result is handed to the browser's PDF
viewer. There is no server-side component, no analytics, no cookies and no storage.

That is why the app can be used on a hospital PC without an information-governance question
about where patient data goes: **no patient data ever enters it**.

---

## How it works

```
data/catalogue.json  (520 regimens: id, site, name, counts)
        │
        │  compiled into the wasm
        ▼
   Yew app ──fetch──► consent/forms/<id>.json   wording + tick coordinates
        │            consent/forms/<id>.pdf    the CRUK form itself
        │
        └── lopdf ──► ticks drawn into the PDF ──► browser viewer ──► print
```

- `src/app.rs` — the screen: picker, search, side effects, declarations, print.
- `src/overlay.rs` — draws ticks and free text into the PDF, and duplicates the document for
  the patient copy.
- `src/document.rs` — assembles the single copy and the two-copy print.
- `src/loader.rs` — fetches a form's JSON and PDF on demand.
- `assets/catalogue.json` — the 520-regimen index (embedded at build time).

Forms are served one at a time rather than embedded, so the page stays small while the
library is complete.

---

## Repository layout

| Path | What it is |
|---|---|
| `src/` | the Rust/Yew application |
| `styles.css` | styling, matched to dpsoncology.com |
| `tools/` | the import pipeline and the verification harness |
| `assets/catalogue.json` | the regimen index embedded in the wasm |
| `homepage/index.html` | the site homepage, with the "More tools" modal |
| `docs/`, `HANDOVER.md` | decisions, quirks and history |

**Not in the repository**, because it is generated or is Cancer Research UK's copyright:

| Excluded | Why | How to get it |
|---|---|---|
| `forms/` | 520 CRUK PDFs + their tick coordinates | `python tools/import_all.py` |
| `sources/` | download cache of the same PDFs | same |
| `site/` | build output | `trunk build --release` |

A fresh clone builds, but has no forms until the importer has run.

---

## Quick start

```bash
# 1. build the app
cargo install trunk            # once
trunk build --release

# 2. download and process the library (about 90 minutes, network required)
python -m pip install pdfplumber pypdfium2 pymupdf numpy pypdf
python tools/import_all.py

# 3. prove it
python tools/verify_forms.py       # structure, wording, position
python tools/verify_boxes.py       # every tick sits on a printed checkbox
python tools/verify_all_ticked.py  # every printed checkbox is ticked
cargo test write_all_proofs -- --ignored
python tools/verify_renders.py     # ink inside the box, nothing stray
python tools/verify_coverage.py    # nothing printed is missing

# 4. package for the web server
python tools/package_site.py
python tools/serve_site.py --port 8080    # then open /consent.html
```

---

## The import pipeline

| Tool | Does |
|---|---|
| `tools/fetch_forms.py` | downloads the CRUK index and every linked PDF |
| `tools/import_all.py` | extracts headings, side effects and declarations; drafts tick coordinates; writes a bundle per form |
| `tools/draft_form_fields.py` | the row reader and coordinate drafter shared by everything else |
| `tools/fix_sites.py` | maps form titles to tumour sites |
| `tools/check_updates.py` | compares the published library with ours — new, revised, withdrawn |

Re-running after a change to the drafter needs `--force`, or existing bundles are skipped:

```bash
python tools/import_all.py --force
python tools/import_all.py --only skin-chop-21      # just one form
```

`--only` merges into the existing catalogue instead of replacing it.

---

## Verification

Five independent checks, because each catches a different kind of error.

| Check | Tool | Proves |
|---|---|---|
| A structure | `verify_forms.py` | groups, one tick per side effect, indexes, declarations |
| B fidelity | `verify_forms.py` | every item is verbatim in the PDF; every printed bullet is in the bundle; no duplicates; no mangled characters |
| C position | `verify_forms.py` | each tick is centred on the printed box of the row carrying that wording |
| D render | `verify_renders.py` | the ink really lands inside the box, and nothing is drawn elsewhere |
| E box exists | `verify_boxes.py` | a checkbox is printed at that exact coordinate — a tick on blank paper fails |
| F box ticked | `verify_all_ticked.py` | every checkbox the form prints receives a tick |
| G coverage | `verify_coverage.py` | no printed words are missing from the app |

`verify_second_engine.py` renders the same pages with MuPDF as well as PDFium, so a PDF that
only one engine can draw is caught before it reaches paper.

Current state: **520 forms, all checks green**, 18 600+ ticks.

---

## Deployment

Upload two things to the site root:

| Local | Server |
|---|---|
| `site/consent.html` | `/consent.html` |
| `site/consent/` (whole folder, about 77 MB) | `/consent/` |

`consent/` holds the hashed JS/WASM/CSS, the two fonts, and `forms/` with 520 bundles and 520
PDFs. Delete the previous hashed files after uploading; purge the CDN cache for the HTML.

The page footer shows the build id. If two machines disagree about behaviour, compare that
line first: a stale cached `consent.html` is the usual cause.

---

## Known exclusions

| Document | Why it is not in the app |
|---|---|
| `open-to-read-faqs-in-this-document` | a FAQ page, not a consent form |
| `children-and-young-people-all-in-children-and-young-people` | an index of children's forms, not a single regimen |
| `haematology-aml-aida-...` | a 143-page booklet rather than a one-regimen form |
| Welsh, bilingual and Bengali interlinear versions | deliberately skipped; the English forms are the source |

Nineteen forms score below 90 % on word coverage. Each is an immunotherapy form whose
"Other information" paragraphs are prose, not tickable items; every printed checkbox on them
is still ticked (check F).

---

## Provenance

The consent forms are © Cancer Research UK, published for use in the NHS at
cruk.org/sact_consent. This repository contains no CRUK PDFs and no extracted form text; it
provides the tooling that fetches and fills them.

Not affiliated with or endorsed by Cancer Research UK.
