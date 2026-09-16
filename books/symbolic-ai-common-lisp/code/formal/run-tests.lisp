(load (merge-pathnames "package.lisp" *load-truename*))
(load (merge-pathnames "formal.lisp" *load-truename*))
(load (merge-pathnames "tests.lisp" *load-truename*))

(unless (symbolic-ai-formal::run-formal-tests)
  (uiop:quit 1))
