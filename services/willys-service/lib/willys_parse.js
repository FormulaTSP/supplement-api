// services/willys-service/lib/willys_parse.js
// Extracted parsing helpers from the older willys_sync flow.
// Given plain text from a PDF/HTML receipt, returns structured items.

function parseGroceryLines(txt) {
  const lines = (txt || "")
    .split(/\r?\n/)
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  const drop = [
    /^summa\b/i,
    /^totalt\b/i,
    /^moms\b/i,
    /^att betala\b/i,
    /^datum\b/i,
    /^kvitto\b/i,
    /^kassa\b/i,
    /^butik\b/i,
    /^betalning\b/i,
    /^kund\b/i,
    /^org\.?nr\b/i,
    /^l\u00f8ga priser/i,
    /^��ppettider/i,
    /^v\u00e4lkommen/i,
    /^kundservice/i,
    /^willys plus/i,
    /^mottaget\b/i,
    /^betalm/i,
    /^moms%/i,
    /^totalt \d+ varor$/i,
    /^[-=]{6,}$/i,
    /^utg\u00f8r$/i,
    /^klipp$/i,
    /^med willys plus har du sparat:/i,
  ];
  const isMostlyNumbers = (s) => {
    const letters = (s.match(/[A-Za-z\u00c0-\u017f]/g) || []).length;
    const digits = (s.match(/[0-9]/g) || []).length;
    return letters === 0 && digits >= 4 && (s.match(/,\d{2}/g) || []).length >= 2;
  };
  const kept = lines.filter(
    (l) => !drop.some((re) => re.test(l)) && !isMostlyNumbers(l)
  );
  if (kept.length <= 3) {
    return (txt || "")
      .split(/(?<=\S)\s{2,}(?=\S)/g)
      .map((s) => s.replace(/\s+/g, " ").trim())
      .filter(Boolean)
      .filter((l) => !drop.some((re) => re.test(l)) && !isMostlyNumbers(l));
  }
  return kept;
}

