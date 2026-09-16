(in-package #:expert-systems.matcher)

(defvar *service-kb-tests-run* 0)

(defun service-kb-check-true (value label)
  (incf *service-kb-tests-run*)
  (unless value
    (error "FAIL service-kb ~A: expected true, got ~S" label value)))

(defun service-kb-check-false (value label)
  (incf *service-kb-tests-run*)
  (when value
    (error "FAIL service-kb ~A: expected false, got ~S" label value)))

(defun service-kb-check-equal (expected actual label)
  (incf *service-kb-tests-run*)
  (unless (equal expected actual)
    (error "FAIL service-kb ~A: expected ~S, got ~S"
           label expected actual)))

(defun service-kb-current-fact (network fact-id)
  (let ((entry
          (find-wm-entry (assumption-network-working-memory network) fact-id)))
    (and entry (wm-entry-fact entry))))

(defun service-kb-diagnosis-id ()
  (systemd-diagnosis-fact-id 'frontend 'api 'attempt-17 'config-3))

(defun service-kb-base-facts (&key
                                (requirement-kind 'requires)
                                (include-requirement t)
                                (include-ordering t)
                                (request-attempt 'attempt-17)
                                (failure-attempt 'attempt-17)
                                (request-config 'config-3)
                                (dependency-config 'config-3)
                                (failure-config 'config-3))
  (append
   (list
    (make-systemd-start-request-fact
     "obs.frontend.start" 'frontend request-attempt request-config))
   (when include-requirement
     (list
      (make-systemd-requirement-fact
       "cfg.frontend.requirement.api"
       'frontend 'api requirement-kind dependency-config)))
   (when include-ordering
     (list
      (make-systemd-ordering-fact
       "cfg.frontend.after.api" 'frontend 'api 'after dependency-config)))
   (list
    (make-systemd-activation-fact
     "obs.api.failed" 'api 'failed failure-attempt failure-config))))

(defun service-kb-run-with (facts)
  (let ((network (make-systemd-dependency-kb facts)))
    (values network (run-assumption-network network))))

(defun service-kb-justification-node (graph production-id)
  (find-if
   (lambda (node)
     (and (eq (explanation-node-kind node) :justification)
          (equal (getf (explanation-node-data node) :production-id)
                 production-id)))
   (explanation-graph-nodes graph)))

(defun run-service-kb-tests ()
  (setf *service-kb-tests-run* 0)

  ;; The happy path requires four explicit supports from one modeled attempt.
  (multiple-value-bind (network result)
      (service-kb-run-with (make-systemd-dependency-fixture))
    (service-kb-check-equal :quiescent
                            (consistency-run-result-status result)
                            "source-backed fixture reaches quiescence")
    (let* ((id (service-kb-diagnosis-id))
           (diagnosis (service-kb-current-fact network id)))
      (service-kb-check-true diagnosis
                             "requires+after+failed dependency derives diagnosis")
      (service-kb-check-equal
       '(frontend api attempt-17 config-3)
       (fact-arguments diagnosis)
       "diagnosis keeps service dependency attempt and config identity")
      (service-kb-check-equal
       "rule.systemd.required-after-failure"
       (getf (fact-provenance diagnosis) :rule-id)
       "derived hypothesis keeps stable rule identity")
      (service-kb-check-equal
       "systemd.unit.requires-after-failure"
       (getf (fact-provenance diagnosis) :source-id)
       "derived hypothesis keeps source identity")
      (let* ((graph (explain-current-fact network id))
             (justification
               (service-kb-justification-node
                graph "rule.systemd.required-after-failure")))
        (service-kb-check-equal :grounded
                                (explanation-graph-status graph)
                                "diagnosis explanation is currently grounded")
        (service-kb-check-true justification
                               "explanation exposes rule justification")
        (service-kb-check-equal
         "systemd.unit.requires-after-failure"
         (getf (getf (explanation-node-data justification)
                     :production-provenance)
               :source-id)
         "explanation preserves production source provenance")
        (service-kb-check-equal
         4
         (count :source (explanation-graph-nodes graph)
                :key #'explanation-node-kind :test #'eq)
         "explanation exposes all four base support sources")
        (service-kb-check-equal
         (explanation-graph-signature graph)
         (explanation-graph-signature (explain-current-fact network id))
         "unchanged diagnosis explanation is deterministic"))))

  ;; Requirement and ordering are orthogonal. Neither alone is enough.
  (multiple-value-bind (network result)
      (service-kb-run-with
       (service-kb-base-facts :include-ordering nil))
    (declare (ignore result))
    (service-kb-check-false
     (service-kb-current-fact network (service-kb-diagnosis-id))
     "requires without after does not invent ordering diagnosis"))

  (multiple-value-bind (network result)
      (service-kb-run-with
       (service-kb-base-facts :include-requirement nil))
    (declare (ignore result))
    (service-kb-check-false
     (service-kb-current-fact network (service-kb-diagnosis-id))
     "after without requires does not invent requirement diagnosis"))

  ;; Wants= is intentionally not promoted into Requires= semantics.
  (multiple-value-bind (network result)
      (service-kb-run-with
       (service-kb-base-facts :requirement-kind 'wants))
    (declare (ignore result))
    (service-kb-check-false
     (service-kb-current-fact network (service-kb-diagnosis-id))
     "wanted dependency failure does not invalidate transaction by this rule"))

  ;; Evidence from a different modeled start attempt must not join.
  (multiple-value-bind (network result)
      (service-kb-run-with
       (service-kb-base-facts :failure-attempt 'attempt-18))
    (declare (ignore result))
    (service-kb-check-false
     (service-kb-current-fact network (service-kb-diagnosis-id))
     "different attempt does not join into current diagnosis"))

  ;; Configuration generation is part of the consistency/join key too.
  (multiple-value-bind (network result)
      (service-kb-run-with
       (service-kb-base-facts :failure-config 'config-4))
    (declare (ignore result))
    (service-kb-check-false
     (service-kb-current-fact network (service-kb-diagnosis-id))
     "different config generation does not join into current diagnosis"))

  ;; Input constructors reject unsupported dependency vocabulary instead of
  ;; silently broadening the documented model.
  (handler-case
      (progn
        (make-systemd-requirement-fact
         "bad.requirement" 'frontend 'api 'binds-to 'config-3)
        (service-kb-check-true nil
                               "unsupported requirement kind must signal"))
    (error ()
      (service-kb-check-true t
                             "unsupported requirement kind signals")))

  (handler-case
      (progn
        (make-systemd-ordering-fact
         "bad.ordering" 'frontend 'api 'requires 'config-3)
        (service-kb-check-true nil
                               "unsupported ordering relation must signal"))
    (error ()
      (service-kb-check-true t
                             "unsupported ordering relation signals")))

  (format t "PASS: ~D service KB checks~%" *service-kb-tests-run*))

(run-service-kb-tests)
