(asdf:defsystem #:symbolic-ai-pattern
  :description "Teaching implementation of symbolic pattern matching and first-order unification."
  :version "0.2.0"
  :serial t
  :components ((:file "package")
               (:file "pattern-unify")
               (:file "equation-unify")))

(asdf:defsystem #:symbolic-ai-pattern/tests
  :depends-on (#:symbolic-ai-pattern)
  :serial t
  :components ((:file "tests")
               (:file "validation-tests"))
  :perform (asdf:test-op (operation component)
             (declare (ignore operation component))
             (uiop:symbol-call '#:symbolic-ai.pattern.tests '#:run-tests)))
