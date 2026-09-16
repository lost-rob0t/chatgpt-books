(in-package #:expert-systems.matcher)

(defvar *incremental-tests-run* 0)

(defun incremental-check-true (value label)
  (incf *incremental-tests-run*)
  (unless value
    (error "FAIL incremental ~A: expected true, got ~S" label value)))

(defun incremental-check-equal (expected actual label)
  (incf *incremental-tests-run*)
  (unless (equal expected actual)
    (error "FAIL incremental ~A: expected ~S, got ~S" label expected actual)))

(defun agenda-keys (agenda)
  (mapcar #'activation-key agenda))

(defun current-fact-ids (engine)
  (mapcar #'fact-id
          (working-memory-facts (engine-working-memory engine))))

(defun firing-rule-ids (engine)
  (mapcar #'firing-record-production-id (engine-firing-records engine)))

(defun run-incremental-tests ()
  (setf *incremental-tests-run* 0)

  ;; Compilation caches local matches and complete joins without changing the
  ;; milestone-B observable agenda contract.
  (let* ((engine (make-engine :facts *service-diagnosis-facts*
                              :productions (make-service-diagnosis-productions)))
         (network (make-incremental-network engine))
         (dependency-network
           (incremental-production-network network "rule.dependency-impact"))
         (alpha (production-network-alpha-memories dependency-network))
         (beta (production-network-beta-memories dependency-network)))
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "seeded incremental agenda equals complete-rematch oracle")
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "seeded cache references only current working-memory occurrences")
    (incremental-check-equal '(1 1)
                             (mapcar (lambda (memory)
                                       (length (alpha-memory-items memory)))
                                     alpha)
                             "alpha memories cache only local condition matches")
    (incremental-check-equal '(1 1 1)
                             (mapcar (lambda (memory)
                                       (length (beta-memory-tokens memory)))
                                     beta)
                             "beta memories retain root partial and complete tokens")
    (let ((terminal (first (beta-memory-tokens (third beta)))))
      (incremental-check-equal
       '("obs.api.state.failed" "dep.frontend.api")
       (beta-token-fact-ids terminal)
       "terminal beta token preserves condition-ordered supports")
      (incremental-check-equal
       '(("obs.api.state.failed" . 1) ("dep.frontend.api" . 4))
       (beta-token-support-stamps terminal)
       "terminal beta token preserves support occurrences")))

  ;; One new assertion should flow through only its alpha/join paths and yield
  ;; the same complete activation as a fresh oracle rematch.
  (let* ((state (test-fact "state" 'service-state '(api failed)))
         (restart (test-fact "restart" 'service-restart-policy '(api on-failure)))
         (production
           (noop-production "rule.requires-restart"
                            '((service-state ?service failed)
                              (service-restart-policy ?service on-failure))))
         (engine (make-engine :facts (list state)
                              :productions (list production)))
         (network (make-incremental-network engine)))
    (incremental-check-equal '() (incremental-agenda network)
                             "missing second condition has no activation")
    (incremental-assert-fact network restart)
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "assertion propagation equals complete-rematch oracle")
    (incremental-check-equal 1 (length (incremental-agenda network))
                             "assertion creates one complete activation")

    ;; Retraction deletes every cached token that depended on the exact WME
    ;; occurrence; unrelated alpha state remains available for later joins.
    (incremental-retract-fact network "state")
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "retraction propagation equals complete-rematch oracle")
    (incremental-check-equal '() (incremental-agenda network)
                             "retracting support removes dependent activation")
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "retraction leaves no stale cache support references")

    ;; Reasserting the stable ID creates a new occurrence and therefore a new
    ;; activation/refraction identity, exactly as milestone B specifies.
    (let ((entry (incremental-assert-fact network state)))
      (incremental-check-equal 3 (wm-entry-sequence entry)
                               "reassertion gets a fresh occurrence sequence"))
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "reassertion agenda equals complete-rematch oracle")
    (incremental-check-equal
     '(3 2)
     (mapcar #'cdr
             (activation-support-stamps (first (incremental-agenda network))))
     "reasserted activation exposes new and retained occurrence stamps")
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "reassertion cache references the new occurrence rather than the old one"))

  ;; Batch assertion validates the whole batch in the milestone-B engine, then
  ;; propagates each accepted new occurrence through the incremental network.
  (let* ((state (test-fact "batch.state" 'service-state '(api failed)))
         (restart (test-fact "batch.restart" 'service-restart-policy
                             '(api on-failure)))
         (production
           (noop-production "rule.batch-restart"
                            '((service-state ?service failed)
                              (service-restart-policy ?service on-failure))))
         (engine (make-engine :productions (list production)))
         (network (make-incremental-network engine))
         (entries (incremental-assert-facts network (list state restart))))
    (incremental-check-equal '(1 2)
                             (mapcar #'wm-entry-sequence entries)
                             "batch assertion returns ordered new occurrences")
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "batch assertion agenda equals complete-rematch oracle")
    (incremental-check-equal 1 (length (incremental-agenda network))
                             "batch assertion creates one joined activation")
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "batch assertion cache references current occurrences"))

  ;; Cache-reference soundness and cache completeness are different properties.
  ;; Bypassing the delta API can leave every old reference valid while omitting
  ;; matches for a newly asserted fact. The oracle catches that incompleteness;
  ;; rebuilding the network restores equivalence.
  (let* ((state (test-fact "bypass.state" 'service-state '(api failed)))
         (restart (test-fact "bypass.restart" 'service-restart-policy
                             '(api on-failure)))
         (production
           (noop-production "rule.bypass"
                            '((service-state ?service failed)
                              (service-restart-policy ?service on-failure))))
         (engine (make-engine :facts (list state)
                              :productions (list production)))
         (network (make-incremental-network engine)))
    (assert-fact (engine-working-memory engine) restart)
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "bypassed assertion can leave old cache references individually valid")
    (incremental-check-true
     (not (equal (agenda-keys (build-agenda engine))
                 (agenda-keys (incremental-agenda network))))
     "bypassed assertion is detected by oracle agenda disagreement")
    (let ((rebuilt (make-incremental-network engine)))
      (incremental-check-equal
       (agenda-keys (build-agenda engine))
       (agenda-keys (incremental-agenda rebuilt))
       "network rebuild restores agenda equivalence after bypassed delta")
      (incremental-check-true
       (incremental-cache-references-current-p rebuilt)
       "rebuilt cache references current working-memory occurrences")))

  ;; Incremental firing must preserve the milestone-B fail-before-mutation
  ;; boundary. If an action proposes invalid output, FIRE-ACTIVATION signals
  ;; before working memory/refraction/history changes and the wrapper must not
  ;; mutate caches either.
  (let* ((state (test-fact "invalid.state" 'service-state '(api failed)))
         (production
           (make-production
            :id "rule.invalid-output"
            :conditions '((service-state ?service failed))
            :action (lambda (activation)
                      (declare (ignore activation))
                      (list :not-a-fact))))
         (engine (make-engine :facts (list state)
                              :productions (list production)))
         (network (make-incremental-network engine))
         (activation (first (incremental-agenda network)))
         (before-fact-ids (current-fact-ids engine))
         (before-snapshot (incremental-network-snapshot network))
         (error-text nil))
    (handler-case
        (incremental-fire-activation network activation)
      (error (condition)
        (setf error-text (princ-to-string condition))))
    (incremental-check-true
     (and error-text
          (search "Expected a FACT" error-text :test #'char-equal))
     "invalid incremental firing exposes the expected validation failure")
    (incremental-check-equal before-fact-ids
                             (current-fact-ids engine)
                             "failed incremental firing leaves working memory unchanged")
    (incremental-check-equal '() (engine-firing-records engine)
                             "failed incremental firing records no firing")
    (incremental-check-equal '() (engine-refracted-keys engine)
                             "failed incremental firing does not mark refraction")
    (incremental-check-equal before-snapshot
                             (incremental-network-snapshot network)
                             "failed incremental firing leaves cache state unchanged")
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "failed incremental firing preserves oracle agenda equivalence")
    (incremental-check-true
     (incremental-cache-references-current-p network)
     "failed incremental firing preserves cache-reference soundness"))

  ;; The existing matcher permits one fact to satisfy more than one condition;
  ;; the incremental network must preserve that declared semantic edge case.
  (let* ((pair (test-fact "pair" 'pair '(api api)))
         (production (noop-production "rule.same-fact-twice"
                                      '((pair ?x ?x) (pair ?x ?x))))
         (engine (make-engine :facts (list pair)
                              :productions (list production)))
         (network (make-incremental-network engine)))
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "same fact may support multiple conditions in both engines")
    (incremental-check-equal '("pair" "pair")
                             (activation-fact-ids
                              (first (incremental-agenda network)))
                             "reused support remains explicit in token order"))

  ;; An empty LHS is an edge case of the existing complete matcher: one empty
  ;; match. The root beta token is the incremental identity for the same case.
  (let* ((production (noop-production "rule.unconditional" '()))
         (engine (make-engine :productions (list production)))
         (network (make-incremental-network engine)))
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "root beta token preserves empty-condition production semantics"))

  ;; Fire through the existing engine mutation boundary, then ensure the new
  ;; derived occurrence was propagated into the cached network.
  (let* ((engine (make-engine :facts *service-diagnosis-facts*
                              :productions (make-service-diagnosis-productions)))
         (network (make-incremental-network engine))
         (first-activation (first (incremental-agenda network))))
    (incremental-fire-activation network first-activation)
    (incremental-check-true
     (find-wm-entry (engine-working-memory engine)
                    "derived.dependency-impact.frontend.api")
     "incremental firing commits the first derived fact")
    (incremental-check-equal
     (agenda-keys (build-agenda engine))
     (agenda-keys (incremental-agenda network))
     "post-firing cached agenda equals complete-rematch oracle")
    (incremental-check-equal
     "rule.investigate-degraded-dependent"
     (production-id
      (activation-production (first (incremental-agenda network))))
     "new derived fact activates the downstream production"))

  ;; End-to-end equivalence uses separate engines so one implementation cannot
  ;; accidentally inherit the other's firing history.
  (let* ((oracle-engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (incremental-engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (network (make-incremental-network incremental-engine))
         (oracle-result (run-engine oracle-engine :firing-limit 10))
         (incremental-result (run-incremental-engine network :firing-limit 10)))
    (incremental-check-equal (run-result-status oracle-result)
                             (run-result-status incremental-result)
                             "end-to-end stop status equals oracle")
    (incremental-check-equal (run-result-firing-count oracle-result)
                             (run-result-firing-count incremental-result)
                             "end-to-end firing count equals oracle")
    (incremental-check-equal (firing-rule-ids oracle-engine)
                             (firing-rule-ids incremental-engine)
                             "end-to-end firing order equals oracle")
    (incremental-check-equal (current-fact-ids oracle-engine)
                             (current-fact-ids incremental-engine)
                             "end-to-end working-memory identities equal oracle")
    (incremental-check-equal '()
                             (incremental-agenda network)
                             "incremental service run reaches true quiescence"))

  (format t "~&PASS: ~D incremental matching checks~%" *incremental-tests-run*)
  t)

(run-incremental-tests)
