(require :asdf)

(let* ((here (uiop:pathname-directory-pathname *load-truename*))
       (book (uiop:pathname-parent-directory-pathname
              (uiop:pathname-parent-directory-pathname here))))
  (asdf:load-asd (merge-pathnames "code/pattern-unify/symbolic-ai-pattern.asd" book))
  (asdf:load-asd (merge-pathnames "code/rules/symbolic-ai-rules.asd" book)))

(asdf:load-system "symbolic-ai-rules/tests")
(symbolic-ai.rules.tests:run-tests)
