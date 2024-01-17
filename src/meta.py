import os
import subprocess
import yaml
from .util import output_path, deep_merge, deep_sort_keys, write_file

GITHUB_META_KEYS = ['actor', 'event_name', 'job', 'ref_name', 'run_attempt', 'repository', 'run_id', 'run_number', 'sha', 'workflow']
GITHUB_META_KEYS = tuple(['github_' + v for v in GITHUB_META_KEYS])

def github_meta():
	return {k.lower().replace('github_',''): v for k, v in os.environ.items() if k.lower() in GITHUB_META_KEYS}

class MetaOutput:
  readme_written = False

  def __init__(self, file, existing_meta = {}):
    self.file = file
    self.csv_file_path = output_path(f'{file}.csv')
    self.meta_dict = self.get_default_meta(existing_meta)

  def get_default_meta(self, existing_meta):
    meta = { 'GitHub': github_meta() }
    deep_merge(meta, existing_meta)
    return meta

  def add_meta(self, label_key, value):
    deep_merge(self.meta_dict, { label_key: value } )

  def clean_up_meta(self):
    self.meta_dict = { k: v for k, v in self.meta_dict.items() if len(v) > 0 }
    self.meta_dict = deep_sort_keys(self.meta_dict)

  def update_file_meta(self):
    file_meta_cmd = f"(wc -l {self.csv_file_path} && du -h {self.csv_file_path}) | xargs -n2 | cut -d ' ' -f 1"
    line_count, file_size = subprocess.check_output([file_meta_cmd], shell=True).decode().split()
    self.add_meta('CSV File', { 'lines': int(line_count), 'size': file_size })

  def write_files(self):
    self.update_file_meta()
    self.clean_up_meta()
    write_file(f'meta/{self.file}', yaml.dump(self.meta_dict))
    self.write_readme()

  def write_readme(self):
    if MetaOutput.readme_written:  # only doe this once per run
      return

    gh_meta = self.meta_dict.get('GitHub', None)

    content = 'manual runs 🙃'
    if not gh_meta is None:
      gh_meta = self.meta_dict['GitHub']
      action_href = f"https://github.com/{gh_meta['repository']}/actions/runs/{gh_meta['run_id']}"
      content = '## ⚙️ [Action](' + action_href + ')'

    write_file('README.md', content)
    MetaOutput.readme_written = True
