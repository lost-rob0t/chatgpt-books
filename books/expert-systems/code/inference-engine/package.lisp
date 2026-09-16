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
           #:match-conditions
           #:working-memory
           #:make-working-memory
           #:facts-in-working-memory
           #:assert-fact
           #:retract-fact
           #:fact-assertion-sequence
           #:production
           #:make-production
           #:production-id
           #:production-conditions
           #:production-actions
           #:production-salience
           #:production-provenance
           #:activation
           #:activation-production-id
           #:activation-bindings
           #:activation-fact-ids
           #:activation-salience
           #:activation-recency
           #:activation-specificity
           #:activation-signature
           #:inference-session
           #:make-inference-session
           #:session-agenda
           #:run-forward-chain
           #:inference-result
           #:inference-result-status
           #:inference-result-firings
           #:inference-result-agenda
           #:firing-record
           #:firing-record-step
           #:firing-record-production-id
           #:firing-record-support-fact-ids
           #:firing-record-asserted-fact-ids))

(in-package #:expert-systems.matcher)
