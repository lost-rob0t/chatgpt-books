(asdf:defsystem #:symbolic-ai-rules
  :description "Transparent teaching production-rule system for Symbolic AI in Common Lisp."
  :version "0.1.0"
  :depends-on (#:symbolic-ai-pattern)
  :serial t
  :components ((:file "package")
               (:file "rules")))

(asdf:defsystem #:symbolic-ai-rules/tests
  :depends-on (#:symbolic-ai-rules)
  :serial t
  :components ((:file "tests"))
  :perform (asdf:test-op (operation component)
             (declare (ignore operation component))
             (uiop:symbol-call '#:symbolic-ai.rules.tests '#:run-tests)))
