import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const defaultTemplate = path.resolve(scriptDir, "../assets/review_template.xlsx");

function argument(name, fallback = undefined) {
  const index = process.argv.indexOf(name);
  return index >= 0 && index + 1 < process.argv.length ? process.argv[index + 1] : fallback;
}

const mode = argument("--mode", "review");
const outputPath = argument("--output");
if (!outputPath) throw new Error("--output is required");

const fontName = "Yu Gothic";
const navy = "#243B53";
const blue = "#356C95";
const lightBlue = "#EAF2F8";
const pale = "#F5F7FA";
const border = "#CCD6E0";

function styleTitle(sheet, range) {
  const title = sheet.getRange(range);
  title.format.font = { name: fontName, size: 16, bold: true, color: navy };
  title.format.rowHeight = 28;
}

function styleHeader(range) {
  range.format = {
    fill: navy,
    font: { name: fontName, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    rowHeight: 36,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
}

function baseSheet(sheet, tabColor = navy) {
  sheet.showGridLines = false;
  sheet.tabColor = tabColor;
}

const categoryColors = {
  "不備": ["#FDE8E7", "#9B1C1C"],
  "リスク": ["#FFF4CC", "#7A5200"],
  "要確認": ["#EAF2F8", "#356C95"],
};
const severityColors = {
  "重大": ["#F8D7DA", "#8A1C1C"],
  "高": ["#FCE8D5", "#9A4A00"],
  "中": ["#FFF4CC", "#7A5200"],
  "低": ["#EAF2F8", "#356C95"],
  "情報": ["#F5F7FA", "#4B5563"],
};
const stateColors = {
  "不一致": categoryColors["不備"], "未実装": categoryColors["不備"],
  "確認不能": categoryColors["リスク"], "未確認": categoryColors["リスク"],
  "一部確認": categoryColors["リスク"],
};

// Direct RGB styles keep the review snapshot legible even if an Excel viewer
// does not apply exported conditional formatting. Rules handle later value edits.
function colorStatuses(sheet, column, firstRow, values, palette) {
  const end = Math.max(firstRow, firstRow + values.length - 1);
  const range = sheet.getRange(`${column}${firstRow}:${column}${end}`);
  range.conditionalFormats.deleteAll();
  for (const [value, [fill, color]] of Object.entries(palette)) {
    range.conditionalFormats.addCustom(`${column}${firstRow}="${value}"`, {
      fill, font: { color, bold: true },
    });
  }
  values.forEach((value, index) => {
    const cell = sheet.getRange(`${column}${firstRow + index}`);
    const [fill, color] = palette[value] ?? ["#FFFFFF", "#202B38"];
    cell.format.fill = fill;
    cell.format.font = { name: fontName, size: 10, color, bold: Boolean(palette[value]) };
  });
}

function simpleSheet(workbook) {
  let sheet = workbook.worksheets.items.find((item) => item.name === "簡易指摘一覧");
  if (!sheet) sheet = workbook.worksheets.add("簡易指摘一覧");
  baseSheet(sheet, blue);
  sheet.getRange("A2").values = [["簡易指摘一覧"]];
  styleTitle(sheet, "A2:F2");
  sheet.getRange("A3:F3").unmerge();
  sheet.getRange("A3:F3").merge();
  sheet.getRange("A3").values = [["対象欄の指摘IDは詳細シートと共通。優先度は詳細の重大度に対応する。"]];
  sheet.getRange("A3:F3").format = { font: { name: fontName, size: 10, color: "#4B5563" }, wrapText: true, rowHeight: 30 };
  sheet.getRange("A5:F5").values = [["区分", "優先度", "対象", "レビュー内容", "確認根拠", "対応案"]];
  styleHeader(sheet.getRange("A5:F5"));
  [12,10,40,48,56,48].forEach((width, i) => sheet.getRangeByIndexes(4, i, 2, 1).format.columnWidth = width);
  sheet.freezePanes.freezeRows(5);
  sheet.freezePanes.freezeColumns(2);
  return sheet;
}

function populateSimple(workbook, data) {
  const findings = data.findings ?? [];
  const supplied = data.simpleFindings;
  const shortFile = (value) => String(value ?? "").split(/[\\/]/).pop();
  const evidence = (row) => [
    row[14],
    [shortFile(row[10]),row[11],row[12]].filter(Boolean).join(" / "),
    [shortFile(row[8]),row[9]].filter(Boolean).join(" / "),
  ].filter(Boolean).join("\n");
  // ID is input metadata, not an extra worksheet column. Legacy four-field
  // inputs retain their target text; the separated content comes from detail.
  const entries = supplied?.length ? supplied.map((row,i) => {
    if (Array.isArray(row) && row.length === 4) {
      const detail=findings[i] ?? [];
      return [row[0],row[1],detail[2],row[2],detail[13],evidence(detail),detail[16]];
    }
    return row;
  }) : findings.map((row) => [
    row[0],row[3],row[2],
    [row[7],shortFile(row[8]),row[9]].filter(Boolean).join("\n"),
    row[13],evidence(row),row[16],
  ]);
  if (entries.length !== findings.length) throw new Error("簡易指摘一覧: detail count mismatch");
  const ids = new Set();
  entries.forEach((row, i) => {
    if (!Array.isArray(row) || row.length !== 7 || row[0] !== findings[i][0] || row[1] !== findings[i][3] || row[2] !== findings[i][2]) {
      throw new Error(`簡易指摘一覧: ID/category/priority/order mismatch at row ${i + 1}`);
    }
    if (ids.has(row[0])) throw new Error(`簡易指摘一覧: duplicate ID ${row[0]}`);
    ids.add(row[0]);
  });
  const rows = entries.map(([id,category,priority,target,content,basis,action]) => [
    category,priority,`[${id}]\n${target ?? ""}`,content,basis,action,
  ]);
  const sheet = simpleSheet(workbook);
  for (const table of [...sheet.tables.items]) table.delete();
  sheet.getRange("A6:F505").clear({ applyTo: "all" });
  const normalized = rows.length ? rows : [Array(6).fill(null)];
  sheet.getRange("A6").write(normalized);
  sheet.getRangeByIndexes(5, 0, normalized.length, 6).format = {
    font: { name: fontName, size: 10, color: "#202B38" },
    fill: "#FFFFFF", wrapText: true, verticalAlignment: "top",
  };
  normalized.forEach((row, i) => {
    const lines = row.map((value, c) => String(value ?? "").split("\n").reduce((count, line) => {
      const length = [...line].reduce((sum, ch) => sum + (ch.charCodeAt(0) > 255 ? 1 : 0.6), 0);
      return count + Math.max(1, Math.ceil(length / ([12,10,40,48,56,48][c] * 0.46)));
    }, 0));
    sheet.getRangeByIndexes(5 + i, 0, 1, 6).format.rowHeight = Math.max(60, Math.max(...lines) * 15 + 18);
  });
  const table=sheet.tables.add(`A5:F${5 + normalized.length}`, true, "SimpleReviewFindings");
  table.style = "TableStyleLight1";
  table.showFilterButton = true;
  sheet.getRange(`A6:A${5 + normalized.length}`).dataValidation = {
    rule: { type: "list", values: ["不備", "リスク", "要確認"] },
  };
  sheet.getRange(`B6:B${5 + normalized.length}`).dataValidation = {
    rule: { type: "list", values: ["重大", "高", "中", "低", "情報"] },
  };
  colorStatuses(sheet, "A", 6, rows.map((row) => row[0]), categoryColors);
  colorStatuses(sheet, "B", 6, rows.map((row) => row[1]), severityColors);
  if (!rows.length) {
    const limits = data.summary?.limitations;
    sheet.getRange("A3").values = [[`指摘0件。${limits ? `確認上の制約：${limits}` : "確認範囲と総合判定はレビューサマリを参照。"}`]];
    sheet.getRange("A3:F3").format.rowHeight = 48;
  }
}

function createTemplate() {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("レビューサマリ");
  simpleSheet(workbook);
  const findings = workbook.worksheets.add("指摘一覧");
  const trace = workbook.worksheets.add("設計実装対応表");
  const inventory = workbook.worksheets.add("確認条件・対象一覧");

  [summary, findings, trace, inventory].forEach((sheet) => baseSheet(sheet));
  summary.tabColor = navy;
  findings.tabColor = "#B42318";
  trace.tabColor = blue;
  inventory.tabColor = "#6B7280";

  summary.getRange("A2").values = [["Salesforce実装レビュー"]];
  styleTitle(summary, "A2:K2");
  summary.getRange("A4:B4").values = [["基本情報", "内容"]];
  summary.getRange("A5:A12").values = [
    ["レビュー対象"], ["レビュー日"], ["レビュー方式"], ["総合判定"],
    ["対象版・APIバージョン"], ["入力資料"], ["主要な制約"], ["レビュー担当"],
  ];
  summary.getRange("B7").values = [["静的レビュー"]];
  styleHeader(summary.getRange("A4:B4"));
  summary.getRange("A5:A12").format = { fill: lightBlue, font: { name: fontName, bold: true, color: navy } };
  summary.getRange("A4:B12").format.borders = { preset: "all", style: "thin", color: border };
  summary.getRange("B5:B12").format.wrapText = true;
  summary.getRange("A4").format.columnWidth = 23;
  summary.getRange("B4").format.columnWidth = 66;
  summary.getRange("D4:E4").values = [["重大度", "件数"]];
  summary.getRange("D5:D9").values = [["重大"], ["高"], ["中"], ["低"], ["情報"]];
  summary.getRange("E5:E9").formulas = [
    ['=COUNTIF(\'指摘一覧\'!$C$6:$C$505,"重大")'],
    ['=COUNTIF(\'指摘一覧\'!$C$6:$C$505,"高")'],
    ['=COUNTIF(\'指摘一覧\'!$C$6:$C$505,"中")'],
    ['=COUNTIF(\'指摘一覧\'!$C$6:$C$505,"低")'],
    ['=COUNTIF(\'指摘一覧\'!$C$6:$C$505,"情報")'],
  ];
  styleHeader(summary.getRange("D4:E4"));
  summary.getRange("D5:E9").format.borders = { preset: "all", style: "thin", color: border };
  summary.getRange("D4").format.columnWidth = 15;
  summary.getRange("E4").format.columnWidth = 10;
  summary.getRange("G4:H4").values = [["確認状態", "件数"]];
  summary.getRange("G5:G8").values = [["確認済み"], ["一部確認"], ["未確認"], ["対象外"]];
  summary.getRange("H5:H8").formulas = [
    ['=COUNTIF(\'確認条件・対象一覧\'!$H$6:$H$505,"確認済み")'],
    ['=COUNTIF(\'確認条件・対象一覧\'!$H$6:$H$505,"一部確認")'],
    ['=COUNTIF(\'確認条件・対象一覧\'!$H$6:$H$505,"未確認")'],
    ['=COUNTIF(\'確認条件・対象一覧\'!$H$6:$H$505,"対象外")'],
  ];
  styleHeader(summary.getRange("G4:H4"));
  summary.getRange("G5:H8").format.borders = { preset: "all", style: "thin", color: border };
  summary.getRange("G4").format.columnWidth = 16;
  summary.getRange("H4").format.columnWidth = 10;
  summary.getRange("A14:H14").values = [["判定上の注意", null, null, null, null, null, null, null]];
  summary.getRange("A15:H17").values = [["指摘件数が0でも、主要範囲が未確認の場合は「可」としない。総合判定は件数だけでなく、影響と確認範囲に基づいて決める。", null, null, null, null, null, null, null], [null,null,null,null,null,null,null,null], [null,null,null,null,null,null,null,null]];
  summary.getRange("A14:H14").format = { fill: navy, font: { name: fontName, bold: true, color: "#FFFFFF" } };
  summary.getRange("A15:H17").format = { fill: pale, font: { name: fontName, color: "#202B38" }, wrapText: true };
  summary.getRange("A15:H17").format.borders = { preset: "outside", style: "thin", color: border };
  summary.getRange("A15:H17").merge();
  summary.getRange("A15:H17").format.rowHeight = 28;

  const findingHeaders = ["指摘ID","関連指摘ID","重大度","判定区分","確度","レビュー観点","対象種別","コンポーネント名","実装ファイル","実装行・XML位置","設計書","設計シート・節","設計行・セル・ページ","指摘内容","根拠となる事実","影響・発生条件","推奨対応","修正時の注意点","確認・テスト方法","根拠資料","対応状況","担当者","回答・対応内容"];
  findings.getRange("A2").values = [["指摘一覧"]];
  findings.getRange("A3").values = [["1指摘・1修正箇所を1行で記録する。行番号は空行・コメントを含む1始まり。推測と確認済み事実を分ける。"]];
  findings.getRange("A5:W5").values = [findingHeaders];
  findings.getRange("A6:W6").values = [Array(23).fill(null)];
  styleTitle(findings, "A2:W2");
  styleHeader(findings.getRange("A5:W5"));
  findings.getRange("A3:W3").format = { font: { name: fontName, italic: true, color: "#4B5563" } };
  findings.getRange("A6:W505").format = { font: { name: fontName, size: 10, color: "#202B38" }, verticalAlignment: "top", wrapText: true };
  [10,12,10,12,9,18,16,24,34,24,32,24,26,45,48,45,45,40,45,35,14,15,40].forEach((width, i) => findings.getRangeByIndexes(4, i, 501, 1).format.columnWidth = width);
  findings.freezePanes.freezeRows(5);
  findings.freezePanes.freezeColumns(3);
  findings.tables.add("A5:W6", true, "ReviewFindings").style = "TableStyleLight1";
  findings.getRange("C6:C505").dataValidation = { rule: { type: "list", values: ["重大","高","中","低","情報"] } };
  findings.getRange("D6:D505").dataValidation = { rule: { type: "list", values: ["不備","リスク","要確認"] } };
  findings.getRange("E6:E505").dataValidation = { rule: { type: "list", values: ["高","中","低"] } };
  findings.getRange("U6:U505").dataValidation = { rule: { type: "list", values: ["未対応","対応中","解消","一部解消","未解消","再現不能","対象外化"] } };
  findings.getRange("C6:C505").conditionalFormats.add("containsText", { text: "重大", format: { fill: "#F8D7DA", font: { color: "#8A1C1C", bold: true } } });
  findings.getRange("C6:C505").conditionalFormats.add("containsText", { text: "高", format: { fill: "#FCE8D5", font: { color: "#9A4A00", bold: true } } });
  findings.getRange("D6:D505").conditionalFormats.add("containsText", { text: "不備", format: { fill: "#FDE8E7", font: { color: "#9B1C1C", bold: true } } });

  const traceHeaders = ["対応ID","設計書","設計シート・節","設計行・セル・ページ","設計項目・要件","要件重要度","実装状態","対象種別","コンポーネント名","実装ファイル","実装行・XML位置","確認結果・根拠","関連指摘ID","備考・不足情報"];
  trace.getRange("A2").values = [["設計実装対応表"]];
  trace.getRange("A3").values = [["設計要件を全件記録し、実装済み・不一致・未実装・確認不能・対象外のいずれかで判定する。"]];
  trace.getRange("A5:N5").values = [traceHeaders];
  trace.getRange("A6:N6").values = [Array(14).fill(null)];
  styleTitle(trace, "A2:N2");
  styleHeader(trace.getRange("A5:N5"));
  trace.getRange("A3:N3").format = { font: { name: fontName, italic: true, color: "#4B5563" } };
  trace.getRange("A6:N505").format = { font: { name: fontName, size: 10, color: "#202B38" }, verticalAlignment: "top", wrapText: true };
  [10,32,24,26,48,12,14,16,24,34,24,52,16,40].forEach((width, i) => trace.getRangeByIndexes(4, i, 501, 1).format.columnWidth = width);
  trace.freezePanes.freezeRows(5);
  trace.freezePanes.freezeColumns(2);
  trace.tables.add("A5:N6", true, "DesignTraceability").style = "TableStyleLight1";
  trace.getRange("F6:F505").dataValidation = { rule: { type: "list", values: ["重大","高","中","低","情報"] } };
  trace.getRange("G6:G505").dataValidation = { rule: { type: "list", values: ["実装済み","不一致","未実装","確認不能","対象外"] } };
  trace.getRange("G6:G505").conditionalFormats.add("containsText", { text: "不一致", format: { fill: "#FDE8E7", font: { color: "#9B1C1C", bold: true } } });
  trace.getRange("G6:G505").conditionalFormats.add("containsText", { text: "未実装", format: { fill: "#FDE8E7", font: { color: "#9B1C1C", bold: true } } });
  trace.getRange("G6:G505").conditionalFormats.add("containsText", { text: "確認不能", format: { fill: "#FFF4CC", font: { color: "#7A5200", bold: true } } });

  const inventoryHeaders = ["管理ID","区分","種別","名称","パス・URL","版・APIバージョン","更新日・確認日","確認状態","対象範囲","対象外・未確認範囲","備考・制約"];
  inventory.getRange("A2").values = [["確認条件・対象一覧"]];
  inventory.getRange("A3").values = [["入力資料、実装対象、公式資料、対象外、未確認範囲を記録する。無断で対象を省略しない。"]];
  inventory.getRange("A5:K5").values = [inventoryHeaders];
  inventory.getRange("A6:K6").values = [Array(11).fill(null)];
  styleTitle(inventory, "A2:K2");
  populateSimple(workbook, { findings: [] });
  styleHeader(inventory.getRange("A5:K5"));
  inventory.getRange("A3:K3").format = { font: { name: fontName, italic: true, color: "#4B5563" } };
  inventory.getRange("A6:K505").format = { font: { name: fontName, size: 10, color: "#202B38" }, verticalAlignment: "top", wrapText: true };
  [11,15,18,35,58,22,20,15,38,38,44].forEach((width, i) => inventory.getRangeByIndexes(4, i, 501, 1).format.columnWidth = width);
  inventory.freezePanes.freezeRows(5);
  inventory.freezePanes.freezeColumns(2);
  inventory.tables.add("A5:K6", true, "ReviewInventory").style = "TableStyleLight1";
  inventory.getRange("H6:H505").dataValidation = { rule: { type: "list", values: ["確認済み","一部確認","未確認","対象外"] } };
  inventory.getRange("H6:H505").conditionalFormats.add("containsText", { text: "未確認", format: { fill: "#FFF4CC", font: { color: "#7A5200", bold: true } } });
  inventory.getRange("H6:H505").conditionalFormats.add("containsText", { text: "一部確認", format: { fill: "#FFF4CC", font: { color: "#7A5200" } } });

  [summary, findings, trace, inventory].forEach((sheet) => {
    const used = sheet.getUsedRange();
    used.format.verticalAlignment = "center";
  });
  styleTitle(summary, "A2:K2");
  styleTitle(findings, "A2:W2");
  styleTitle(trace, "A2:N2");
  styleTitle(inventory, "A2:K2");
  return workbook;
}

async function populate(workbook, data) {
  const summary = workbook.worksheets.getItem("レビューサマリ");
  const findings = workbook.worksheets.getItem("指摘一覧");
  const trace = workbook.worksheets.getItem("設計実装対応表");
  const inventory = workbook.worksheets.getItem("確認条件・対象一覧");
  const summaryValues = [
    data.summary?.target ?? "",
    data.summary?.reviewDate ?? "",
    data.summary?.method ?? "静的レビュー",
    data.summary?.overall ?? "判定不能",
    data.summary?.version ?? "",
    data.summary?.inputs ?? "",
    data.summary?.limitations ?? "",
    data.summary?.reviewer ?? "",
  ];
  summary.getRange("B5:B12").values = summaryValues.map((value) => [value]);
  summary.getRange("B10:B11").format.rowHeight = 42;

  const blocks = [
    [findings, "A6:W505", data.findings ?? [], 23, "ReviewFindings", "A5", "W"],
    [trace, "A6:N505", data.traceability ?? [], 14, "DesignTraceability", "A5", "N"],
    [inventory, "A6:K505", data.inventory ?? [], 11, "ReviewInventory", "A5", "K"],
  ];
  for (const [sheet, clearRange, rows, columns, tableName, start, endColumn] of blocks) {
    sheet.getRange(clearRange).clear({ applyTo: "contents" });
    for (const table of [...sheet.tables.items]) table.delete();
    const normalized = rows.length ? rows.map((row) => {
      if (!Array.isArray(row) || row.length !== columns) throw new Error(`${sheet.name}: each row must have ${columns} columns`);
      return row;
    }) : [Array(columns).fill(null)];
    sheet.getRange("A6").write(normalized);
    const rowHeight = sheet.name === "指摘一覧" ? 126 : sheet.name === "設計実装対応表" ? 78 : 60;
    sheet.getRangeByIndexes(5, 0, normalized.length, columns).format.rowHeight = rowHeight;
    const lastRow = 5 + normalized.length;
    const table = sheet.tables.add(`${start}:${endColumn}${lastRow}`, true, tableName);
    table.style = "TableStyleLight1";
  }
  colorStatuses(findings, "C", 6, (data.findings ?? []).map((row) => row[2]), severityColors);
  colorStatuses(findings, "D", 6, (data.findings ?? []).map((row) => row[3]), categoryColors);
  colorStatuses(trace, "F", 6, (data.traceability ?? []).map((row) => row[5]), severityColors);
  colorStatuses(trace, "G", 6, (data.traceability ?? []).map((row) => row[6]), stateColors);
  colorStatuses(inventory, "H", 6, (data.inventory ?? []).map((row) => row[7]), stateColors);
  populateSimple(workbook, data);
  return workbook;
}

let workbook;
if (mode === "template") {
  const templatePath=argument("--template");
  if (templatePath) {
    workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(path.resolve(templatePath)));
    populateSimple(workbook,{findings:[]});
  } else {
    workbook = createTemplate();
  }
} else {
  const templatePath = path.resolve(argument("--template", defaultTemplate));
  const dataPath = argument("--data");
  if (!dataPath) throw new Error("--data is required in review mode");
  const template = await FileBlob.load(templatePath);
  workbook = await SpreadsheetFile.importXlsx(template);
  const data = JSON.parse(await fs.readFile(path.resolve(dataPath), "utf8"));
  workbook = await populate(workbook, data);
}

workbook.recalculate();
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  maxChars: 8000,
});
console.log(formulaErrors.ndjson);

const renderDir = argument("--render-dir");
if (renderDir) {
  await fs.mkdir(path.resolve(renderDir), { recursive: true });
  const ranges = {
    "レビューサマリ": "A1:H17",
    "簡易指摘一覧": "A1:F10",
    "指摘一覧": "A1:W10",
    "設計実装対応表": "A1:N10",
    "確認条件・対象一覧": "A1:K10",
  };
  for (const [sheetName, range] of Object.entries(ranges)) {
    const image = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(path.resolve(renderDir, `${sheetName}.png`), new Uint8Array(await image.arrayBuffer()));
  }
}
await fs.mkdir(path.dirname(path.resolve(outputPath)), { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(path.resolve(outputPath));

const check = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
console.log(check.ndjson);
