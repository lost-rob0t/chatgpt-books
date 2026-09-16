(in-package #:expert-systems.matcher)

(defvar *truth-maintenance-tests-run* 0)

(defun truth-check-true (value label)
  (incf *truth-maintenance-tests-run*)
  (unless value
    (error "FAIL truth-maintenance ~A: expected true, got ~S" label value)))

(defun truth-check-false (value label)
  (incf *truth-maintenance-tests-run*)
  (when value
    (error "FAIL truth-maintenance ~A: expected false, got ~S" label value)))

(defun truth-check-equal (expected actual label)
  (incf *truth-maintenance-tests-run*)
  (unless (equal expected actual)
    (error "FAIL truth-maintenance ~A: expected ~S, got ~S"
           label expected actual)))

(defun truth-check-signals-content-conflict (thunk label)
  (incf *truth-maintenance-tests-run*)
  (handler-case
      (progn
        (funcall thunk)
        (error "FAIL truth-maintenance ~A: expected FACT-ID-CONTENT-CONFLICT"
               label))
    (fact-id-content-conflict () t)))

(defun constant-derived-production (id conditions fact-id relation arguments)
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

(defun run-truth-maintenance-tests ()
  (setf *truth-maintenance-tests-run* 0)

  ;; Construction classifies the exact seeded occurrences as base evidence.
  (let* ((seed (test-fact "base.seed" 'seed '(ready)))
         (engine (make-engine :facts (list seed)))
         (truth (make-truth-maintained-network engine))
         (report (truth-maintained-support-report truth "base.seed")))
    (truth-check-equal :base (support-report-status report)
                       "seeded fact reports base status")
    (truth-check-true (support-report-present-p report)
                      "seeded base fact is present")
    (truth-check-true (support-report-base-supported-p report)
                      "seeded base fact has unconditional course support")
    (truth-check-true (support-report-grounded-p report)
                      "base fact is grounded without a derived reason")
    (truth-check-equal '(("base.seed" . 1))
                       (truth-maintained-network-base-support-stamps truth)
                       "base support records exact occurrence identity"))

  ;; The existing service chain is the first substantial truth-maintenance
  ;; scenario: two derived facts, a transitive dependency, and a cascade.
  (let* ((engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (truth (make-truth-maintained-network engine))
         (result (truth-maintained-run-engine truth :firing-limit 10))
         (impact-id "derived.dependency-impact.frontend.api")
         (investigate-id "derived.needs-investigation.frontend")
         (impact-reasons
           (truth-maintained-justifications-for truth impact-id))
         (impact-report
           (truth-maintained-support-report truth impact-id)))
    (truth-check-equal :quiescent (run-result-status result)
                       "truth-maintained service run reaches quiescence")
    (truth-check-equal 2 (run-result-firing-count result)
                       "service run still fires the accepted two-rule chain")
    (truth-check-equal 1 (length impact-reasons)
                       "first derived fact records one justification")
    (truth-check-equal
     '(("obs.api.state.failed" . 1) ("dep.frontend.api" . 4))
     (justification-support-stamps (first impact-reasons))
     "justification records exact condition-ordered support occurrences")
    (truth-check-equal "rule.dependency-impact"
                       (justification-production-id (first impact-reasons))
                       "justification records stable production identity")
    (truth-check-equal :derived (support-report-status impact-report)
                       "derived fact reports derived status")
    (truth-check-false (support-report-base-supported-p impact-report)
                       "derived fact is not mislabeled as base evidence")
    (truth-check-true (support-report-grounded-p impact-report)
                      "derived service fact is grounded before retraction")
    (truth-check-equal (list impact-id)
                       (truth-maintained-current-dependents
                        truth "obs.api.state.failed")
                       "dependency query exposes direct conclusion")
    (truth-check-equal (list investigate-id)
                       (truth-maintained-current-dependents truth impact-id)
                       "dependency query exposes transitive next edge")
    (let ((retraction
            (truth-maintained-retract-base-fact
             truth "obs.api.state.failed")))
      (truth-check-true
       (retraction-report-base-support-removed-p retraction)
       "base observation support classification is removed")
      (truth-check-true
       (retraction-report-requested-occurrence-removed-p retraction)
       "unsupported base observation occurrence is retracted")
      (truth-check-equal (list impact-id investigate-id)
                         (retraction-report-cascaded-fact-ids retraction)
                         "lost support cascades through both derived facts")
      (truth-check-false
       (find-wm-entry (engine-working-memory engine) impact-id)
       "first unsupported conclusion leaves working memory")
      (truth-check-false
       (find-wm-entry (engine-working-memory engine) investigate-id)
       "downstream unsupported conclusion leaves working memory")
      (truth-check-true
       (incremental-cache-references-current-p
        (truth-maintained-network-incremental-network truth))
       "truth-maintenance cascade leaves matcher caches reference-sound")))

  ;; Multiple justifications are OR alternatives: removing one support group
  ;; must not retract a conclusion that still has another grounded reason.
  (let* ((left (test-fact "support.left" 'support '(left)))
         (right (test-fact "support.right" 'support '(right)))
         (left-rule
           (constant-derived-production
            "rule.left" '((support left)) "derived.shared" 'conclusion '(ready)))
         (right-rule
           (constant-derived-production
            "rule.right" '((support right)) "derived.shared" 'conclusion '(ready)))
         (engine (make-engine :facts (list left right)
                              :productions (list left-rule right-rule)))
         (truth (make-truth-maintained-network engine)))
    (truth-maintained-run-engine truth :firing-limit 10)
    (truth-check-equal 1
                       (count "derived.shared"
                              (mapcar #'fact-id
                                      (working-memory-facts
                                       (engine-working-memory engine)))
                              :test #'equal)
                       "two reasons materialize one working-memory fact")
    (truth-check-equal 2
                       (length (current-justifications-for
                                truth "derived.shared"))
                       "shared conclusion records both independent reasons")
    (let ((left-retraction
            (truth-maintained-retract-base-fact truth "support.left")))
      (truth-check-equal '()
                         (retraction-report-cascaded-fact-ids left-retraction)
                         "removing one alternative support does not retract conclusion")
      (truth-check-true
       (truth-maintained-fact-grounded-p truth "derived.shared")
       "remaining independent reason keeps conclusion grounded"))
    (let ((right-retraction
            (truth-maintained-retract-base-fact truth "support.right")))
      (truth-check-equal '("derived.shared")
                         (retraction-report-cascaded-fact-ids right-retraction)
                         "last grounded reason removal retracts shared conclusion")
      (truth-check-false
       (find-wm-entry (engine-working-memory engine) "derived.shared")
       "shared conclusion disappears after its last support")))

  ;; Base support and a derived justification are independent support sources.
  ;; Removing only the base classification must preserve the same current
  ;; occurrence when another grounded reason exists, including its dependents.
  (let* ((x (test-fact "mixed.x" 'state '(ready)))
         (y (test-fact "mixed.y" 'support '(on)))
         (y-to-x
           (constant-derived-production
            "rule.mixed-y-to-x" '((support on))
            "mixed.x" 'state '(ready)))
         (x-to-z
           (constant-derived-production
            "rule.mixed-x-to-z" '((state ready))
            "mixed.z" 'dependent '(present)))
         (engine (make-engine :facts (list x y)
                              :productions (list y-to-x x-to-z)))
         (truth (make-truth-maintained-network engine)))
    (truth-maintained-run-engine truth :firing-limit 10)
    (let ((x-stamp (current-stamp-for-fact-id truth "mixed.x")))
      (truth-check-equal 1
                         (length (current-justifications-for truth "mixed.x"))
                         "base X also records the independent Y-derived reason")
      (truth-check-equal '("mixed.z")
                         (truth-maintained-current-dependents truth "mixed.x")
                         "X has a current downstream dependent before base removal")
      (let ((x-retraction
              (truth-maintained-retract-base-fact truth "mixed.x")))
        (truth-check-true
         (retraction-report-base-support-removed-p x-retraction)
         "mixed-support retraction removes X base support")
        (truth-check-false
         (retraction-report-requested-occurrence-removed-p x-retraction)
         "grounded derived reason keeps X occurrence in working memory")
        (truth-check-equal '()
                           (retraction-report-removed-occurrence-stamps
                            x-retraction)
                           "retaining X reports no removed working-memory stamp")
        (truth-check-equal x-stamp
                           (current-stamp-for-fact-id truth "mixed.x")
                           "mixed-support X retains the exact same occurrence")
        (let ((x-report
                (truth-maintained-support-report truth "mixed.x")))
          (truth-check-equal :derived (support-report-status x-report)
                             "retained X becomes derived after base support removal")
          (truth-check-false (support-report-base-supported-p x-report)
                             "retained X is no longer base-supported")
          (truth-check-true (support-report-grounded-p x-report)
                            "retained X remains grounded through Y"))
        (truth-check-true
         (not (null (find-wm-entry (engine-working-memory engine) "mixed.z")))
         "downstream Z remains present while X occurrence remains")
        (truth-check-equal '("mixed.z")
                           (truth-maintained-current-dependents truth "mixed.x")
                           "retained X keeps its downstream dependency edge"))
      (let ((y-retraction
              (truth-maintained-retract-base-fact truth "mixed.y")))
        (truth-check-true
         (retraction-report-requested-occurrence-removed-p y-retraction)
         "removing final base Y occurrence starts mixed-support cascade")
        (truth-check-equal '("mixed.x" "mixed.z")
                           (retraction-report-cascaded-fact-ids y-retraction)
                           "losing Y later retracts X and cascades to Z")
        (truth-check-false
         (find-wm-entry (engine-working-memory engine) "mixed.x")
         "X leaves working memory after its last grounding path disappears")
        (truth-check-false
         (find-wm-entry (engine-working-memory engine) "mixed.z")
         "Z leaves working memory after X disappears"))))

  ;; Failure lab: a cycle of derived facts cannot become its own foundation.
  (let* ((seed (test-fact "cycle.seed" 'seed '(on)))
         (seed-a
           (constant-derived-production
            "rule.seed-a" '((seed on)) "cycle.a" 'node '(a)))
         (a-b
           (constant-derived-production
            "rule.a-b" '((node a)) "cycle.b" 'node '(b)))
         (b-a
           (constant-derived-production
            "rule.b-a" '((node b)) "cycle.a" 'node '(a)))
         (engine (make-engine :facts (list seed)
                              :productions (list seed-a a-b b-a)))
         (truth (make-truth-maintained-network engine)))
    (truth-maintained-run-engine truth :firing-limit 10)
    (truth-check-equal 2
                       (length (current-justifications-for truth "cycle.a"))
                       "cycle A has seed and cyclic reasons before seed removal")
    (truth-check-true (truth-maintained-fact-grounded-p truth "cycle.a")
                      "base path grounds A before retraction")
    (let ((retraction
            (truth-maintained-retract-base-fact truth "cycle.seed")))
      (truth-check-equal '("cycle.a" "cycle.b")
                         (retraction-report-cascaded-fact-ids retraction)
                         "unsupported A/B cycle collapses after seed removal")
      (truth-check-false (truth-maintained-fact-grounded-p truth "cycle.a")
                         "absent cycle A is no longer grounded")
      (truth-check-false (truth-maintained-fact-grounded-p truth "cycle.b")
                         "absent cycle B is no longer grounded")))

  ;; Stable IDs do not make old reasons current. Reasserting the same base ID
  ;; creates a new occurrence; only a fresh firing can establish a fresh reason.
  (let* ((seed (test-fact "reassert.seed" 'seed '(on)))
         (rule
           (constant-derived-production
            "rule.seed-result" '((seed on))
            "reassert.result" 'result '(ready)))
         (engine (make-engine :facts (list seed)
                              :productions (list rule)))
         (truth (make-truth-maintained-network engine)))
    (truth-maintained-run-engine truth :firing-limit 10)
    (let ((old-reason
            (first (truth-maintained-justifications-for
                    truth "reassert.result"))))
      (truth-check-equal '(("reassert.seed" . 1))
                         (justification-support-stamps old-reason)
                         "first reason records original base occurrence")
      (truth-maintained-retract-base-fact truth "reassert.seed")
      (let ((new-entry (truth-maintained-assert-base-fact truth seed)))
        (truth-check-equal 3 (wm-entry-sequence new-entry)
                           "same stable base ID reasserts as a new occurrence")
        (truth-check-false
         (justification-supports-current-p truth old-reason)
         "old reason does not attach to new same-ID base occurrence"))
      (truth-maintained-run-engine truth :firing-limit 10)
      (let ((current-reasons
              (current-justifications-for truth "reassert.result")))
        (truth-check-equal 1 (length current-reasons)
                           "rederived occurrence has one current reason")
        (truth-check-equal '(("reassert.seed" . 3))
                           (justification-support-stamps
                            (first current-reasons))
                           "fresh firing records fresh support occurrence")
        (truth-check-equal 2
                           (length (truth-maintained-justifications-for
                                    truth "reassert.result"))
                           "historical reason remains available without grounding new occurrence"))))

  ;; Stable IDs guard logical content. A production cannot silently replace a
  ;; current fact with different content under the same ID, and the failure
  ;; happens before every normal engine/TMS mutation layer.
  (let* ((seed (test-fact "conflict.seed" 'seed '(on)))
         (bad-rule
           (constant-derived-production
            "rule.conflict" '((seed on))
            "conflict.seed" 'different '(content)))
         (engine (make-engine :facts (list seed)
                              :productions (list bad-rule)))
         (truth (make-truth-maintained-network engine))
         (activation
           (first (incremental-agenda
                   (truth-maintained-network-incremental-network truth))))
         (before-facts
           (mapcar #'fact-id
                   (working-memory-facts (engine-working-memory engine))))
         (before-state (truth-maintained-network-snapshot truth)))
    (truth-check-signals-content-conflict
     (lambda () (truth-maintained-fire-activation truth activation))
     "same stable ID with different content is rejected")
    (truth-check-equal before-facts
                       (mapcar #'fact-id
                               (working-memory-facts
                                (engine-working-memory engine)))
                       "content conflict leaves working memory unchanged")
    (truth-check-equal '() (engine-firing-records engine)
                       "content conflict appends no firing record")
    (truth-check-equal '() (engine-refracted-keys engine)
                       "content conflict does not refract activation")
    (truth-check-equal before-state (truth-maintained-network-snapshot truth)
                       "content conflict leaves support and cache state unchanged"))

  ;; Explanation-facing reports intentionally distinguish absence from derived
  ;; and base support without claiming Chapter 20's full narrative explanation.
  (let* ((seed (test-fact "report.seed" 'seed '(on)))
         (rule
           (constant-derived-production
            "rule.report" '((seed on)) "report.derived" 'result '(ready)))
         (engine (make-engine :facts (list seed)
                              :productions (list rule)))
         (truth (make-truth-maintained-network engine)))
    (truth-maintained-run-engine truth :firing-limit 10)
    (let ((base (truth-maintained-support-report truth "report.seed"))
          (derived (truth-maintained-support-report truth "report.derived"))
          (absent (truth-maintained-support-report truth "report.missing")))
      (truth-check-equal :base (support-report-status base)
                         "support report identifies base evidence")
      (truth-check-equal :derived (support-report-status derived)
                         "support report identifies derived evidence")
      (truth-check-true (support-report-grounded-p derived)
                        "support report exposes grounded derived fact")
      (truth-check-equal 1
                         (length (support-report-current-justification-ids
                                  derived))
                         "derived support report exposes current reason identity")
      (truth-check-equal :absent (support-report-status absent)
                         "support report distinguishes absent fact")
      (truth-check-false (support-report-present-p absent)
                         "absent support report is not marked present")))

  (format t "~&PASS: ~D truth-maintenance checks~%"
          *truth-maintenance-tests-run*)
  t)

(run-truth-maintenance-tests)
