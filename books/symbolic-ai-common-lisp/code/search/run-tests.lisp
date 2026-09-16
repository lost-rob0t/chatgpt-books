(let* ((here (or *load-truename* *compile-file-truename*))
       (directory (make-pathname :name nil :type nil :defaults here)))
  (load (merge-pathnames "package.lisp" directory))
  (load (merge-pathnames "search.lisp" directory))
  (load (merge-pathnames "tests.lisp" directory))
  (load (merge-pathnames "metamorphic-tests.lisp" directory)))

(symbolic-ai.search.tests:run-tests)
