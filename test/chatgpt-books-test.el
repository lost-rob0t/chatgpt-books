;;; chatgpt-books-test.el --- ERT tests -*- lexical-binding: t; -*-
(require 'ert)
(require 'cl-lib)
(add-to-list 'load-path (expand-file-name "../elisp" (file-name-directory (or load-file-name buffer-file-name))))
(require 'chatgpt-books)
(require 'chatgpt-books-roam)

(ert-deftest chatgpt-books-root-detection ()
  (let ((chatgpt-books-root (file-name-directory (directory-file-name (expand-file-name ".." (file-name-directory (or load-file-name buffer-file-name)))))))
    (should (file-directory-p (chatgpt-books-root)))
    (should (file-exists-p (expand-file-name "README.org" (chatgpt-books-root))))))

(ert-deftest chatgpt-books-discovers-nine-books ()
  (should (= 9 (length (chatgpt-books-book-slugs)))))

(ert-deftest chatgpt-books-roam-db-is-project-local ()
  (should (string-suffix-p "/.cache/org-roam.db" (chatgpt-books-roam-db-location))))

(ert-deftest chatgpt-books-safe-book-paths ()
  (dolist (slug (chatgpt-books-book-slugs))
    (should-not (string-match-p "\\.\\." slug))
    (should (file-exists-p (expand-file-name "PROJECTS.org" (expand-file-name slug (chatgpt-books--books-directory)))))))

(ert-deftest chatgpt-books-roam-state-roundtrip ()
  (let ((org-roam-directory "/tmp/personal-roam")
        (org-roam-db-location "/tmp/personal.db")
        (org-roam-capture-templates '(("x" "personal" plain "%?")))
        (org-roam-db-autosync-mode nil)
        (chatgpt-books-roam--saved-state nil))
    (chatgpt-books-roam--save-state)
    (setq org-roam-directory "/tmp/project" org-roam-db-location "/tmp/project.db")
    (cl-letf (((symbol-function 'org-roam-db-autosync-mode) (lambda (&optional _) nil)))
      (chatgpt-books-roam-restore))
    (should (equal org-roam-directory "/tmp/personal-roam"))
    (should (equal org-roam-db-location "/tmp/personal.db"))))

(ert-deftest chatgpt-books-roam-real-database-sync ()
  "Build the project Org-roam DB and prove that real nodes are indexed."
  (skip-unless (require 'org-roam nil t))
  (let ((db (chatgpt-books-roam-db-location))
        (chatgpt-books-roam--saved-state nil))
    (when (file-exists-p db)
      (delete-file db))
    (unwind-protect
        (progn
          (chatgpt-books-roam-setup)
          (org-roam-db-sync)
          (should (file-exists-p db))
          (should (> (length (org-roam-node-list)) 0)))
      (chatgpt-books-roam-restore))))
