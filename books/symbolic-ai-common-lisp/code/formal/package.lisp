(defpackage #:symbolic-ai-formal
  (:use #:cl)
  (:export
   #:invalid-transition-system
   #:unknown-successors
   #:unknown-state
   #:unknown-reason
   #:transition-system
   #:make-transition-system
   #:check-result
   #:check-result-status
   #:check-result-trace
   #:check-result-visited
   #:check-result-conclusive-p
   #:check-result-reason
   #:check-invariant
   #:run-formal-tests))
