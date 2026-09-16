(let* ((here (or *load-truename* *compile-file-truename*))
       (directory (make-pathname :name nil :type nil :defaults here)))
  (load (merge-pathnames "package.lisp" directory))
  (load (merge-pathnames "formal.lisp" directory))
  (load (merge-pathnames "tests.lisp" directory)))

(symbolic-ai-formal::run-formal-tests)
