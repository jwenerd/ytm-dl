import json
import os
import flask
import functions_framework
from github import Github


try:
    SECRETS = json.loads(os.environ.get('SECRETS', ''))
except Exception as e:
    SECRETS = {"GH_TOKEN": os.environ["GH_TOKEN"], "PASSKEY": os.environ["PASSKEY"]}


GH_TOKEN = SECRETS["GH_TOKEN"]
PASSKEY = SECRETS["PASSKEY"]
GH_REPO = "jwenerd/ytm-dl"
GH_ACTION = "run.yml"

repo = Github(login_or_token=GH_TOKEN).get_repo(GH_REPO, lazy=True)
workflow = repo.get_workflow(GH_ACTION)

def dispatch_github_run(option='all'):
    return workflow.create_dispatch("main", inputs={"run_option": option})


@functions_framework.http
def trigger_run_post(request: flask.Request):
    passkey = request.args.get('passkey', '')
    if (passkey != PASSKEY or request.method != 'POST'):
        return flask.make_response("🤠", 403)

    dispatched = dispatch_github_run()
    return {"dispatched": dispatched }
