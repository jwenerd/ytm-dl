#!/usr/bin/env bash

proj_dir=$(dirname $0)
cd $proj_dir
source bin/activate
python ytm-dl.py

cd output
git add -A
git commit --message="🤠 🎶 🎻"
git push origin