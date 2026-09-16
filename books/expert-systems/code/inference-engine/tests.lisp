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

(defun check-signals (thunk label)
  (incf *tests-run*)
  (let ((signaled-p nil))
    (handler-case
        (funcall thunk)
      (error () (setf signaled-p t)))
    (unless signaled-p
      (error "FAIL ~A: expected an error" label))))

(defun binding (name bindings)
  (cdr (assoc name bindings :test #'eq)))

(defun fact-by-relation (relation facts)
  (find relation facts :key #'fact-relation :test #'eq))

(defun run-tests ()
  (setf *tests-run* 0)

  ;; Milestone A regression oracle.
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

  (let ((same (make-fact :id "same" :relation 'pair :arguments '(api api)))
        (different (make-fact :id "different" :relation 'pair
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

  (let* ((results (match-conditions
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

  (let* ((results (match-conditions
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

  ;; Milestone B: real mutable working memory.
  (let* ((one (make-fact :id "obs.1" :relation 'signal :arguments '(api bad)))
         (same-content (make-fact :id "obs.2" :relation 'signal
                                  :arguments '(api bad)))
         (memory (make-working-memory (list one))))
    (check-equal 1 (fact-assertion-sequence memory "obs.1")
                 "first assertion receives sequence one")
    (check-equal 2 (assert-fact memory same-content)
                 "assertion sequence is monotonic")
    (check-equal 2 (length (facts-in-working-memory memory))
                 "equal content remains distinct under different IDs")
    (check-signals
     (lambda ()
       (assert-fact memory
                    (make-fact :id "obs.2" :relation 'other :arguments '(x))))
     "duplicate active fact ID is rejected")
    (check-equal "obs.1" (fact-id (retract-fact memory "obs.1"))
                 "retraction returns the removed fact")
    (check-false (fact-assertion-sequence memory "obs.1")
                 "retracted fact has no active assertion sequence")
    (check-signals
     (lambda ()
       (assert-fact memory
                    (make-fact :id "obs.1" :relation 'signal
                               :arguments '(api bad))))
     "retracted stable ID cannot be recycled")
    (check-false (retract-fact memory "missing")
                 "retracting an unknown active ID is a no-op"))

  ;; Production validation and agenda ordering.
  (let* ((memory (make-working-memory
                  (list (make-fact :id "old" :relation 'signal
                                   :arguments '(api bad))
                        (make-fact :id "new" :relation 'signal
                                   :arguments '(worker bad)))))
         (low (make-production :id "rule.low"
                               :conditions '((signal ?service bad))
                               :actions '((:assert seen ?service))
                               :salience 1))
         (high (make-production :id "rule.high"
                                :conditions '((signal ?service bad))
                                :actions '((:assert seen ?service))
                                :salience 10))
         (session (make-inference-session memory (list low high)))
         (agenda (session-agenda session)))
    (check-equal "rule.high" (activation-production-id (first agenda))
                 "higher salience wins before recency")
    (check-equal '("new") (activation-fact-ids (first agenda))
                 "newer support wins within equal production priority")
    (check-equal 2 (activation-recency (first agenda))
                 "activation records newest support sequence"))

  (let* ((memory (make-working-memory
                  (list (make-fact :id "state" :relation 'state
                                   :arguments '(api failed))
                        (make-fact :id "policy" :relation 'policy
                                   :arguments '(api restart)))))
         (one-condition
           (make-production :id "a.less-specific"
                            :conditions '((policy ?service restart))
                            :actions '((:assert selected one))
                            :salience 0))
         (two-conditions
           (make-production :id "z.more-specific"
                            :conditions '((state ?service failed)
                                          (policy ?service restart))
                            :actions '((:assert selected two))
                            :salience 0))
         (agenda (session-agenda
                  (make-inference-session memory
                                          (list one-condition two-conditions)))))
    (check-equal "z.more-specific" (activation-production-id (first agenda))
                 "condition-count specificity breaks a recency tie"))

  (let* ((memory (make-working-memory
                  (list (make-fact :id "only" :relation 'state
                                   :arguments '(api failed)))))
         (b (make-production :id "b.rule" :conditions '((state api failed))
                             :actions '((:assert chosen b))))
         (a (make-production :id "a.rule" :conditions '((state api failed))
                             :actions '((:assert chosen a))))
         (agenda (session-agenda (make-inference-session memory (list b a)))))
    (check-equal "a.rule" (activation-production-id (first agenda))
                 "stable production ID is the deterministic final rule tie-break"))

  (check-signals
   (lambda ()
     (make-inference-session
      (make-working-memory)
      (list (make-production :id "dup" :conditions '((x y))
                             :actions '((:assert z y)))
            (make-production :id "dup" :conditions '((a b))
                             :actions '((:assert c b))))))
   "duplicate production IDs are rejected")

  (check-signals
   (lambda ()
     (make-inference-session
      (make-working-memory)
      (list (make-production :id "bad-action" :conditions '((x y))
                             :actions '((:call arbitrary-code))))))
   "arbitrary callable actions are rejected")

  ;; Forward chaining, structured actions, provenance, and refraction.
  (let* ((memory (make-working-memory *service-diagnosis-facts*))
         (session (make-inference-session memory *service-diagnosis-productions*))
         (result (run-forward-chain session :max-firings 10))
         (facts (facts-in-working-memory memory))
         (impact (fact-by-relation 'dependency-impact facts))
         (restart (fact-by-relation 'restart-candidate facts)))
    (check-equal :quiescent (inference-result-status result)
                 "service scenario reaches quiescence")
    (check-equal 2 (length (inference-result-firings result))
                 "two independent productions fire once")
    (check-equal "derive.dependency-impact"
                 (firing-record-production-id
                  (first (inference-result-firings result)))
                 "higher-salience dependency rule fires first")
    (check-true impact "forward chain asserts dependency impact")
    (check-equal '(frontend api) (fact-arguments impact)
                 "assert action substitutes activation bindings")
    (check-true restart "forward chain asserts restart candidate")
    (check-equal :derived (getf (fact-provenance impact) :kind)
                 "derived fact provenance is explicit")
    (check-equal '("obs.api.state.failed" "dep.frontend.api")
                 (getf (fact-provenance impact) :support-fact-ids)
                 "derived fact records exact supports")
    (check-equal 0
                 (length (inference-result-firings
                          (run-forward-chain session :max-firings 10)))
                 "persistent session refraction prevents same-support refiring"))

  ;; Retraction removes activations; a genuinely new identity can activate again.
  (let* ((first (make-fact :id "old.failed" :relation 'state
                           :arguments '(api failed)))
         (memory (make-working-memory (list first)))
         (rule (make-production :id "observe.failure"
                                :conditions '((state ?service failed))
                                :actions '((:assert noticed ?service))))
         (session (make-inference-session memory (list rule))))
    (check-equal 1 (length (session-agenda session))
                 "active support creates an activation")
    (retract-fact memory "old.failed")
    (check-equal 0 (length (session-agenda session))
                 "retraction removes dependent activation")
    (assert-fact memory
                 (make-fact :id "new.failed" :relation 'state
                            :arguments '(api failed)))
    (check-equal '("new.failed")
                 (activation-fact-ids (first (session-agenda session)))
                 "same content with new observation identity can activate"))

  ;; Refraction is not a general termination proof: changing supports can loop.
  (let* ((memory (make-working-memory
                  (list (make-fact :id "pulse.seed" :relation 'pulse
                                   :arguments '(api)))))
         (rule (make-production :id "copy.pulse"
                                :conditions '((pulse ?service))
                                :actions '((:assert pulse ?service))))
         (result (run-forward-chain
                  (make-inference-session memory (list rule))
                  :max-firings 3)))
    (check-equal :limit-reached (inference-result-status result)
                 "bounded runner reports changing-support loop")
    (check-equal 3 (length (inference-result-firings result))
                 "firing limit bounds non-quiescent inference"))

  (format t "~&PASS: ~D expert-system semantic checks~%" *tests-run*)
  t)

(run-tests)
