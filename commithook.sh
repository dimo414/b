#!/bin/bash

# Mercurial commit hook which prompts if you would like to run the tests, and
# then stop the command if any tests fail.  It is suggested you use it with the
# precommit hook, like so:
#
#   [hooks]
#   precommit=commithook.sh
#
# This does not stop you from committing (simply tell it not to run the tests)
# but is provided as a convenience to prevent regressions. Tests should always
# be run before pushing.

msg=$(printf '\e[1;33m%s\e[0m\n' "Would you like to run unit tests before committing? [Y/n] ")
read -r -p "$msg" response;
if [[ "$response" =~ ^([nN][oO]|[nN])$ ]]; then
  exit 0
fi


set -e

python src/b-test.py

bats src