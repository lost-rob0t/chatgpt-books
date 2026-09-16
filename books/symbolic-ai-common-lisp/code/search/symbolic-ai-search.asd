(asdf:defsystem #:symbolic-ai-search
  :description "Teaching implementation of deterministic graph-search algorithms."
  :version "0.1.0"
  :serial t
  :components ((:file "package")
               (:file "search")))

(asdf:defsystem #:symbolic-ai-search/tests
  :depends-on (#:symbolic-ai-search)
  :serial t
  :components ((:file "tests"))
  :perform (asdf:test-op (operation component)
             (declare (ignore operation component))
             (uiop:symbol-call '#:symbolic-ai.search.tests '#:run-tests)))
