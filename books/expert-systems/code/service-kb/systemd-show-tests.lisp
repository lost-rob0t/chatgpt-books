(in-package #:expert-systems.service-kb)

(defvar *systemd-show-tests-run* 0)

(defun show-check-true (value label)
  (incf *systemd-show-tests-run*)
  (unless value
    (error "FAIL systemd-show ~A: expected true, got ~S" label value)))

(defun show-check-false (value label)
  (incf *systemd-show-tests-run*)
  (when value
    (error "FAIL systemd-show ~A: expected false, got ~S" label value)))

(defun show-check-equal (expected actual label)
  (incf *systemd-show-tests-run*)
  (unless (equal expected actual)
    (error "FAIL systemd-show ~A: expected ~S, got ~S"
           label expected actual)))

(defun show-check-condition (condition-type thunk label)
  (incf *systemd-show-tests-run*)
  (handler-case
      (progn
        (funcall thunk)
        (error "FAIL systemd-show ~A: expected condition ~S"
               label condition-type))
    (condition (caught)
      (unless (typep caught condition-type)
        (error "FAIL systemd-show ~A: expected ~S, got ~S"
               label condition-type (type-of caught))))))

(defun fact-with-relation (facts relation)
  (find relation facts :key #'fact-relation :test #'eq))

(defun source-node-with-provenance-kind (graph kind)
  (find-if
   (lambda (node)
     (and (eq (explanation-node-kind node) :source)
          (eq (getf (getf (explanation-node-data node) :provenance) :kind)
              kind)))
   (explanation-graph-nodes graph)))

(defun failed-show-text (unit invocation-id)
  (format nil
          "Id=~A~%InvocationID=~A~%ActiveState=failed~%SubState=failed~%Result=exit-code~%ExecMainCode=1~%ExecMainStatus=1~%"
          unit invocation-id))

(defun nonfailed-nonzero-show-text (unit invocation-id)
  (format nil
          "Id=~A~%InvocationID=~A~%ActiveState=inactive~%SubState=dead~%Result=success~%ExecMainCode=1~%ExecMainStatus=75~%"
          unit invocation-id))

(defun activating-show-text (unit invocation-id)
  (format nil
          "Id=~A~%InvocationID=~A~%ActiveState=activating~%SubState=start~%Result=success~%ExecMainCode=0~%ExecMainStatus=0~%"
          unit invocation-id))

(defun project-2-configuration-facts (generation)
  (list
   (fixture-fact
    "cfg.e2e.requirement" 'unit-requirement
    (list "frontend.service" "api.service" :requires generation)
    :synthetic-configuration "systemd-show-e2e" "fixture:requires")
   (fixture-fact
    "cfg.e2e.ordering" 'unit-ordering
    (list "frontend.service" "api.service" :after generation)
    :synthetic-configuration "systemd-show-e2e" "fixture:after")))

(defun normalize-e2e-snapshots (&key
                                  (context "activation-context-1")
                                  (generation "generation-1"))
  (append
   (normalize-systemctl-show
    (activating-show-text
     "frontend.service" "11111111111111111111111111111111")
    :expected-unit "frontend.service"
    :activation-context context
    :generation generation
    :capture-id "frontend-capture")
   (normalize-systemctl-show
    (failed-show-text
     "api.service" "22222222222222222222222222222222")
    :expected-unit "api.service"
    :activation-context context
    :generation generation
    :capture-id "api-capture")))

(defun run-systemd-show-tests ()
  (setf *systemd-show-tests-run* 0)

  (let ((properties
          (parse-systemctl-show
           (format nil "Id=api.service~%StatusText=alpha=beta=gamma~%~%"))))
    (show-check-equal "alpha=beta=gamma"
                      (systemctl-show-property properties "StatusText")
                      "parser splits on first equals only")
    (show-check-equal "api.service"
                      (systemctl-show-property properties "Id")
                      "parser preserves property order/content"))

  (show-check-condition
   'systemctl-show-malformed-line
   (lambda () (parse-systemctl-show "not-a-property-line"))
   "malformed line fails closed")

  (show-check-condition
   'systemctl-show-duplicate-property
   (lambda ()
     (parse-systemctl-show
      (format nil "Id=a.service~%Id=b.service~%")))
   "duplicate property fails closed")

  (show-check-condition
   'systemctl-show-missing-property
   (lambda ()
     (normalize-systemctl-show
      "Id=api.service"
      :activation-context "ctx"
      :generation "g"
      :capture-id "missing"))
   "missing requested property is rejected")

  (show-check-condition
   'systemctl-show-empty-property
   (lambda ()
     (normalize-systemctl-show
      (format nil
              "Id=api.service~%InvocationID=~%ActiveState=failed~%SubState=failed~%Result=exit-code~%ExecMainCode=1~%ExecMainStatus=1~%")
      :activation-context "ctx"
      :generation "g"
      :capture-id "empty-invocation"))
   "empty invocation identity is rejected")

  (show-check-condition
   'systemctl-show-unit-mismatch
   (lambda ()
     (normalize-systemctl-show
      (failed-show-text "api.service" "inv-a")
      :expected-unit "frontend.service"
      :activation-context "ctx"
      :generation "g"
      :capture-id "wrong-unit"))
   "expected unit mismatch is rejected")

  (let* ((facts
           (normalize-systemctl-show
            (failed-show-text "api.service" "inv-api")
            :expected-unit "api.service"
            :activation-context "activation-context-1"
            :generation "generation-1"
            :capture-id "api-failed"))
         (invocation (fact-with-relation facts 'unit-invocation))
         (outcome (fact-with-relation facts 'activation-outcome))
         (exit (fact-with-relation facts 'service-main-exit-observation)))
    (show-check-equal
     '("api.service" "inv-api" "activation-context-1" "generation-1")
     (fact-arguments invocation)
     "unit InvocationID is preserved separately from activation context")
    (show-check-equal
     '("api.service" "activation-context-1" "generation-1" :failed)
     (fact-arguments outcome)
     "failed ActiveState maps to bounded activation outcome")
    (show-check-equal
     '("api.service" "1" "1" "inv-api"
       "activation-context-1" "generation-1")
     (fact-arguments exit)
     "main process status remains raw evidence")
    (show-check-equal :synthetic
                      (getf (fact-provenance outcome) :status)
                      "default capture provenance is synthetic")
    (show-check-equal "failed"
                      (cdr (assoc "ActiveState"
                                  (getf (fact-provenance outcome)
                                        :raw-properties)
                                  :test #'equal))
                      "raw source properties survive provenance"))

  ;; SuccessExitStatus= can make a non-zero main-process status successful.
  ;; The normalizer therefore preserves the raw status but does not derive a
  ;; failure merely from ExecMainStatus != 0.
  (let* ((facts
           (normalize-systemctl-show
            (nonfailed-nonzero-show-text "worker.service" "inv-worker")
            :expected-unit "worker.service"
            :activation-context "ctx-success"
            :generation "generation-1"
            :capture-id "worker-success"))
         (exit (fact-with-relation facts 'service-main-exit-observation)))
    (show-check-false (fact-with-relation facts 'activation-outcome)
                      "nonzero ExecMainStatus alone is not failure")
    (show-check-equal "75" (third (fact-arguments exit))
                      "nonzero main status is retained for inspection")
    (show-check-equal "success"
                      (second
                       (fact-arguments
                        (fact-with-relation facts
                                            'service-result-observation)))
                      "service Result remains separate from main status"))

  ;; Two units in the same modeled activation context keep distinct
  ;; InvocationIDs. The shared context is caller-supplied and explicit.
  (let* ((facts (normalize-e2e-snapshots))
         (invocations
           (remove-if-not
            (lambda (fact) (eq (fact-relation fact) 'unit-invocation))
            facts)))
    (show-check-equal 2 (length invocations)
                      "two snapshots preserve two unit invocation facts")
    (show-check-false
     (equal (second (fact-arguments (first invocations)))
            (second (fact-arguments (second invocations))))
     "per-unit InvocationIDs are not conflated")
    (show-check-equal
     "activation-context-1"
     (third (fact-arguments (first invocations)))
     "cross-unit correlation is explicit caller context")
    (show-check-equal
     "activation-context-1"
     (third (fact-arguments (second invocations)))
     "shared context does not overwrite unit identity"))

  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (append (project-2-configuration-facts "generation-1")
               (normalize-e2e-snapshots)))
    (show-check-equal :quiescent
                      (consistency-run-result-status result)
                      "normalized evidence reaches quiescence")
    (let* ((id
             (required-dependency-hypothesis-id
              "frontend.service" "api.service"
              "activation-context-1" "generation-1"))
           (fact (current-fact-by-id network id))
           (graph (explain-current-fact network id))
           (capture-source
             (source-node-with-provenance-kind
              graph :systemd-show-capture)))
      (show-check-true fact
                       "normalized snapshots support milestone-A diagnosis")
      (show-check-equal :grounded
                        (explanation-graph-status graph)
                        "normalized diagnosis remains explainable")
      (show-check-true capture-source
                       "explanation retains collector provenance")
      (show-check-equal "v261.3"
                        (getf (getf (explanation-node-data capture-source)
                                    :provenance)
                              :systemd-release)
                        "collector provenance pins normalization contract")))

  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (append
        (project-2-configuration-facts "generation-1")
        (normalize-systemctl-show
         (activating-show-text "frontend.service" "inv-frontend")
         :activation-context "context-current"
         :generation "generation-1"
         :capture-id "frontend-current")
        (normalize-systemctl-show
         (failed-show-text "api.service" "inv-api-old")
         :activation-context "context-old"
         :generation "generation-1"
         :capture-id "api-old")))
    (declare (ignore result))
    (show-check-equal
     :absent
     (explanation-graph-status
      (explain-required-dependency-hypothesis
       network "frontend.service" "api.service"
       "context-current" "generation-1"))
     "different activation contexts do not cross-join"))

  (multiple-value-bind (network result)
      (run-systemd-dependency-case
       (append
        (project-2-configuration-facts "generation-1")
        (normalize-systemctl-show
         (activating-show-text "frontend.service" "inv-frontend")
         :activation-context "context-current"
         :generation "generation-1"
         :capture-id "frontend-generation-1")
        (normalize-systemctl-show
         (failed-show-text "api.service" "inv-api")
         :activation-context "context-current"
         :generation "generation-2"
         :capture-id "api-generation-2")))
    (declare (ignore result))
    (show-check-equal
     :absent
     (explanation-graph-status
      (explain-required-dependency-hypothesis
       network "frontend.service" "api.service"
       "context-current" "generation-1"))
     "different configuration generations do not cross-join"))

  (format t "PASS: ~D systemd-show normalization checks~%"
          *systemd-show-tests-run*)
  t)

(run-systemd-show-tests)
