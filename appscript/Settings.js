const { GH_TOKEN, PASSKEY } = ASM.useSecret("jwenerd-ytm-dl", "APP_SECRETS", "latest", JSON.parse);

if (!GH_TOKEN || !PASSKEY) {
  throw "Missing GH_TOKEN or PASSKEY";
}
const FILES = {
  history: "1orUAIJEq9LX20-vU2qt_d4RI_dvAKw7Qmpx8sCUUvPQ",
  liked_songs: "1GQ3eEC6LuQsbzsavdJ9VIYIYLMD3Ce7QLCrrdPXkhK4",
  library_albums: "1CW3wFalk2t6Gb02X4QZR0jmZ-UD1h50oXxarGUVSEks",
};

const REPO = "jwenerd/ytm-dl";
const WORKFLOW_ID = "run.yml";

const NOT_FOUND = ContentService.createTextOutput("😵");
