---
name: object-label-rollout-list
description: Create a grouped Excel rollout list from an object-name Grep CSV when a Salesforce or business-system object display label is being renamed. Use for identifying affected design documents and separating required logical/display-name changes from technical identifiers, independent field/function names, history, and OOXML duplicate hits. Do not use to edit the source design documents unless the user separately requests those edits.
---

# Object Label Rollout List

Turn a Grep result into a reviewable impact list grouped by design document. Treat the Grep count as discovery evidence, not as the number of edits.

## Inputs and scope

Confirm or infer:

- the Grep CSV path;
- the old object label and new label;
- whether the change is display/logical label only or also includes physical/API names;
- the project output folder and any read-only source restrictions.

When the user says the change is display-label-only, never expand the scope to API names, DeveloperName values, formulas, relationship names, filenames, or other technical identifiers. Trim accidental leading/trailing whitespace from the supplied labels and disclose that normalization.

Read applicable `AGENTS.md` and project knowledge before classifying. Do not modify the Grep CSV or original design documents. Save the new workbook in the applicable project `output` folder.

## Workflow

1. Read [references/classification.md](references/classification.md).
2. Inspect the CSV headers and representative rows. Expected columns are `file_path`, `file_type`, `sheet_name`, `object_type`, `location`, `keyword`, `matched_text`, and `source`.
3. Identify frequent compound terms that are separate names, then run `scripts/classify_grep.py` in a temporary or working directory. Pass the old and new labels and repeat `--protect-term` for those compound terms. The script produces JSON containing deduplicated locations, first-pass classifications, document summaries, and raw type counts.
4. Review high-volume files and representative examples from every classification. Adjust obvious project-specific proper nouns or separate object/field/function names before presenting counts. Automated classification is a first-pass triage, not final approval.
5. Use the Spreadsheets skill to create one `.xlsx` workbook following [references/output-workbook.md](references/output-workbook.md). Do not use Python spreadsheet libraries for authoring.
6. Recalculate, inspect key ranges, scan formulas for errors, render the summary and document list, and visually verify them before delivery.

## Non-negotiable decisions

- Deduplicate by `file_path + sheet_name + object_type + location`; multiple snippets from the same location are one review location.
- Count `Cell`, `Formula`, `DrawingOrTextBox`, and `SheetName` as direct review evidence. Treat `SharedString`, workbook/worksheet XML, relationships, defined-name references, and similar package internals as supporting noise unless they reveal a visible construct not otherwise captured.
- Change a design description when the old term denotes the renamed object logical name, even if the text is not a screenshot.
- Do not mechanically change compound terms such as `<old label>番号`, `<old label>ID`, `<old label>管理`, another object's name, a batch/interface name, or a historical proper noun. Put these in review-required unless the user explicitly includes them.
- Formula cells showing the old label normally require changing their source cell, not overwriting the formula.
- Sheet and file names require dependency review; a display-label change alone does not authorize renaming them.
- Make the detailed list traceable to the original CSV row numbers.

## Delivery

State the required-location count, affected-document count, review-required count, and package-internal/noise count. Explain that the classifications are a first-pass list requiring owner confirmation for review-required rows.
