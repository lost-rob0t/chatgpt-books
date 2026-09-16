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

(defun binding (name bindings)
  (cdr (assoc name bindings :test #'eq)))

(defun run-tests ()
  (setf *tests-run* 0)

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

  (format t "~&PASS: ~D expert-system matcher checks~%" *tests-run*)
  t)

(run-tests)
