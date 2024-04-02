function onRun() {
  return saveCSVs();
}

function doGet() {
  return ContentService.createTextOutput('🤠');
}

function authorized(request) {
  const passkey = request.parameter.passkey;
  return passkey === PASSKEY;
}

function doPost(request) {
  if (! authorized(request) ) {
    return NOT_FOUND;
  }
  const result = saveCSVs();
  return ContentService
    .createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

function saveCSVs() {
  const results = Object.entries(FILES).map( ([file, sheetId]) => {
    return _updateFile(file, sheetId);
  });
  console.log({ results });
  return results;
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
  return "updated " + file + " - count: " + data.length
}
