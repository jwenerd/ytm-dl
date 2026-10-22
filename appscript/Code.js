function onRun() {
  return saveCSVs();
}

function doGet() {
  return ContentService.createTextOutput('🤠');
}

function authorized(request, body) {
  const queryPasskey = request && request.parameter && request.parameter.passkey;
  const bodyPasskey = body && body.passkey;
  return queryPasskey === PASSKEY || bodyPasskey === PASSKEY;
}

function doPost(request) {
  let body = {};
  if (request && request.postData && request.postData.contents) {
    try {
      body = JSON.parse(request.postData.contents);
    } catch (e) {
      console.warn("Could not parse JSON postData: " + e);
    }
  }

  if (! authorized(request, body) ) {
    return NOT_FOUND;
  }

  // 1. Direct email dispatch from ReportMailer (separate process)
  if (body.action === "send_email" || body.html_body) {
    const emailResult = dispatchEmailFromPayload(body, request.parameter);
    return ContentService
      .createTextOutput(JSON.stringify(emailResult))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 2. Synchronous override if explicitly requested (?sync=true)
  if (request && request.parameter && request.parameter.sync === "true") {
    const output = {
      sheets: saveCSVs()
    };
    if (request.parameter.report === "daily") {
      try {
        output.email = sendDailyReportEmail();
      } catch (err) {
        console.error("Failed to dispatch daily report email: " + err);
        output.email_error = String(err);
      }
    }
    return ContentService
      .createTextOutput(JSON.stringify(output))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 3. Default: Asynchronous CSV synchronization with instant acknowledgment (< 500ms)
  _cleanupTriggers("asyncSaveCSVs");

  ScriptApp.newTrigger("asyncSaveCSVs")
    .timeBased()
    .after(1000)
    .create();

  return ContentService
    .createTextOutput(JSON.stringify({
      status: "queued",
      message: "CSV synchronization job accepted and scheduled"
    }))
    .setMimeType(ContentService.MimeType.JSON);
}

function asyncSaveCSVs() {
  try {
    saveCSVs();
  } catch (err) {
    console.error("Async saveCSVs failed: " + err);
  } finally {
    _cleanupTriggers("asyncSaveCSVs");
  }
}

function _cleanupTriggers(handlerName) {
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === handlerName) {
      try {
        ScriptApp.deleteTrigger(triggers[i]);
      } catch (err) {
        console.warn("Could not delete trigger: " + err);
      }
    }
  }
}

function saveCSVs() {
  const results = Object.entries(FILES).map( ([file, sheetId]) => {
    return _updateFile(file, sheetId);
  });
  console.log({ results });
  return results;
}

function dispatchEmailFromPayload(body, params) {
  const recipient = (body && body.recipient) || (params && params.recipient) || Session.getEffectiveUser().getEmail();
  const htmlBody = (body && body.html_body) || "";

  if (!htmlBody) {
    return { status: "error", message: "No html_body provided in request" };
  }

  const titleMatch = htmlBody.match(/<title>([^<]+)<\/title>/i);
  let subject = (body && body.subject) || (titleMatch ? titleMatch[1] : "Daily Listening Log");
  subject = subject.replace(/^[\s\p{Extended_Pictographic}\u2600-\u27bf\uFE0F]+/u, "").trim();
  const plainText = "Your daily listening log is ready. Please view this message in an HTML-compatible email client.";

  GmailApp.sendEmail(recipient, subject, plainText, {
    htmlBody: htmlBody,
    name: "ytm-dl Listening Log"
  });

  const successInfo = {
    status: "success",
    recipient: recipient,
    subject: subject,
    bytes: htmlBody.length
  };
  console.log("Email successfully dispatched via GmailApp:", successInfo);
  return successInfo;
}

function sendDailyReportEmail(options) {
  const recipient = (options && options.recipient) || Session.getEffectiveUser().getEmail();
  const url = `https://api.github.com/repos/${REPO}/contents/output/reports/daily.html?ref=main-output`;

  let htmlBody = "";
  try {
    htmlBody = __gh_req(url);
  } catch (err) {
    const msg = `Could not fetch daily.html from GitHub repository: ${err}`;
    console.error(msg);
    return { status: "error", message: msg };
  }

  return dispatchEmailFromPayload({ html_body: htmlBody, recipient: recipient });
}

function testSendDailyEmail() {
  const sampleHtml = `<!DOCTYPE html><html><body style="background:#0d1117;color:#f0f6fc;font-family:sans-serif;padding:20px;">
    <h2>YTM-DL Test Dispatch</h2>
    <p>This is an automated test verifying end-to-end Gmail dispatch from Google Apps Script.</p>
  </body></html>`;

  const result = dispatchEmailFromPayload({
    subject: "YTM-DL Test Dispatch",
    html_body: sampleHtml
  });
  console.log("testSendDailyEmail result:", result);
  return result;
}

function __gh_req(url) {
  const headers = {
    Accept: "application/vnd.github.v3.raw",
    Authorization: `Bearer ${GH_TOKEN}`
  };
  return UrlFetchApp.fetch(url, { headers })
    .getBlob()
    .getDataAsString();
}

function _updateFile(file, id) {
  const url = `https://api.github.com/repos/${REPO}/contents/output/${file}.csv?ref=main-output`;
  const gSheetDoc = SpreadsheetApp.openById(id);

  const data = Utilities.parseCsv(__gh_req(url));
  const wsht = gSheetDoc.getSheetByName("Sheet1").clearContents();
  wsht.getRange(1, 1, data.length, data[0].length).setValues(data);
  return "updated " + file + " - count: " + data.length;
}
