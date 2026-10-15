# Classification rules

Use these codes for a display/logical-label-only change.

## A — Required change

The old term denotes the renamed object itself.

Strong evidence includes:

- exact logical-name cells;
- `<old label>レコード` or `<old label>オブジェクト`;
- record/object descriptions such as `<old label>を取得`, `<old label>に紐づく`, or `<old label>から更新`;
- object boxes in diagrams, object-list logical-name columns, ER diagrams, permission matrices, or logical object columns in mappings;
- qualified presentations that are clearly the object label plus a record/business type.

Replace only the occurrence that denotes the target object. Protect unrelated compound terms in the same cell.

## B — Source-reference change

The match is a formula cell whose cached/displayed value contains the old label. Keep the formula and locate the source cell. Confirm that updating the source changes all dependent displays.

## C — Review required

The occurrence may be an independently configured label or structural name, including:

- `<old label>番号`, `<old label>ID`, `<old label>名`, `<old label>区分`, or `<old label>状態`;
- `<old label>管理`, `<old label>一覧`, process names, batch names, interface names, and migration-tool names;
- another object name containing the old string;
- record type names when it is unclear whether the object label is embedded or the whole phrase is separately configured;
- sheet names, filenames, defined display names, or generated phonetic/helper labels;
- ordinary business prose where the referent cannot be established from the snippet.

Only change these when the actual Salesforce/configuration label or approved naming scope includes them.

## D — Do not change

- version histories, review histories, and quotations that must preserve the wording at that time;
- proper names of legacy systems or source documents;
- API names, DeveloperName values, physical fields, relationship names, formulas, external-link paths, and identifiers;
- unrelated business uses of the same word.

## E — Package/internal duplicate

Shared strings and OOXML package parts frequently repeat cell text, sheet names, print areas, headers, external links, or workbook metadata. Do not edit these entries directly. Edit the visible cell, drawing, header/footer, or other owning Excel construct if it is genuinely in scope.

## Review technique

Check at least:

- the highest-volume documents;
- one example from every `object_type`;
- object lists, ER diagrams, object designs, permission designs, screen designs, flows, batches, interfaces, and migration documents when present;
- the most frequent compound terms containing the old label.

If a snippet contains both the target-object reference and an independent compound term, classify the location as required but make the proposed edit explicit about which occurrence changes.

