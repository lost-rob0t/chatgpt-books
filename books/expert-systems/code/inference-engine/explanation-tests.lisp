(in-package #:expert-systems.matcher)

(defvar *explanation-tests-run* 0)

(defun explanation-check-true (value label)
  (incf *explanation-tests-run*)
  (unless value
    (error "FAIL explanation ~A: expected true, got ~S" label value)))

(defun explanation-check-false (value label)
  (incf *explanation-tests-run*)
  (when value
    (error "FAIL explanation ~A: expected false, got ~S" label value)))

(defun explanation-check-equal (expected actual label)
  (incf *explanation-tests-run*)
  (unless (equal expected actual)
    (error "FAIL explanation ~A: expected ~S, got ~S"
           label expected actual)))

(defun explanation-node-count (graph kind)
  (count kind (explanation-graph-nodes graph)
         :key #'explanation-node-kind
         :test #'eq))

(defun explanation-edge-count (graph kind)
  (count kind (explanation-graph-edges graph)
         :key #'explanation-edge-kind
         :test #'eq))

(defun explanation-find-node (graph kind)
  (find kind (explanation-graph-nodes graph)
        :key #'explanation-node-kind
        :test #'eq))

(defun explanation-derived-production
    (id conditions fact-id relation arguments &optional (provenance '(:kind :test-rule)))
  (make-production
   :id id
   :conditions conditions
   :provenance provenance
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
             :support-fact-ids
             (copy-list (activation-fact-ids activation))))))))

(defun run-explanation-tests ()
  (setf *explanation-tests-run* 0)

  ;; Base evidence is an explicit support source, not a mystery leaf.
  (let* ((fact (test-fact "obs.base" 'signal '(present)))
         (truth (make-truth-maintained-network
                 (make-engine :facts (list fact))))
         (network (make-assumption-network truth))
         (graph (explain-current-fact network "obs.base")))
    (explanation-check-equal :grounded
                             (explanation-graph-status graph)
                             "base evidence is grounded")
    (explanation-check-equal 1
                             (explanation-node-count graph :fact)
                             "base explanation has one fact occurrence")
    (explanation-check-equal 1
                             (explanation-node-count graph :source)
                             "base explanation has an explicit source node")
    (let ((source (explanation-find-node graph :source)))
      (explanation-check-equal :evidence
                               (getf (explanation-node-data source)
                                     :support-kind)
                               "ordinary base support is labeled evidence")))

  ;; Explicit assumptions retain their distinct support classification.
  (let* ((truth (make-truth-maintained-network (make-engine)))
         (network (make-assumption-network truth))
         (fact (test-fact "assume.flag" 'feature-flag '(enabled))))
    (assumption-network-assert-assumption network fact)
    (let* ((graph (explain-current-fact network "assume.flag"))
           (source (explanation-find-node graph :source)))
      (explanation-check-equal :grounded
                               (explanation-graph-status graph)
                               "assumption is grounded while asserted")
      (explanation-check-equal :assumption
                               (getf (explanation-node-data source)
                                     :support-kind)
                               "assumption source stays explicit")))

  ;; The existing service fixture forms a two-hop support graph.
  (let* ((engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (truth (make-truth-maintained-network engine))
         (network (make-assumption-network truth)))
    (run-assumption-network network
                            :firing-limit 10
                            :contradiction-policy :report-only)
    (let ((graph
            (explain-current-fact
             network "derived.needs-investigation.frontend")))
      (explanation-check-equal :grounded
                               (explanation-graph-status graph)
                               "two-hop service conclusion is grounded")
      (explanation-check-equal 2
                               (explanation-node-count graph :justification)
                               "two-hop explanation keeps both rule applications")
      (explanation-check-true
       (>= (explanation-edge-count graph :uses) 4)
       "two-hop explanation exposes exact supporting occurrences")
      (let ((top-just
              (find-if
               (lambda (node)
                 (and (eq (explanation-node-kind node) :justification)
                      (equal
                       "rule.investigate-degraded-dependent"
                       (getf (explanation-node-data node)
                             :production-id))))
               (explanation-graph-nodes graph))))
        (explanation-check-true top-just
                                "top rule identity is present")
        (explanation-check-equal
         :book-rule
         (getf
          (getf (explanation-node-data top-just)
                :production-provenance)
          :kind)
         "rule provenance survives into explanation"))))

  ;; Independent derivations remain alternatives instead of being collapsed.
  (let* ((a (test-fact "base.a" 'seed '(a)))
         (b (test-fact "base.b" 'seed '(b)))
         (p1
           (explanation-derived-production
            "rule.a-to-x" '((seed a))
            "derived.x" 'conclusion '(x)
            '(:kind :test-rule :source "rule-a")))
         (p2
           (explanation-derived-production
            "rule.b-to-x" '((seed b))
            "derived.x" 'conclusion '(x)
            '(:kind :test-rule :source "rule-b")))
         (truth
           (make-truth-maintained-network
            (make-engine :facts (list a b)
                         :productions (list p1 p2))))
         (network (make-assumption-network truth)))
    (run-assumption-network network
                            :firing-limit 10
                            :contradiction-policy :report-only)
    (let ((graph (explain-current-fact network "derived.x")))
      (explanation-check-equal 2
                               (explanation-node-count graph :justification)
                               "two independent reasons are both retained")
      (explanation-check-equal 2
                               (explanation-edge-count graph :supported-by)
                               "fact points to both independent reasons")))

  ;; Base support and a derived reason are distinct support sources.
  (let* ((seed (test-fact "base.seed" 'seed '(on)))
         (x (test-fact "fact.x" 'conclusion '(x)))
         (production
           (explanation-derived-production
            "rule.seed-to-x" '((seed on))
            "fact.x" 'conclusion '(x)))
         (truth
           (make-truth-maintained-network
            (make-engine :facts (list seed x)
                         :productions (list production))))
         (network (make-assumption-network truth)))
    (run-assumption-network network
                            :firing-limit 10
                            :contradiction-policy :report-only)
    (let ((graph (explain-current-fact network "fact.x")))
      (explanation-check-equal 1
                               (explanation-node-count graph :source)
                               "mixed support preserves base source")
      (explanation-check-equal 1
                               (explanation-node-count graph :justification)
                               "mixed support preserves derived reason")
      (explanation-check-equal 1
                               (explanation-edge-count graph :grounded-by)
                               "mixed support has source edge")
      (explanation-check-equal 1
                               (explanation-edge-count graph :supported-by)
                               "mixed support has justification edge")))

  ;; Historical reasons are not silently rebound to a later same-ID occurrence.
  (let* ((seed (test-fact "base.seed" 'seed '(on)))
         (production
           (explanation-derived-production
            "rule.seed-to-x" '((seed on))
            "fact.x" 'conclusion '(x)))
         (engine (make-engine :facts (list seed)
                              :productions (list production)))
         (truth (make-truth-maintained-network engine))
         (network (make-assumption-network truth)))
    (run-assumption-network network
                            :firing-limit 10
                            :contradiction-policy :report-only)
    (let ((old-stamp (current-stamp-for-fact-id truth "fact.x")))
      (truth-maintained-retract-base-fact truth "base.seed")
      (explanation-check-false
       (find-wm-entry (engine-working-memory engine) "fact.x")
       "losing final support removes derived occurrence")
      (truth-maintained-assert-base-fact
       truth (test-fact "fact.x" 'conclusion '(x)))
      (let ((new-stamp (current-stamp-for-fact-id truth "fact.x"))
            (graph (explain-current-fact network "fact.x")))
        (explanation-check-false
         (equal old-stamp new-stamp)
         "same stable ID receives a fresh occurrence stamp")
        (explanation-check-equal 0
                                 (explanation-node-count graph :justification)
                                 "stale historical reason is excluded")
        (explanation-check-equal 1
                                 (explanation-node-count graph :source)
                                 "new base occurrence explains itself as evidence"))))

  ;; Absence is a typed result, not an invented opposite or failed-rule story.
  (let* ((network
           (make-assumption-network
            (make-truth-maintained-network (make-engine))))
         (graph (explain-current-fact network "missing.fact")))
    (explanation-check-equal :absent
                             (explanation-graph-status graph)
                             "absent fact has explicit status")
    (explanation-check-equal '()
                             (explanation-graph-nodes graph)
                             "absent fact has no invented support graph")
    (explanation-check-equal '()
                             (explanation-graph-edges graph)
                             "absent fact has no invented edges"))

  ;; Current contradiction explanations preserve both branches and the
  ;; provenance of the declaration that says those branches conflict.
  (let* ((active
           (test-fact "obs.api.active.e42"
                      'unit-active-state '(api-service active 42)))
         (failed
           (test-fact "assume.api.failed.e42"
                      'unit-active-state '(api-service failed 42)))
         (spec (active-vs-failed-spec))
         (truth
           (make-truth-maintained-network
            (make-engine :facts (list active))))
         (network
           (make-assumption-network truth
                                    :contradiction-specs (list spec))))
    (assumption-network-assert-assumption network failed)
    (let* ((report (first (assumption-network-contradictions network)))
           (graph (explain-contradiction-report network report))
           (root (explanation-find-node graph :contradiction)))
      (explanation-check-equal :contradiction
                               (explanation-graph-status graph)
                               "current conflict gets contradiction graph")
      (explanation-check-equal 2
                               (explanation-edge-count graph :counterevidence)
                               "contradiction root keeps both sides")
      (explanation-check-equal
       '(:source :systemd-dbus-unit-api
         :claim :one-high-level-active-state-per-observation)
       (getf (explanation-node-data root) :spec-provenance)
       "constraint provenance is preserved")
      (explanation-check-equal
       '(:evidence :assumption)
       (list (getf (explanation-node-data root) :left-support-kind)
             (getf (explanation-node-data root) :right-support-kind))
       "counterevidence support kinds remain distinct")
      (explanation-check-equal
       (explanation-graph-signature graph)
       (explanation-graph-signature
        (explain-contradiction-report network report))
       "explanation graph ordering is deterministic")
      (assumption-network-withdraw-assumption
       network "assume.api.failed.e42")
      (let ((stale (explain-contradiction-report network report)))
        (explanation-check-equal :stale
                                 (explanation-graph-status stale)
                                 "old contradiction report becomes stale")
        (explanation-check-equal '()
                                 (explanation-graph-nodes stale)
                                 "stale contradiction has no current graph"))))

  (format t "PASS: ~D explanation/provenance checks~%"
          *explanation-tests-run*)
  t)

(run-explanation-tests)
