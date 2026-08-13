;;; chatgpt-books-assets.el --- Asset commands -*- lexical-binding: t; -*-
;;; Commentary: Thin Emacs front-end for deterministic asset generation.
;;; Code:
(require 'compile)
(require 'chatgpt-books)
(defun chatgpt-books-assets-build (slug)
  "Build deterministic assets for book SLUG."
  (interactive (list (completing-read "Book: " (chatgpt-books-book-slugs) nil t)))
  (compile (format "make -C %s assets BOOK=%s" (shell-quote-argument (chatgpt-books-root)) (shell-quote-argument slug))))
(provide 'chatgpt-books-assets)
;;; chatgpt-books-assets.el ends here
