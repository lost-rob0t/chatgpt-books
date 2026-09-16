(in-package #:expert-systems.matcher)

(defvar *assumption-tests-run* 0)

(defun assumption-check-true (value label)
  (incf *assumption-tests-run*)
  (unless value
    (error "FAIL assumptions ~A: expected true, got ~S" label value)))

(defun assumption-check-false (value label)
  (incf *assumption-tests-run*)
  (when value
    (error "FAIL assumptions ~A: expected false, got ~S" label value)))

(defun assumption-check-equal (expected actual label)
  (incf *assumption-tests-run*)
  (unless (equal expected actual)
    (error "FAIL assumptions ~A: expected ~S, got ~S"
           label expected actual)))

(defun assumption-check-signals-duplicate-spec-id (thunk label)
  (incf *assumption-tests-run*)
  (handler-case
      (progn
        (funcall thunk)
        (error "FAIL assumptions ~A: expected DUPLICATE-CONTRADICTION-SPEC-ID"
               label))
    (duplicate-contradiction-spec-id () t)))

(defun active-vs-failed-spec ()
  (make-contradiction-spec
   :id "constraint.systemd.active-state.active-vs-failed"
   :left-pattern '(unit-active-state ?unit active ?epoch)
   :right-pattern '(unit-active-state ?unit failed ?epoch)
   :provenance '(:source :systemd-dbus-unit-api
                 :claim :one-high-level-active-state-per-observation)))

(defun assumption-derived-production (id conditions fact-id relation arguments)
  (make-production
   :id id
   :conditions conditions
   :provenance '(:kind :test-rule)
   :action
   (lambda (activation)
     (list
      (make-fact
       :id fact-id
       :relation relation
       :arguments arguments
       :provenance
       (list :kind :derived
             :rule-id id
             :support-fact-ids (copy-list (activation-fact-ids activation))))))))

