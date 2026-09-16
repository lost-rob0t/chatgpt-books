(defpackage #:symbolic-ai.pattern
  (:use #:cl)
  (:export
   #:apply-substitution
   #:make-variable
   #:match-pattern
   #:match-result
   #:match-result-bindings
   #:match-result-datum
   #:match-result-pattern
   #:match-result-reason
   #:match-result-status
   #:normalize-substitution
   #:unification-result
   #:unification-result-left
   #:unification-result-reason
   #:unification-result-right
   #:unification-result-status
   #:unification-result-substitution
   #:unify
   #:variable-name
   #:variable-p))

(in-package #:symbolic-ai.pattern)
