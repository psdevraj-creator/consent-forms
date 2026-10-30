# UX notes

## Primary task

Pick a regimen, tick the side effects that were actually explained, sign, print the record
and patient copies.

## Friction found

- A wizard adds clicks between "which form" and "show the patient the list"; the whole task
  fits on one screen, so a stepper would only slow it down.
- Side-effect lists run to 49 items; a flat list buries the headings the forms use.
- The printed output must be exactly what the clinician just reviewed, so a preview that is
  built separately from the print DOM would drift.
- On a 13-inch laptop the side-by-side preview squeezes the tick list, which is the part
  being read out loud.

## Changes made

- One screen, three blocks: Treatment, Side effects discussed, Patient and signature.
- Side effects grouped under the form's own headings, with the frequency band kept in the
  heading rather than bolted onto every row.
- Notes only appear on rows that are ticked, so the default view stays scannable.
- Print copies and the preview are the same DOM; `@media print` hides the working screen.
- Below 1180 px the preview becomes a full-screen drawer behind a Preview button instead of
  stacking under the form.

## Validation

Visual check only. Not yet observed in a real consultation.

## Next usability test

Ask a clinician to take consent for a regimen they do not usually use, and watch where they
stop: at the site dropdown, at the side-effect list, or at the signature.