(defun run-assumption-tests ()
  (setf *assumption-tests-run* 0)

  ;; Contradiction declarations have stable identity just like productions.
  (let ((spec (active-vs-failed-spec)))
    (assumption-check-signals-duplicate-spec-id
     (lambda ()
       (make-assumption-network
        (make-truth-maintained-network (make-engine))
        :contradiction-specs (list spec spec)))
     "duplicate contradiction specification IDs fail before use"))

  ;; The systemd teaching constraint is keyed by unit AND observation epoch.
  ;; Same unit + same epoch + incompatible high-level states is contradictory.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed
           (test-fact "assume.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (truth (make-truth-maintained-network
                 (make-engine :facts (list active))))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec)))))
    (assumption-network-assert-assumption network failed)
    (assumption-check-equal :evidence
                            (assumption-network-support-kind
                             network "obs.api.active.e42")
                            "seeded base observation is ordinary evidence")
    (assumption-check-equal :assumption
                            (assumption-network-support-kind
                             network "assume.api.failed.e42")
                            "explicit assumption is distinguished from evidence")
    (let ((reports (assumption-network-contradictions network)))
      (assumption-check-equal 1 (length reports)
                              "same-epoch ActiveState conflict is detected")
      (let ((report (first reports)))
        (assumption-check-equal
         "constraint.systemd.active-state.active-vs-failed"
         (contradiction-report-spec-id report)
         "report preserves stable consistency-rule identity")
        (assumption-check-equal
         '((?unit . api-service) (?epoch . 42))
         (contradiction-report-bindings report)
         "shared variables identify the contradictory unit and epoch")
        (assumption-check-equal :evidence
                                (contradiction-report-left-support-kind report)
                                "report preserves evidence side")
        (assumption-check-equal :assumption
                                (contradiction-report-right-support-kind report)
                                "report preserves assumption side as counterevidence")))
    (assumption-check-equal :contradictory
                            (assumption-network-consistency-status network)
                            "current counterevidence makes consistency explicit"))

  ;; Two observations can disagree across time without being logically
  ;; simultaneous. Carrying ?EPOCH across both patterns prevents that false hit.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed-later
           (test-fact "obs.api.failed.e43"
                      'unit-active-state '(api-service failed 43)))
         (truth (make-truth-maintained-network
                 (make-engine :facts (list active failed-later))))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec)))))
    (assumption-check-equal '()
                            (assumption-network-contradictions network)
                            "different observation epochs are not collapsed")
    (assumption-check-equal :consistent
                            (assumption-network-consistency-status network)
                            "temporal separation preserves consistency"))

  ;; Withdrawing an unsupported assumption removes only that side; the engine
  ;; does not touch the independent counterevidence.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed
           (test-fact "assume.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (engine (make-engine :facts (list active)))
         (truth (make-truth-maintained-network engine))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec)))))
    (assumption-network-assert-assumption network failed)
    (let ((report
            (assumption-network-withdraw-assumption
             network "assume.api.failed.e42")))
      (assumption-check-true
       (retraction-report-base-support-removed-p report)
       "assumption withdrawal removes its base-support source")
      (assumption-check-true
       (retraction-report-requested-occurrence-removed-p report)
       "unsupported assumption occurrence leaves working memory")
      (assumption-check-false
       (find-wm-entry (engine-working-memory engine) "assume.api.failed.e42")
       "withdrawn unsupported assumption is absent")
      (assumption-check-true
       (find-wm-entry (engine-working-memory engine) "obs.api.active.e42")
       "counterevidence is preserved")
      (assumption-check-equal :consistent
                              (assumption-network-consistency-status network)
                              "withdrawing one unsupported side clears conflict")))

  ;; An assumption is a support source, not an instruction to delete a fact.
  ;; If a separate derived reason grounds the same occurrence, assumption
  ;; withdrawal demotes it to derived and the contradiction remains visible.
  (let* ((seed (test-fact "base.seed" 'seed '(on)))
         (failed (test-fact "obs.api.failed.e42"
                            'unit-active-state '(api-service failed 42)))
         (active-assumption
           (test-fact "state.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (derive-active
           (assumption-derived-production
            "rule.seed-active" '((seed on))
            "state.api.active.e42" 'unit-active-state
            '(api-service active 42)))
         (engine (make-engine :facts (list seed failed)
                              :productions (list derive-active)))
         (truth (make-truth-maintained-network engine))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec)))))
    (assumption-network-assert-assumption network active-assumption)
    (run-assumption-network network
                            :firing-limit 10
                            :contradiction-policy :report-only)
    (assumption-check-equal 1
                            (length (current-justifications-for
                                     truth "state.api.active.e42"))
                            "assumed occurrence acquires independent derived reason")
    (let ((old-stamp
            (current-stamp-for-fact-id truth "state.api.active.e42"))
          (withdrawal
            (assumption-network-withdraw-assumption
             network "state.api.active.e42")))
      (assumption-check-false
       (retraction-report-requested-occurrence-removed-p withdrawal)
       "grounded derived reason retains occurrence after assumption withdrawal")
      (assumption-check-equal old-stamp
                              (current-stamp-for-fact-id
                               truth "state.api.active.e42")
                              "support demotion preserves exact occurrence identity")
      (assumption-check-equal :derived
                              (assumption-network-support-kind
                               network "state.api.active.e42")
                              "retained occurrence is no longer classified assumed")
      (assumption-check-equal :contradictory
                              (assumption-network-consistency-status network)
                              "counterevidence remains contradictory after demotion"))
    (truth-maintained-retract-base-fact truth "base.seed")
    (assumption-check-false
     (find-wm-entry (engine-working-memory engine) "state.api.active.e42")
     "losing final derived grounding retracts former assumption")
    (assumption-check-equal :consistent
                            (assumption-network-consistency-status network)
                            "contradiction clears only after occurrence disappears"))

  ;; :HALT is a consistency gate: an already-contradictory state prevents the
  ;; next eligible production from firing, but preserves both observations.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed
           (test-fact "obs.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (consume
           (assumption-derived-production
            "rule.consume-active"
            '((unit-active-state api-service active 42))
            "derived.consumed" 'consumed '(yes)))
         (engine (make-engine :facts (list active failed)
                              :productions (list consume)))
         (truth (make-truth-maintained-network engine))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec))))
         (result (run-assumption-network network :firing-limit 10)))
    (assumption-check-equal :contradiction
                            (consistency-run-result-status result)
                            "halt policy stops on current contradiction")
    (assumption-check-equal 0
                            (consistency-run-result-firing-count result)
                            "halt policy fires nothing from inconsistent state")
    (assumption-check-equal 1
                            (length
                             (consistency-run-result-remaining-activation-keys
                              result))
                            "eligible activation remains inspectable after halt")
    (assumption-check-false
     (find-wm-entry (engine-working-memory engine) "derived.consumed")
     "halt policy does not consume contradictory state"))

  ;; :REPORT-ONLY keeps the contradiction visible while allowing an inspection
  ;; run to continue. It is deliberately not a resolution strategy.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed
           (test-fact "obs.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (consume
           (assumption-derived-production
            "rule.consume-active.report-only"
            '((unit-active-state api-service active 42))
            "derived.report-only" 'inspection '(complete)))
         (engine (make-engine :facts (list active failed)
                              :productions (list consume)))
         (truth (make-truth-maintained-network engine))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec))))
         (result
           (run-assumption-network network
                                   :firing-limit 10
                                   :contradiction-policy :report-only)))
    (assumption-check-equal :quiescent
                            (consistency-run-result-status result)
                            "report-only mode can run to ordinary quiescence")
    (assumption-check-equal 1
                            (consistency-run-result-firing-count result)
                            "report-only mode executes eligible production")
    (assumption-check-equal 1
                            (length
                             (consistency-run-result-contradictions result))
                            "report-only result still carries counterevidence")
    (assumption-check-true
     (find-wm-entry (engine-working-memory engine) "derived.report-only")
     "report-only mode leaves an explicit audit trail of continued reasoning"))

  ;; The halt check runs before EACH next firing. Here the first firing creates
  ;; a contradiction and the second newly enabled firing is held on the agenda.
  (let* ((seed (test-fact "seed.active" 'seed '(on)))
         (failed
           (test-fact "obs.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (derive-active
           (assumption-derived-production
            "rule.derive-active" '((seed on))
            "derived.api.active.e42" 'unit-active-state
            '(api-service active 42)))
         (consume-active
           (assumption-derived-production
            "rule.consume-derived-active"
            '((unit-active-state api-service active 42))
            "derived.after-conflict" 'unsafe-next-step '(blocked)))
         (engine
           (make-engine :facts (list seed failed)
                        :productions (list derive-active consume-active)))
         (truth (make-truth-maintained-network engine))
         (network
           (make-assumption-network
            truth :contradiction-specs (list (active-vs-failed-spec))))
         (result (run-assumption-network network :firing-limit 10)))
    (assumption-check-equal :contradiction
                            (consistency-run-result-status result)
                            "derived contradiction halts before next firing")
    (assumption-check-equal 1
                            (consistency-run-result-firing-count result)
                            "only contradiction-producing firing commits")
    (assumption-check-true
     (find-wm-entry (engine-working-memory engine) "derived.api.active.e42")
     "contradictory derived fact remains available as counterevidence")
    (assumption-check-false
     (find-wm-entry (engine-working-memory engine) "derived.after-conflict")
     "newly enabled downstream action is blocked by consistency gate")
    (assumption-check-equal 1
                            (length
                             (consistency-run-result-remaining-activation-keys
                              result))
                            "blocked downstream activation remains inspectable"))

  (format t "~&PASS: ~D assumption/contradiction checks~%"
          *assumption-tests-run*)
  t)

(run-assumption-tests)
