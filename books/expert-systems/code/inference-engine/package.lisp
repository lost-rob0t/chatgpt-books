(defpackage #:expert-systems.matcher
  (:use #:cl)
  (:export #:fact
           #:make-fact
           #:fact-id
           #:fact-relation
           #:fact-arguments
           #:fact-provenance
           #:match-result
           #:match-result-bindings
           #:match-result-fact-ids
           #:variable-p
           #:literal-condition-match-p
           #:match-condition
           #:match-conditions))

(in-package #:expert-systems.matcher)
