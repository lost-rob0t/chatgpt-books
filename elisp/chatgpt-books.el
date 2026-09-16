;;; chatgpt-books.el --- Project entry point for chatgpt-books -*- lexical-binding: t; -*-
;;; Commentary:
;; Entry point and discovery helpers for the Org-first books repository.
;;; Code:
(require 'cl-lib)
(require 'seq)
(require 'subr-x)
(defgroup chatgpt-books nil "Project-local technical book authoring." :group 'org)
(defcustom chatgpt-books-root nil "Explicit repository root, or nil for discovery." :type '(choice (const nil) directory))
(defconst chatgpt-books--marker "README.org")
(defun chatgpt-books--valid-root-p (dir)
  "Return non-nil when DIR looks like the chatgpt-books root."
  (and dir (file-exists-p (expand-file-name chatgpt-books--marker dir))
       (file-directory-p (expand-file-name "books" dir))
       (file-directory-p (expand-file-name "elisp" dir))))
(defun chatgpt-books--root-from-library ()
  "Find project root relative to this installed library."
  (when-let ((lib (or load-file-name (locate-library "chatgpt-books"))))
    (let ((candidate (file-name-directory (directory-file-name (file-name-directory lib)))))
      (when (chatgpt-books--valid-root-p candidate) (file-truename candidate)))))
(defun chatgpt-books-root ()
  "Return the absolute repository root or signal a user error."
  (let* ((explicit (and chatgpt-books-root (expand-file-name chatgpt-books-root)))
         (from-buffer (and buffer-file-name (locate-dominating-file buffer-file-name chatgpt-books--marker)))
         (root (or (and (chatgpt-books--valid-root-p explicit) explicit)
                   (and (chatgpt-books--valid-root-p from-buffer) from-buffer)
                   (chatgpt-books--root-from-library))))
    (unless root (user-error "Cannot locate chatgpt-books repository root"))
    (file-truename root)))
(defun chatgpt-books--books-directory () (expand-file-name "books" (chatgpt-books-root)))
(defun chatgpt-books-book-slugs ()
  "Return sorted slugs for every in-tree book or book scaffold."
  (sort (seq-filter (lambda (name)
                      (file-exists-p (expand-file-name "README.org" (expand-file-name name (chatgpt-books--books-directory)))))
                    (directory-files (chatgpt-books--books-directory) nil "^[^.].*")) #'string<))
(defun chatgpt-books-project-book-slugs ()
  "Return sorted book slugs that currently expose a PROJECTS.org contract."
  (seq-filter (lambda (slug)
                (file-exists-p
                 (expand-file-name "PROJECTS.org"
                                   (expand-file-name slug (chatgpt-books--books-directory)))))
              (chatgpt-books-book-slugs)))
(defun chatgpt-books-open-book (slug)
  "Prompt for and open book SLUG README."
  (interactive (list (completing-read "Book: " (chatgpt-books-book-slugs) nil t)))
  (find-file (expand-file-name "README.org" (expand-file-name slug (chatgpt-books--books-directory)))))
(defun chatgpt-books-open-project ()
  "Open a major-project document for a selected active book."
  (interactive)
  (let ((slug (completing-read "Book: " (chatgpt-books-project-book-slugs) nil t)))
    (find-file (expand-file-name "PROJECTS.org" (expand-file-name slug (chatgpt-books--books-directory))))))
;;;###autoload
(defun chatgpt-books ()
  "Enter the project-scoped authoring environment and open README.org."
  (interactive)
  (require 'chatgpt-books-roam)
  (chatgpt-books-roam-setup)
  (find-file (expand-file-name "README.org" (chatgpt-books-root))))
(autoload 'chatgpt-books-build-book "chatgpt-books-export" "Build one book via repository tooling." t)
(autoload 'chatgpt-books-build-all "chatgpt-books-export" "Build all books via repository tooling." t)
(provide 'chatgpt-books)
;;; chatgpt-books.el ends here
