(asdf:defsystem "symbolic-ai-formal"
  :description "Finite formal-systems teaching workbench for Symbolic AI in Common Lisp"
  :version "0.1.0"
  :serial t
  :components ((:file "package")
               (:file "formal")))

(asdf:defsystem "symbolic-ai-formal/tests"
  :depends-on ("symbolic-ai-formal")
  :serial t
  :components ((:file "tests"))
  :perform (test-op (operation component)
             (declare (ignore operation component))
             (unless (symbol-call :symbolic-ai-formal :run-formal-tests)
               (error "Formal-methods tests failed."))))
