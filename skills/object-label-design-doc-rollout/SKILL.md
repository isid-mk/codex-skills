---
name: object-label-design-doc-rollout
description: Apply A-required entries from an approved object-label rollout list to copied Excel design documents. Use when A-required locations must be updated in object-named folders under the designated national-CRM design-work output folder, with only the replaced text shown in red while preserving its original font and all other wording, formatting, formulas, and workbook features. Do not use for B-source-reference entries, to generate the rollout list, or to overwrite formal source documents.
---

# Object Label Design-Document Rollout

Apply a reviewed rollout list to working copies of Excel design documents. Treat the listed source documents as read-only originals.

## Inputs and boundaries

Identify or infer:

- the rollout-list workbook;
- the formal design-document root;
- the old and new object labels;
- any user-specified document-type filter. The classification scope is fixed to `A` / `A必須対応`.

Use this fixed output root unless the user explicitly provides a newer destination in the current request:

`D:\OneDrive\OneDrive - 電通\ChatGPT\work\国民CRM\設計書作業\output`

Read applicable `AGENTS.md` and project knowledge first. If formal current documents conflict with knowledge or the rollout list, prefer the formal current documents and report the mismatch. Never edit, rename, move, or create sidecar files beside a formal source document.

This skill consumes a rollout list. Use `object-label-rollout-list` when the user needs the list created or reclassified.

## Workflow

1. Read [references/rollout-list.md](references/rollout-list.md), then inspect the rollout workbook with the Spreadsheets skill.
2. Select only `A` / `A必須対応` entries and the document types authorized by the user. Always exclude `B` / `B参照元対応` and every other classification; B-source-reference updates are outside this skill. Group the selected A locations by object name and source design document.
3. Resolve each formal source file read-only. Select from the current design tree before considering content similarity. Exclude delivery snapshots, review folders, `old`/`_old`, LOT snapshots, backups, trash, and other archives. Use package similarity only to choose between multiple current candidates; it must never make an archived copy outrank the current formal file. Verify that the listed text and location still map to the chosen version. Do not guess when multiple current candidates remain plausible.
4. Build into a fresh temporary staging folder under the design-work area. Under it, create one folder named for each object and copy each distinct source document into that folder before editing. Preserve the filename. If two different sources would collide on the same destination filename, stop and resolve the collision rather than overwriting one. Keep the existing final output untouched until every staged workbook passes validation.
5. Verify every proposed edit against the copied workbook. Use the exact sheet, cell or owning construct and current text. Never perform workbook-wide replacement.
6. Apply edits:
   - For A-required rows, replace only the occurrence that denotes the renamed object.
   - Protect API names, identifiers, independent compound terms, historical wording, formulas, filenames, sheet names, and other excluded text unless the list and user explicitly authorize them.
   - For ordinary Excel text cells, use `scripts/patch_xlsx_partial_red.py` with minimal old/new phrases. The script colors only the inserted replacement text red and preserves other rich-text runs and cell styles.
   - Match the replacement text's font to the text it replaces. Preserve the source font family, size, bold, italic, underline, strike-through, vertical alignment, and other run-level font properties; change only the replacement run's text and font color.
   - Preserve the effective font of every unchanged character in an edited cell. When converting a plain shared string to rich text, materialize the cell style's font on all runs—including unchanged runs—so Excel cannot substitute a default font. Merge any pre-existing rich-text properties over that inherited font rather than replacing them.
   - Do not apply a red font to the whole cell. Preserve pre-existing red text and all unrelated formatting.
   - Handle drawings, headers/footers, and other non-cell objects through their owning Excel construct; do not patch package-internal duplicate hits.
7. Verify each completed workbook with the Spreadsheets skill:
   - inspect all changed values and formulas;
   - confirm every new replacement run is red and unchanged runs retain their prior formatting;
   - compare each replacement run with the source text it replaced and confirm that its font family, size, emphasis, decoration, and vertical alignment are unchanged; font color is the only intended font-property difference;
   - compare the full text of every edited cell with the source and confirm that unchanged characters retain the same effective font. Do not validate only the replacement substring;
   - scan for formula errors;
   - render every changed area and visually compare it with the source;
   - compare package entries, sheet names, cell counts, merged ranges, formulas, and drawing relationships with the formal source. For cell-only edits made by the helper, only the expected worksheet XML entries should differ;
   - validate every `mc:Ignorable` token in edited OOXML. Every prefix named there must still be declared on the owning XML root. An OOXML ZIP that merely opens with a ZIP parser is not sufficient validation;
   - when desktop Excel is available, run `scripts/validate_xlsx_openable.ps1` against the complete staged object folder. It opens every workbook read-only with normal-load mode and does not save. A workbook that needs Excel repair is a failure. If native Excel is unavailable, do not claim native-open validation; report that limitation.
8. After every staged workbook passes, replace the authorized final object folder with the staged folder as one controlled swap. Only then remove the superseded working copy and temporary artifacts.
9. Deliver the copied workbooks and report completed, already-current, stale, and unresolved locations by object and document. State that the formal originals were not modified and whether native Excel validation ran.

## Safety and stopping conditions

- Preserve OOXML namespace declarations exactly enough for Excel compatibility. Never serialize an edited worksheet or drawing with a library that drops namespace declarations referenced by `mc:Ignorable`. The bundled helper uses `lxml`; do not replace it with `xml.etree.ElementTree` for workbook authoring.
- Never introduce a default font while creating rich-text runs. Materialize the cell style's effective font on every run that lacks explicit font properties, preserve existing run overrides, and then change only the replacement run's color.
- A stale cell address is not permission to search-and-replace the whole workbook. Remap it from the listed current/proposed text and nearby row context.
- If the current text no longer matches, classify the row as already applied, stale, or unresolved. Do not force the edit.
- Do not overwrite an existing working copy unless the user authorized updating that copy. Prefer a temporary output followed by an atomic replacement after verification.
- Keep temporary files inside the working area and remove them after successful verification.

## Helper usage

Create a UTF-8 JSON edit file as described in [references/rollout-list.md](references/rollout-list.md), using minimal replacement phrases, then run:

```text
python scripts/patch_xlsx_partial_red.py --input <read-only-source.xlsx> --output "D:\OneDrive\OneDrive - 電通\ChatGPT\work\国民CRM\設計書作業\output\<object name>\<copied.xlsx>" --edits <edits.json>
```

Use `--overwrite` only for an authorized working-copy replacement. The helper refuses formulas and missing or ambiguous matches so that source-reference and stale-list cases are handled deliberately.
