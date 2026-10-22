/**
 * ציוני דרך — Google Apps Script לאתר na-tel-aviv.github.io
 *
 * הטופס "שליחת ציון דרך" באתר שולח לכאן. כל ציון דרך נכנס כשורה בגיליון "ציוני דרך"
 * עם תיבת סימון "מאושר". רק שורות מסומנות מופיעות בלוח ההודעות באתר,
 * עד יום אחרי החגיגה.
 */
const SHEET_NAME = 'ציוני דרך';
const HEADERS = ['נשלח', 'שם', 'ציון הדרך', 'פגישה', 'תאריך', 'שעה', 'מאושר'];
const TZ = 'Asia/Jerusalem';
const NOTIFY = true; // מייל לבעלת הגיליון על כל ציון דרך חדש

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
    sh.setRightToLeft(true);
  }
  return sh;
}

function clean_(value, max) {
  return String(value == null ? '' : value).replace(/[\u0000-\u001f<>]/g, ' ').trim().slice(0, max);
}

function json_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}

function asDate_(v) {
  return v instanceof Date ? Utilities.formatDate(v, TZ, 'yyyy-MM-dd') : String(v).trim();
}

function asTime_(v) {
  return v instanceof Date ? Utilities.formatDate(v, TZ, 'HH:mm') : String(v).trim().slice(0, 5);
}

/** קבלת ציון דרך מהטופס באתר */
function doPost(e) {
  try {
    const d = JSON.parse(e.postData.contents);
    if (d.website) return json_({ ok: true }); // שדה מלכודת לרובוטים
    const name = clean_(d.name, 60), milestone = clean_(d.milestone, 60), meeting = clean_(d.meeting, 80);
    const date = clean_(d.date, 10), time = clean_(d.time, 5);
    if (!name || !milestone || !meeting || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) {
      return json_({ ok: false });
    }
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    const sh = sheet_();
    sh.appendRow([new Date(), name, milestone, meeting, "'" + date, "'" + time, false]);
    sh.getRange(sh.getLastRow(), 7).insertCheckboxes();
    lock.releaseLock();
    if (NOTIFY) {
      MailApp.sendEmail(Session.getEffectiveUser().getEmail(), 'ציון דרך חדש ממתין לאישור: ' + name,
        name + ' – ' + milestone + '\n' + meeting + ', ' + date + ' ' + time +
        '\n\nלאישור: לסמן ✔ בעמודה "מאושר" בגיליון:\n' + SpreadsheetApp.getActiveSpreadsheet().getUrl());
    }
    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false });
  }
}

/** ציוני הדרך המאושרים שעוד לא עברו — לאתר */
function doGet() {
  const today = Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');
  const items = sheet_().getDataRange().getValues().slice(1)
    .filter(r => r[6] === true)
    .map(r => ({ name: clean_(r[1], 60), milestone: clean_(r[2], 60), meeting: clean_(r[3], 80), date: asDate_(r[4]), time: asTime_(r[5]) }))
    .filter(x => /^\d{4}-\d{2}-\d{2}$/.test(x.date) && x.date >= today);
  return json_({ ok: true, items });
}

/** הרצה ראשונה מהעורך: יוצרת את הגיליון ומבקשת הרשאות */
function setup() {
  sheet_();
}
