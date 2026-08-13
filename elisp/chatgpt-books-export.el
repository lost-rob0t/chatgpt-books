;;; chatgpt-books-export.el --- Build commands -*- lexical-binding: t; -*-
;;; Commentary: Invoke repository build tools without embedding the publication implementation in dotfiles.
;;; Code:
(require 'compile)
(require 'chatgpt-books)
(defun chatgpt-books-export--book-command (target slug)
  (format "make -C %s %s BOOK=%s" (shell-quote-argument (chatgpt-books-root)) target (shell-quote-argument slug)))
(defun chatgpt-books-build-book (slug)
  "Build selected book SLUG via the repository Makefile."
  (interactive (list (completing-read "Book: " (chatgpt-books-book-slugs) nil t)))
  (compile (chatgpt-books-export--book-command "book" slug)))
(defun chatgpt-books-build-all ()
  "Build all book manuscripts through the repository tooling."
  (interactive)
  (compile (format "make -C %s all-books" (shell-quote-argument (chatgpt-books-root)))))
(provide 'chatgpt-books-export)
;;; chatgpt-books-export.el ends here
