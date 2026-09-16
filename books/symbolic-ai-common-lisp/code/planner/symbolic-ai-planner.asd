(asdf:defsystem #:symbolic-ai-planner
  :description "Course-local symbolic state-space planner built from the book's search and unification mechanisms."
  :version "0.2.0"
  :depends-on (#:symbolic-ai-search #:symbolic-ai-pattern)
  :serial t
  :components ((:file "package")
               (:file "planner")
               (:file "heuristics")))

(asdf:defsystem #:symbolic-ai-planner/tests
  :depends-on (#:symbolic-ai-planner)
  :serial t
  :components ((:file "tests"))
  :perform (asdf:test-op (operation component)
             (declare (ignore operation component))
             (uiop:symbol-call '#:symbolic-ai.planner.tests '#:run-tests)))
