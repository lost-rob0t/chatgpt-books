(in-package #:expert-systems.matcher)

(defvar *tests-run* 0)

(defun check-true (value label)
  (incf *tests-run*)
  (unless value
    (error "FAIL ~A: expected true, got ~S" label value)))

(defun check-false (value label)
  (incf *tests-run*)
  (when value
    (error "FAIL ~A: expected false, got ~S" label value)))

(defun check-equal (expected actual label)
  (incf *tests-run*)
  (unless (equal expected actual)
    (error "FAIL ~A: expected ~S, got ~S" label expected actual)))

(defun check-signals-duplicate-fact-id (thunk label)
  (incf *tests-run*)
  (handler-case
      (progn
        (funcall thunk)
        (error "FAIL ~A: expected DUPLICATE-FACT-ID" label))
    (duplicate-fact-id () t)))

(defun check-signals-duplicate-production-id (thunk label)
  (incf *tests-run*)
  (handler-case
      (progn
        (funcall thunk)
        (error "FAIL ~A: expected DUPLICATE-PRODUCTION-ID" label))
    (duplicate-production-id () t)))

(defun binding (name bindings)
  (cdr (assoc name bindings :test #'eq)))

(defun noop-production (id conditions &key (salience 0))
  (make-production
   :id id
   :conditions conditions
   :salience salience
   :provenance '(:kind :test-rule)
   :action (lambda (activation)
             (declare (ignore activation))
             '())))

(defun test-fact (id relation arguments)
  (make-fact :id id
             :relation relation
             :arguments arguments
             :provenance '(:kind :test)))

(defun run-tests ()
  (setf *tests-run* 0)

  ;; Milestone A: literal matching, variables, and deterministic joins.
  (let ((fact (first *service-diagnosis-facts*)))
    (check-true
     (literal-condition-match-p '(service-state api failed) fact)
     "literal matcher accepts exact relation and arguments")
    (check-false
     (literal-condition-match-p '(service-state api active) fact)
     "literal matcher rejects a different literal")
    (multiple-value-bind (bindings matched-p)
        (match-condition '(service-state ?service failed) fact)
      (check-true matched-p "variable pattern matches")
      (check-equal 'api (binding '?service bindings)
                   "variable receives fact value")))

  (let ((same (make-fact :id "same"
                         :relation 'pair
                         :arguments '(api api)))
        (different (make-fact :id "different"
                              :relation 'pair
                              :arguments '(api frontend))))
    (multiple-value-bind (bindings matched-p)
        (match-condition '(pair ?x ?x) same)
      (check-true matched-p "repeated variable accepts equal fields")
      (check-equal 'api (binding '?x bindings)
                   "repeated variable keeps one binding"))
    (multiple-value-bind (bindings matched-p)
        (match-condition '(pair ?x ?x) different)
      (declare (ignore bindings))
      (check-false matched-p "repeated variable rejects unequal fields")))

  (multiple-value-bind (bindings matched-p)
      (match-condition '(service-state ?service failed)
                       (first *service-diagnosis-facts*)
                       (list (cons '?service 'frontend)))
    (declare (ignore bindings))
    (check-false matched-p "existing binding cannot be overwritten"))

  (let* ((results
           (match-conditions
            '((service-state ?service failed)
              (service-restart-policy ?service on-failure))
            *service-diagnosis-facts*))
         (result (first results)))
    (check-equal 1 (length results)
                 "two-condition join returns one service")
    (check-equal 'api (binding '?service (match-result-bindings result))
                 "join propagates the shared service binding")
    (check-equal '("obs.api.state.failed" "cfg.api.restart.on-failure")
                 (match-result-fact-ids result)
                 "join records supporting fact identities"))

  (let* ((results
           (match-conditions
            '((service-state ?service failed)
              (service-restart-policy ?service on-failure)
              (depends-on ?dependent ?service))
            *service-diagnosis-facts*))
         (result (first results)))
    (check-equal 1 (length results)
                 "three-condition join finds the dependency chain")
    (check-equal 'api (binding '?service (match-result-bindings result))
                 "three-condition join keeps service binding")
    (check-equal 'frontend (binding '?dependent (match-result-bindings result))
                 "later condition extends bindings")
    (check-equal '("obs.api.state.failed"
                   "cfg.api.restart.on-failure"
                   "dep.frontend.api")
                 (match-result-fact-ids result)
                 "supporting fact order follows condition order"))

  (check-equal
   '()
   (match-conditions
    '((service-state ?service active)
      (service-restart-policy ?service on-failure))
    *service-diagnosis-facts*)
   "failed first condition yields no complete matches")

  (let ((provenance (fact-provenance (first *service-diagnosis-facts*))))
    (check-equal :synthetic-observation (getf provenance :kind)
                 "fixture labels synthetic evidence honestly")
    (check-true (getf provenance :source)
                "fixture retains source provenance"))

  ;; Milestone B: mutable working memory with identity and assertion occurrences.
  (let ((memory (make-working-memory *service-diagnosis-facts*)))
    (check-equal 5 (length (working-memory-entries memory))
                 "working memory contains seeded facts")
    (check-equal '(1 2 3 4 5)
                 (mapcar #'wm-entry-sequence (working-memory-entries memory))
                 "initial assertions receive monotonic occurrence sequences")
    (check-equal 5 (working-memory-next-sequence memory)
                 "working memory records latest sequence"))

  (let* ((first (test-fact "same-id" 'service-state '(api failed)))
         (memory (make-working-memory (list first))))
    (check-signals-duplicate-fact-id
     (lambda ()
       (assert-fact memory
                    (test-fact "same-id" 'service-state '(api failed))))
     "duplicate stable fact ID is rejected")
    (check-equal 1 (length (working-memory-facts memory))
                 "failed duplicate assertion leaves memory unchanged"))

  (let* ((first (test-fact "obs-1" 'service-state '(api failed)))
         (second (test-fact "obs-2" 'service-state '(api failed)))
         (memory (make-working-memory (list first))))
    (assert-fact memory second)
    (check-equal 2 (length (working-memory-facts memory))
                 "equal content with distinct IDs remains distinct evidence"))

  (let* ((first (test-fact "obs-a" 'service-state '(api failed)))
         (memory (make-working-memory (list first))))
    (multiple-value-bind (retracted present-p)
        (retract-fact memory "obs-a")
      (check-true present-p "retraction reports present stable ID")
      (check-equal "obs-a" (fact-id retracted)
                   "retraction returns exact fact")
      (check-equal '() (working-memory-facts memory)
                   "retraction removes current occurrence"))
    (let ((entry (assert-fact memory first)))
      (check-equal 2 (wm-entry-sequence entry)
                   "reasserted stable ID receives a new occurrence sequence")))

  (let* ((memory (make-working-memory
                  (list (test-fact "old" 'x '(1)))))
         (before (length (working-memory-facts memory))))
    (check-signals-duplicate-fact-id
     (lambda ()
       (assert-facts memory
                     (list (test-fact "fresh" 'x '(2))
                           (test-fact "old" 'x '(3)))))
     "batch validates every ID before mutation")
    (check-equal before (length (working-memory-facts memory))
                 "invalid assertion batch has no partial commit")
    (check-false (find-wm-entry memory "fresh")
                 "fresh member of rejected batch was not asserted"))

  ;; Production identity and complete instantiations.
  (let ((production
          (noop-production "rule.failed-service"
                           '((service-state ?service failed)))))
    (let* ((engine (make-engine :facts *service-diagnosis-facts*
                                :productions (list production)))
           (agenda (build-agenda engine))
           (activation (first agenda)))
      (check-equal 1 (length agenda)
                   "production builds one complete activation")
      (check-equal "rule.failed-service"
                   (production-id (activation-production activation))
                   "activation retains stable production identity")
      (check-equal 'api (activation-binding activation '?service)
                   "activation retains complete bindings")
      (check-equal '("obs.api.state.failed")
                   (activation-fact-ids activation)
                   "activation retains supporting fact IDs")
      (check-equal '(("obs.api.state.failed" . 1))
                   (activation-support-stamps activation)
                   "activation retains support occurrence stamp")))

  (let ((p1 (noop-production "duplicate-rule" '((x ?x))))
        (p2 (noop-production "duplicate-rule" '((y ?y)))))
    (check-signals-duplicate-production-id
     (lambda () (make-engine :productions (list p1 p2)))
     "stable production IDs are unique inside an engine"))

  ;; Agenda ordering is explicit and deterministic.
  (let* ((fact (test-fact "state" 'service-state '(api failed)))
         (low (noop-production "rule.low" '((service-state ?s failed))
                               :salience 0))
         (high (noop-production "rule.high" '((service-state ?s failed))
                                :salience 50))
         (agenda (build-agenda
                  (make-engine :facts (list fact)
                               :productions (list low high)))))
    (check-equal "rule.high"
                 (production-id (activation-production (first agenda)))
                 "higher salience wins before other agenda keys"))

  (let* ((older (test-fact "old-state" 'service-state '(api failed)))
         (newer (test-fact "new-state" 'service-state '(frontend failed)))
         (production
           (noop-production "rule.any-failure"
                            '((service-state ?service failed))))
         (agenda (build-agenda
                  (make-engine :facts (list older newer)
                               :productions (list production)))))
    (check-equal "new-state" (first (activation-fact-ids (first agenda)))
                 "newer support occurrence wins equal-salience conflict"))

  (let* ((fact (test-fact "state" 'service-state '(api failed)))
         (general
           (noop-production "rule.general"
                            '((service-state ?service ?state))))
         (specific
           (noop-production "rule.specific"
                            '((service-state ?service failed))))
         (agenda (build-agenda
                  (make-engine :facts (list fact)
                               :productions (list general specific)))))
    (check-equal "rule.specific"
                 (production-id (activation-production (first agenda)))
                 "greater structural specificity wins after recency"))

  (let* ((fact (test-fact "state" 'service-state '(api failed)))
         (b (noop-production "rule.b" '((service-state ?service failed))))
         (a (noop-production "rule.a" '((service-state ?service failed))))
         (agenda (build-agenda
                  (make-engine :facts (list fact)
                               :productions (list b a)))))
    (check-equal "rule.a"
                 (production-id (activation-production (first agenda)))
                 "stable production ID removes definition-order tie"))

  ;; Refraction keys use support occurrences, not only stable fact IDs.
  (let* ((fact (test-fact "state" 'service-state '(api failed)))
         (production
           (noop-production "rule.once-per-support"
                            '((service-state ?service failed))))
         (engine (make-engine :facts (list fact)
                              :productions (list production)))
         (first-activation (first (build-agenda engine)))
         (first-key (activation-key first-activation)))
    (fire-activation engine first-activation)
    (check-equal '() (build-agenda engine)
                 "unchanged fired activation is refracted")
    (retract-fact (engine-working-memory engine) "state")
    (assert-fact (engine-working-memory engine) fact)
    (let ((second-activation (first (build-agenda engine))))
      (check-true second-activation
                  "reasserted support can create a new activation")
      (check-false (equal first-key (activation-key second-activation))
                   "new assertion occurrence changes refraction key")))

  ;; Invalid action output fails before mutation and before refraction.
  (let* ((fact (test-fact "state" 'service-state '(api failed)))
         (production
           (make-production
            :id "rule.bad-output"
            :conditions '((service-state ?service failed))
            :action
            (lambda (activation)
              (declare (ignore activation))
              (list (test-fact "state" 'derived '(duplicate-id))))))
         (engine (make-engine :facts (list fact)
                              :productions (list production)))
         (activation (first (build-agenda engine))))
    (check-signals-duplicate-fact-id
     (lambda () (fire-activation engine activation))
     "duplicate action output is rejected")
    (check-equal 1 (length (working-memory-facts
                            (engine-working-memory engine)))
                 "failed firing does not partially mutate working memory")
    (check-equal '() (engine-firing-records engine)
                 "failed firing does not append a firing record")
    (check-true (first (build-agenda engine))
                "failed firing does not incorrectly refract activation"))

  ;; Project 1 milestone B: actual multi-cycle forward chaining.
  (let* ((engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (result (run-engine engine :firing-limit 10))
         (memory (engine-working-memory engine))
         (impact (find-wm-entry memory
                                "derived.dependency-impact.frontend.api"))
         (investigate (find-wm-entry memory
                                     "derived.needs-investigation.frontend"))
         (records (engine-firing-records engine)))
    (check-equal :quiescent (run-result-status result)
                 "service scenario reaches quiescence")
    (check-equal 2 (run-result-firing-count result)
                 "service scenario requires two production firings")
    (check-true impact "first firing derives dependency impact")
    (check-true investigate "second firing derives investigation need")
    (check-equal '("rule.dependency-impact"
                   "rule.investigate-degraded-dependent")
                 (mapcar #'firing-record-production-id records)
                 "firing trace records deterministic production order")
    (check-equal '("obs.api.state.failed" "dep.frontend.api")
                 (firing-record-support-fact-ids (first records))
                 "first firing trace records its exact support")
    (check-equal :derived
                 (getf (fact-provenance (wm-entry-fact impact)) :kind)
                 "derived fact is explicitly marked derived")
    (check-equal "rule.dependency-impact"
                 (getf (fact-provenance (wm-entry-fact impact)) :rule-id)
                 "derived provenance records stable rule ID")
    (check-equal '()
                 (run-result-remaining-activation-keys result)
                 "quiescent result exposes no hidden remaining work"))

  (let* ((engine
           (make-engine :facts *service-diagnosis-facts*
                        :productions (make-service-diagnosis-productions)))
         (result (run-engine engine :firing-limit 1)))
    (check-equal :limit (run-result-status result)
                 "firing limit is distinct from quiescence")
    (check-equal 1 (run-result-firing-count result)
                 "firing limit records committed work only")
    (check-true (run-result-remaining-activation-keys result)
                "limit result exposes remaining eligible activation"))

  (format t "~&PASS: ~D expert-system engine checks~%" *tests-run*)
  t)

(run-tests)
