#!/usr/bin/env bash
# Exact reproduction of books-ci Org-roam/ERT steps (ci.yml lines 57-81).
set -uo pipefail
mkdir -p probe-logs

sudo apt-get update > probe-logs/apt.log 2>&1
sudo apt-get install -y emacs-nox >> probe-logs/apt.log 2>&1
emacs --version | head -1 | tee probe-logs/emacs-version.log

emacs -Q --batch \
  --eval "(require 'package)" \
  --eval "(setq package-user-dir (expand-file-name \".cache/elpa\" default-directory))" \
  --eval "(setq package-install-upgrade-built-in t)" \
  --eval "(setq package-archives '((\"gnu\" . \"https://elpa.gnu.org/packages/\") (\"nongnu\" . \"https://elpa.nongnu.org/nongnu/\") (\"melpa\" . \"https://melpa.org/packages/\")))" \
  --eval "(package-initialize)" \
  --eval "(package-refresh-contents)" \
  --eval "(package-install 'org-roam)" \
  > probe-logs/org-roam-install.log 2>&1
echo "org-roam-install exit: $?"

emacs -Q --batch \
  --eval "(require 'package)" \
  --eval "(setq package-user-dir (expand-file-name \".cache/elpa\" default-directory))" \
  --eval "(package-initialize)" \
  -L elisp \
  -l test/chatgpt-books-test.el \
  -f ert-run-tests-batch-and-exit \
  > probe-logs/ert.log 2>&1
echo "ert exit: $?"
ls -la .cache/org-roam.db >> probe-logs/ert.log 2>&1
