import os
import subprocess
from glob import glob

import yaml

from .markdown import md_lines, md_table
from .util import (
    deep_merge,
    deep_sort_keys,
    make_dict_readonly,
    output_path,
    write_file,
    write_output_file,
)

GITHUB_META_KEYS = [
    "event_name",
    "event_schedule",
    "job",
    "ref_name",
    "run_attempt",
    "repository",
    "run_id",
    "run_number",
    "sha",
    "workflow",
]
GITHUB_META_KEYS = tuple(["github_" + v for v in GITHUB_META_KEYS])
GITHUB_META = {
    k.lower().replace("github_", ""): v
    for k, v in os.environ.items()
    if k.lower() in GITHUB_META_KEYS
}
make_dict_readonly(GITHUB_META)
IS_GITHUB = len(GITHUB_META) > 0


class MetaOutput:
    def __init__(self, file, existing_meta=None):
        if existing_meta is None:
            existing_meta = {}
        self.file = file
        self.file_path = output_path(f"{file}.csv")
        self.meta_dict = self.get_default_meta(existing_meta)

    def get_default_meta(self, existing_meta):
        meta = {}
        deep_merge(meta, existing_meta)
        return meta

    def add_meta(self, label_key, value):
        deep_merge(self.meta_dict, {label_key: value})

    def clean_up_meta(self):
        self.meta_dict = {k: v for k, v in self.meta_dict.items() if len(v) > 0}
        self.meta_dict = deep_sort_keys(self.meta_dict)

    def update_file_meta(self):
        self.add_meta("CSV File", file_sizes(self.file_path))

    def write_files(self):
        self.update_file_meta()
        self.clean_up_meta()
        write_output_file(f"meta/{self.file}", yaml.dump(self.meta_dict))


def file_sizes(file):
    cmds = " && ".join([f"wc -l {file}", f"du -h {file}", f"wc -c {file}"])
    file_meta_cmd = f"({cmds}) | xargs -n2 | cut -d ' ' -f 1"
    lines, size, _size_bytes = subprocess.check_output([file_meta_cmd], shell=True).decode().split()

    return {"lines": int(lines), "size": size}


def file_list():
    path = output_path()
    csv_files = glob(f"{path}/**/*.csv", recursive=True)
    csv_files.sort()
    return [{"file": f, **(file_sizes(f))} for f in csv_files]


def write_readme():
    markdown = ["# 📝  output "]
    if IS_GITHUB:
        href = (
            f"https://github.com/{GITHUB_META['repository']}/actions/runs/{GITHUB_META['run_id']}"
        )
        markdown += [f"## ⚙️ [{GITHUB_META['job']} #{GITHUB_META['run_number']}]({href})"]

    # file table
    path = output_path()

    def quote(v):
        return f"`{v}`"

    def to_link(file):
        return f"[{quote(file)} ]({file})"

    def fmt_file(file):
        return to_link(file.replace(f"{path}/", ""))

    data = [{k: fmt_file(v) if k == "file" else v for k, v in d.items()} for d in file_list()]
    data = [{"" if k == "file" else k: v for k, v in d.items()} for d in data]

    markdown += ["### 📁 Files", md_table(data)]
    write_output_file("README.md", md_lines(markdown))


def write_auth_meta():
    auth_info = MetaStore.get("auth").data.get("info")
    if not auth_info or "captured_at" not in auth_info:
        from .api import get_auth_info

        fresh_info = get_auth_info()
        if auth_info:
            fresh_info.update({k: v for k, v in auth_info.items() if v is not None})
        auth_info = fresh_info

    captured = auth_info.get("captured_at", "Unknown")
    age = auth_info.get("age", "Unknown")
    auth_type = auth_info.get("auth_type", "Unknown")

    lines = [
        "### 🔑 Authentication",
        f"- **Mode**: `{auth_type}`",
    ]
    if "captured_at" in auth_info:
        lines.append(f"- **Session Age**: {age} (Captured: `{captured}`)")
    lines.append("- **Status**: ✅ Active & Valid")
    write_file("tmp/step_output/auth_info.md", "\n".join(lines) + "\n")


def write_api_meta():
    data = list(MetaStore.get("api").data.values())
    md = md_lines("### 🤖 API Info", md_table(data))
    write_file("tmp/step_output/api_info.md", md)


def write_meta(updated=False):
    if updated:
        write_readme()

    if updated and IS_GITHUB:
        url = f"https://github.com/{GITHUB_META['repository']}/commit/__OUTPUTCOMMIT__?diff=unified&w=1"
        write_file("tmp/commit_link.md", f"### ± [Output Commit]({url})" + "\n\n")

    write_auth_meta()
    write_api_meta()


class MetaStore:
    instances = {}

    @staticmethod
    def get(name):
        if MetaStore.instances.get(name, None) is None:
            MetaStore.instances[name] = MetaStore(name)
        return MetaStore.instances[name]

    def __init__(self, name):
        self.name = name
        self.data = {}

    def add(self, key, value):
        self.data[key] = value
