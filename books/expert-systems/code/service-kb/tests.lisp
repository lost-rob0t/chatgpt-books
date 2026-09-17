(in-package #:expert-systems.service-kb)

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
    (error "FAIL service-kb ~A: expected ~S, got ~S" label expected actual)))

(defun current-fact-by-id (network fact-id)
  (let* ((memory (assumption-network-working-memory network))
         (entry (find-wm-entry memory fact-id)))
    (and entry (wm-entry-fact entry))))

(defun graph-node-by-kind (graph kind)
  (find kind (explanation-graph-nodes graph)
        :key #'explanation-node-kind :test #'eq))

(defun graph-justification-by-rule (graph rule-id)
  (find-if
   (lambda (node)
     (and (eq (explanation-node-kind node) :justification)
          (equal rule-id
                 (getf (explanation-node-data node) :production-id))))
   (explanation-graph-nodes graph)))

(defun run-service-kb-tests ()
  (setf *service-kb-tests-run* 0)

  ;; Requires + After + same-attempt failed dependency yields the bounded
  ;; startup-blocked diagnostic hypothesis documented by systemd.unit v261.3.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case (make-systemd-dependency-fixture))
    (service-kb-check-equal :quiescent
                            (consistency-run-result-status result)
                            "required-after scenario reaches quiescence")
    (let* ((id (required-dependency-hypothesis-id
                "frontend.service" "api.service"
                "attempt-1" "generation-1"))
           (fact (current-fact-by-id network id))
           (graph (explain-current-fact network id))
           (justification
             (graph-justification-by-rule
              graph "rule.systemd.requires-after-failed-dependency")))
      (service-kb-check-true fact
                             "required-after failure derives a hypothesis")
      (service-kb-check-equal
       '(:required-dependency-blocked-startup
         "frontend.service" "api.service" "attempt-1" "generation-1")
       (fact-arguments fact)
       "hypothesis retains exact attempt and generation identity")
      (service-kb-check-equal :grounded
                              (explanation-graph-status graph)
                              "derived hypothesis is grounded")
      (service-kb-check-true justification
                             "explanation includes source-backed rule")
      (service-kb-check-equal
       "v261.3"
       (getf (getf (explanation-node-data justification)
                   :production-provenance)
             :release)
       "rule provenance pins systemd release")
      (service-kb-check-equal
       :requires-plus-after-and-failed-required-unit-prevents-dependent-start
       (getf (getf (explanation-node-data justification)
                   :production-provenance)
             :documented-claim)
       "rule provenance names the documented claim")
      (let ((source (graph-node-by-kind graph :source)))
        (service-kb-check-equal
         :synthetic-configuration
         (getf (getf (explanation-node-data source) :provenance) :kind)
         "explanation keeps synthetic observation provenance distinct"))))

  ;; Requires= does not imply ordering. Without After=, the bounded diagnostic
  ;; rule must not fire merely because the dependency failed.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture :include-ordering nil))
    (declare (ignore result))
    (let ((graph
            (explain-required-dependency-hypothesis
             network "frontend.service" "api.service"
             "attempt-1" "generation-1")))
      (service-kb-check-equal :absent
                              (explanation-graph-status graph)
                              "requires without after proves no startup order")))

  ;; After= orders units that are in the transaction; it does not pull the
  ;; listed unit into the transaction by itself.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture :include-requirement nil))
    (declare (ignore result))
    (let ((graph
            (explain-required-dependency-hypothesis
             network "frontend.service" "api.service"
             "attempt-1" "generation-1")))
      (service-kb-check-equal :absent
                              (explanation-graph-status graph)
                              "after without requirement proves no pull-in")))

  ;; Wants= is deliberately a different relation value. A wanted dependency
  ;; failure yields an inspectable boundary note, not the blocked-startup
  ;; hypothesis used for Requires= + After=.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture :requirement-kind :wants))
    (declare (ignore result))
    (let* ((hypothesis
             (explain-required-dependency-hypothesis
              network "frontend.service" "api.service"
              "attempt-1" "generation-1"))
           (boundary-id
             (wanted-dependency-boundary-id
              "frontend.service" "api.service"
              "attempt-1" "generation-1"))
           (boundary (current-fact-by-id network boundary-id))
           (boundary-graph (explain-current-fact network boundary-id)))
      (service-kb-check-equal :absent
                              (explanation-graph-status hypothesis)
                              "wants failure is not a requires diagnosis")
      (service-kb-check-true boundary
                             "wants failure keeps an explicit boundary fact")
      (service-kb-check-equal :grounded
                              (explanation-graph-status boundary-graph)
                              "wants boundary note is explainable")))

  ;; Configuration generations are part of the join key. Stale configuration
  ;; evidence must not combine with a newer activation observation.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture
        :requirement-generation "generation-0"
        :ordering-generation "generation-0"
        :attempt-generation "generation-1"
        :outcome-generation "generation-1"))
    (declare (ignore result))
    (service-kb-check-equal
     :absent
     (explanation-graph-status
      (explain-required-dependency-hypothesis
       network "frontend.service" "api.service"
       "attempt-1" "generation-1"))
     "cross-generation evidence does not join"))

  ;; Activation attempts are also explicit identity. A failure from a previous
  ;; attempt cannot be borrowed into the current attempt.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture
        :outcome-attempt "attempt-0"))
    (declare (ignore result))
    (service-kb-check-equal
     :absent
     (explanation-graph-status
      (explain-required-dependency-hypothesis
       network "frontend.service" "api.service"
       "attempt-1" "generation-1"))
     "cross-attempt evidence does not join"))

  ;; A non-failed dependency outcome does not satisfy the documented failure
  ;; condition. This is absence of this diagnosis, not proof of service health.
  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (make-systemd-dependency-fixture :dependency-outcome :active))
    (declare (ignore result))
    (service-kb-check-equal
     :absent
     (explanation-graph-status
      (explain-required-dependency-hypothesis
       network "frontend.service" "api.service"
       "attempt-1" "generation-1"))
     "nonfailed dependency does not trigger failure diagnosis"))

  (format t "PASS: ~D source-backed systemd service-KB checks~%"
          *service-kb-tests-run*)
  t)

(run-service-kb-tests)
