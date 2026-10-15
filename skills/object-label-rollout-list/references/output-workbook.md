# Output workbook

Create one focused workbook with these sheets.

## 1. Summary

Show:

- old label, new label, and scope;
- required locations and affected documents;
- source-reference, review-required, and excluded counts;
- raw Grep rows, source files, direct-hit rows, deduplicated locations, and package/internal rows;
- a short warning that review-required rows need owner confirmation.

## 2. Documents

One row per design document, grouped/sortable by design phase and document type. Include priority, design phase and document type, document filename, counts for A/B/C/D, total direct locations, main affected sheets, concise action, and source-relative path.

Assign high priority to canonical object-model documents and high-volume required changes. Keep review-only documents visible after required-change documents.

## 3. Locations

One row per deduplicated direct location. Include classification, design phase, document type, filename, sheet, object type, cell/location, current text, proposed edit/action, reason, relative path, original CSV row numbers, and a note for drawings, formulas, or structural names.

Use filters, frozen header rows, and frozen identifying columns. Color classifications consistently but keep the body restrained.

## 4. Rules

Summarize A–E definitions and operational rules. State that global string replacement is prohibited for display-label-only changes.

## Formatting and verification

- Put Summary first and the detailed evidence after Documents.
- Use one readable font, dark headers, restrained status colors, and no worksheet gridlines.
- Avoid excessive row heights; long text can remain unwrapped in the detailed view so filtering stays usable.
- Scan formula errors only in authored calculation/display areas so source snippets containing strings such as `#REF!` do not create false alarms.
- Render and inspect Summary and the first page of Documents.

