const { GH_TOKEN, PASSKEY } = ASM.useSecret('jwenerd-ytm-dl', 'APP_SECRETS', 'latest', JSON.parse);

if (!GH_TOKEN || !PASSKEY) {
  throw "Missing GH_TOKEN or PASSKEY"
}
const FILES = {
  history: "1orUAIJEq9LX20-vU2qt_d4RI_dvAKw7Qmpx8sCUUvPQ",
  liked_songs: "1GQ3eEC6LuQsbzsavdJ9VIYIYLMD3Ce7QLCrrdPXkhK4",
  library_albums: "1CW3wFalk2t6Gb02X4QZR0jmZ-UD1h50oXxarGUVSEks",
};

const REPO = 'jwenerd/ytm-dl';
const WORKFLOW_ID = 'run.yml';

const NOT_FOUND = ContentService.createTextOutput('😵');

function onRun() {
  return __githubActionRequest();
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