function normalizeNumber(str) {
  if (str == null) return null;
  const s = String(str).replace(/\s|\u00A0/g, "").replace(",", ".");
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}
function lastMoney(line) {
  const m = line.match(/(\d{1,3}(?:[ \u00A0]\d{3})*,\d{2}|\d+,\d{2})(?!.*\d)/);
  return m ? normalizeNumber(m[1]) : null;
}
function parseMultiBuy(line) {
  const m = line.match(/(\d+)\s*st\*\s*(\d+,\d{2})\s+(\d+,\d{2})/i);
  if (!m) return null;
  return {
    count: parseInt(m[1], 10),
    unitPrice: normalizeNumber(m[2]),
    total: normalizeNumber(m[3]),
  };
}
function parseWeightLine(line) {
  const m = line.match(
    /(\d+,\d+)\s*(kg|g|l|cl|ml)\s*\*\s*(\d+,\d{2})\s*kr\/(kg|l)\s+(\d+,\d{2})/i
  );
  if (!m) return null;
  return {
    qty: normalizeNumber(m[1]),
    unit: m[2].toLowerCase(),
    unitPrice: normalizeNumber(m[3]),
    unitPriceUnit: m[4].toLowerCase(),
    total: normalizeNumber(m[5]),
  };
}
function isDiscountLine(line) {
  if (/^\d+\s*\*\s*Rab:/i.test(line)) return true;
  if (/^\s*(Rabatt:|Rab:|W\s*Plus:)/i.test(line)) return true;
  return false;
}
function discountValue(line) {
  const m = line.match(/-?\d+,\d{2}(?!.*\d)/);
  return m ? -Math.abs(normalizeNumber(m[0])) : null;
}
function cleanName(name) {
  return name
    .replace(/\b(W\s*Plus:.*)$/i, "")
    .replace(/\bMAX\d+\b/i, "")
    .replace(/\bUTG\u00c5.R\b/i, "")
    .replace(/\bKLIPP\b/i, "")
    .replace(/\bRab(?:att)?:.*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

function parseItemsFromLines(lines) {
  const items = [];
  let pending = null;
  const commitPending = () => {
    if (!pending) return;
    const total = (pending.price ?? 0) + (pending.discount ?? 0);
    pending.total = Math.round(total * 100) / 100;
    items.push(pending);
    pending = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    if (
      /^(Delavst\u00c4\u201e\u00c6\u201cning|SPARA KVITTOT|\u00c5-ppettider|V\u00c4\u201a\u00c5\u00a1lkommen \u00d8ter!|Du betj\u00c4\u201c\u00c5\u00a1nades av|Kassa:)/i.test(
        raw
      )
    )
      continue;

    if (isDiscountLine(raw)) {
      const val = discountValue(raw);
      if (val != null) {
        if (pending) pending.discount = (pending.discount ?? 0) + val;
        else if (items.length)
          items[items.length - 1].discount =
            (items[items.length - 1].discount ?? 0) + val;
        else
          items.push({
            name: "RABATT",
            qty: 1,
            unit: "st",
            price: 0,
            discount: val,
            total: val,
            raw,
          });
      }
      continue;
    }

    const w = parseWeightLine(raw);
    if (w && pending) {
      Object.assign(pending, {
        qty: w.qty,
        unit: w.unit,
        unitPrice: w.unitPrice,
        unitPriceUnit: w.unitPriceUnit,
        price: w.total,
      });
      continue;
    }
    if (w && !pending) {
      pending = {
        name: "OK\u00c4\u00b4NT",
        qty: w.qty,
        unit: w.unit,
        unitPrice: w.unitPrice,
        unitPriceUnit: w.unitPriceUnit,
        price: w.total,
        discount: 0,
        raw,
      };
      continue;
    }
    if (pending) commitPending();

    const mb = parseMultiBuy(raw);
    if (mb) {
      items.push({
        name:
          cleanName(
            raw
              .replace(/(\d+)\s*st\*\s*\d+,\d{2}\s+\d+,\d{2}.*/i, "")
              .trim()
          ) || "OK\u00c4\u00b4NT",
        qty: mb.count,
        unit: "st",
        unitPrice: mb.unitPrice,
        unitPriceUnit: "st",
        price: mb.total,
        discount: 0,
        total: mb.total,
        raw,
      });
      continue;
    }

    const price = lastMoney(raw);
    if (price != null) {
      const noPrice = raw
        .replace(
          /(\d{1,3}(?:[ \u00A0]\d{3})*,\d{2}|\d+,\d{2})(?!.*\d)/,
          ""
        )
        .trim();
      let name =
        cleanName(noPrice.split(/\s+/).filter(Boolean).join(" ")) ||
        "OK\u00c4\u00b4NT";

      const next = lines[i + 1];
      const nextW = next ? parseWeightLine(next) : null;
      if (nextW) {
        pending = {
          name,
          qty: nextW.qty,
          unit: nextW.unit,
          unitPrice: nextW.unitPrice,
          unitPriceUnit: nextW.unitPriceUnit,
          price: nextW.total,
          discount: 0,
          raw: `${raw}\n${next}`,
        };
        i++;
        continue;
      }
      items.push({
        name,
        qty: 1,
        unit: "st",
        price,
        discount: 0,
        total: price,
        raw,
      });
      continue;
    }

    if (/^[A-Z\u00c0-\u017f0-9].*/i.test(raw)) {
      const next = lines[i + 1];
      const nextW = next ? parseWeightLine(next) : null;
      if (nextW) {
        pending = {
          name: cleanName(raw),
          qty: nextW.qty,
          unit: nextW.unit,
          unitPrice: nextW.unitPrice,
          unitPriceUnit: nextW.unitPriceUnit,
          price: nextW.total,
          discount: 0,
          raw: `${raw}\n${next}`,
        };
        i++;
      }
    }
  }
  commitPending();
  for (const it of items) {
    const base = it.price ?? 0,
      disc = it.discount ?? 0;
    it.total = Math.round((base + disc) * 100) / 100;
  }
  return items.filter((it) => {
    if (!it.name || /^Med Willys Plus har du sparat/i.test(it.name)) return false;
    const letters = (it.name.match(/[A-Za-z\u00c0-\u017f]/g) || []).length;
    const digits = (it.name.match(/[0-9]/g) || []).length;
    if (letters === 0 && digits >= 2) return false;
    return true;
  });
}

export function parseReceiptText(rawText) {
  if (!rawText) return { items: [], lineCount: 0, itemCount: 0, total: null };
  const lines = parseGroceryLines(rawText);
  const items = parseItemsFromLines(lines);
  const total = items.reduce((sum, it) => sum + (it.total ?? 0), 0);
  return {
    items,
    lineCount: lines.length,
    itemCount: items.length,
    total: Math.round(total * 100) / 100,
  };
}
