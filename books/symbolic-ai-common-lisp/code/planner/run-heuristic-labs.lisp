(require :asdf)

(let* ((here (uiop:pathname-directory-pathname *load-truename*))
       (book (uiop:pathname-parent-directory-pathname
              (uiop:pathname-parent-directory-pathname here))))
  (asdf:load-asd (merge-pathnames "code/search/symbolic-ai-search.asd" book))
  (asdf:load-asd (merge-pathnames "code/pattern-unify/symbolic-ai-pattern.asd" book))
  (asdf:load-asd (merge-pathnames "code/planner/symbolic-ai-planner.asd" book)))

(asdf:load-system "symbolic-ai-planner/tests")
(uiop:symbol-call '#:symbolic-ai.planner.tests '#:run-heuristic-labs)
