(asdf:defsystem #:symbolic-ai-formal
  :description "Finite formal-systems teaching workbench for Symbolic AI in Common Lisp"
  :version "0.1.0"
  :serial t
  :components ((:file "package")
               (:file "formal")))

(asdf:defsystem #:symbolic-ai-formal/tests
  :depends-on (#:symbolic-ai-formal)
  :serial t
  :components ((:file "tests"))
  :perform (asdf:test-op (operation component)
             (declare (ignore operation component))
             (uiop:symbol-call '#:symbolic-ai-formal '#:run-formal-tests)))
