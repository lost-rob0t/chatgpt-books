(in-package #:cl-user)

(defpackage #:symbolic-ai.rules.tests
  (:use #:cl #:symbolic-ai.rules)
  (:export #:run-tests))

(in-package #:symbolic-ai.rules.tests)

(defvar *tests* '())

(defmacro deftest (name &body body)
  `(progn
     (defun ,name () ,@body)
     (pushnew ',name *tests*)))

(defmacro is (form &optional (message nil message-p))
  `(unless ,form
     (error "Assertion failed: ~S~@[ -- ~A~]"
            ',form
            ,(when message-p message))))

(defmacro is-equal (expected form &key (test ''equal))
  `(let ((actual ,form)
         (wanted ,expected))
     (unless (funcall ,test wanted actual)
       (error "Expected ~S, got ~S from ~S" wanted actual ',form))))

(defmacro signals (condition &body body)
  `(handler-case
       (progn ,@body
              (error "Expected condition ~S, but body returned normally."
                     ',condition))
     (,condition () t)))

(defun v (name)
  (symbolic-ai.pattern:make-variable name))

(defun bound (name bindings)
  (multiple-value-bind (value present-p)
      (binding-value name bindings)
    (unless present-p
      (error "Expected binding for ~S in ~S" name bindings))
    value))

(defun fact-data (result)
  (mapcar #'fact-datum
          (working-memory-facts (run-result-working-memory result))))

(defun justification-for-datum (result datum)
  (let ((fact (find datum
                    (working-memory-facts (run-result-working-memory result))
                    :key #'fact-datum
                    :test #'equal)))
    (and fact
         (find (fact-id fact)
               (run-result-justifications result)
               :key #'justification-fact-id
               :test #'eql))))

(deftest single-condition-matching-carries-bindings
  (let* ((service (v 'service))
         (memory (make-working-memory '((service api state failed))))
         (rule (make-rule
                'observe-failure
                `((service ,service state failed))
                (lambda (bindings)
                  (declare (ignore bindings))
                  '())))
         (agenda (build-agenda (list rule) memory)))
    (is (= 1 (length agenda)))
    (is-equal 'api (bound 'service (activation-bindings (first agenda))))
    (is-equal '(1) (activation-support-fact-ids (first agenda)))))

(deftest joins-preserve-one-binding-environment
  (let* ((service (v 'service))
         (dependency (v 'dependency))
         (rule
           (make-rule
            'dependency-down
            `((service ,service depends-on ,dependency)
              (service ,dependency health down))
            (lambda (bindings)
              `((service ,(bound 'service bindings)
                         suspect dependency-unavailable)))))
         (result
           (run-rules
            '((service api depends-on db)
              (service cache health down)
              (service db health down))
            (list rule))))
    (is (eq :quiescent (run-result-status result)))
    (is (member '(service api suspect dependency-unavailable)
                (fact-data result)
                :test #'equal))
    (is (not (member '(service cache suspect dependency-unavailable)
                     (fact-data result)
                     :test #'equal)))))

(deftest one-fact-does-not-fill-two-condition-slots-by-default
  (let* ((x (v 'x))
         (memory (make-working-memory '((tag a))))
         (strict
           (make-rule 'needs-two `((tag ,x) (tag ,x))
                      (lambda (bindings)
                        (declare (ignore bindings))
                        '())))
         (reuse
           (make-rule 'reuse-one `((tag ,x) (tag ,x))
                      (lambda (bindings)
                        (declare (ignore bindings))
                        '())
                      :allow-fact-reuse-p t)))
    (is (null (build-agenda (list strict) memory)))
    (is (= 1 (length (build-agenda (list reuse) memory))))
    (is-equal '(1 1)
              (activation-support-fact-ids
               (first (build-agenda (list reuse) memory))))))

(deftest agenda-orders-salience-then-rule-order
  (let* ((memory (make-working-memory '((ready))))
         (low (make-rule 'low '((ready))
                         (lambda (bindings)
                           (declare (ignore bindings))
                           '())
                         :salience 0))
         (high (make-rule 'high '((ready))
                          (lambda (bindings)
                            (declare (ignore bindings))
                            '())
                          :salience 10))
         (peer (make-rule 'peer '((ready))
                          (lambda (bindings)
                            (declare (ignore bindings))
                            '())
                          :salience 10))
         (agenda (build-agenda (list low high peer) memory)))
    (is-equal '(high peer low) (mapcar #'activation-rule-id agenda))))

(deftest multiple-binding-environments-produce-distinct-activations
  (let* ((service (v 'service))
         (memory
           (make-working-memory
            '((service api state failed)
              (service worker state failed))))
         (rule
           (make-rule 'failure
                      `((service ,service state failed))
                      (lambda (bindings)
                        (declare (ignore bindings))
                        '())))
         (agenda (build-agenda (list rule) memory)))
    (is (= 2 (length agenda)))
    (is-equal '(api worker)
              (mapcar (lambda (activation)
                        (bound 'service (activation-bindings activation)))
                      agenda))
    (is-equal '((1) (2))
              (mapcar #'activation-support-fact-ids agenda))))

(deftest duplicate-assertion-keeps-stable-fact-identity
  (let ((memory (make-working-memory '((ready)))))
    (multiple-value-bind (fact new-p)
        (assert-fact memory '(ready))
      (is (not new-p))
      (is (= 1 (fact-id fact)))
      (is (= 1 (length (working-memory-facts memory)))))))

(deftest exact-activation-refraction-stops-a-no-op-loop
  (let* ((rule
           (make-rule 'echo '((ping))
                      (lambda (bindings)
                        (declare (ignore bindings))
                        '((ping)))))
         (result (run-rules '((ping)) (list rule) :max-firings 10)))
    (is (eq :quiescent (run-result-status result)))
    (is (= 1 (length (run-result-firings result))))
    (is-equal '(1)
              (firing-duplicate-fact-ids
               (first (run-result-firings result))))
    (is (= 1 (length (working-memory-facts
                      (run-result-working-memory result)))))))

(deftest infrastructure-diagnosis-chains-with-justification
  (let* ((service (v 'service))
         (dependency (v 'dependency))
         (rule-dependency
           (make-rule
            'dependency-down
            `((service ,service depends-on ,dependency)
              (service ,dependency health down))
            (lambda (bindings)
              `((service ,(bound 'service bindings)
                         suspect dependency-unavailable)))
            :salience 10))
         (rule-diagnose
           (make-rule
            'diagnose-dependency
            `((service ,service state failed)
              (service ,service suspect dependency-unavailable)
              (probe ,service code connection-refused))
            (lambda (bindings)
              `((diagnosis ,(bound 'service bindings)
                           dependency-unavailable)))
            :salience 0))
         (result
           (run-rules
            '((service api state failed)
              (service api depends-on db)
              (service db health down)
              (probe api code connection-refused))
            (list rule-dependency rule-diagnose)))
         (diagnosis '(diagnosis api dependency-unavailable))
         (why (justification-for-datum result diagnosis)))
    (is (eq :quiescent (run-result-status result)))
    (is (member diagnosis (fact-data result) :test #'equal))
    (is why)
    (is-equal 'diagnose-dependency (justification-rule-id why))
    (is-equal '(1 5 4) (justification-support-fact-ids why))
    (is-equal 'api (bound 'service (justification-bindings why)))))

(deftest growing-rule-reports-bounded-not-quiescent
  (let* ((x (v 'x))
         (rule
           (make-rule
            'grow
            `((seed ,x))
            (lambda (bindings)
              `((seed (next ,(bound 'x bindings)))))))
         (result (run-rules '((seed zero)) (list rule) :max-firings 3)))
    (is (eq :bounded (run-result-status result)))
    (is (= 3 (length (run-result-firings result))))
    (is (= 4 (length (working-memory-facts
                      (run-result-working-memory result)))))
    (is (= 1 (length (run-result-remaining-agenda result))))))

(deftest ungrounded-rule-output-fails-closed
  (let ((rule
          (make-rule 'bad '((ready))
                     (lambda (bindings)
                       (declare (ignore bindings))
                       `((derived ,(v 'unbound)))))))
    (signals invalid-derived-fact
      (run-rules '((ready)) (list rule)))))

(deftest non-list-rule-output-fails-closed
  (let ((rule
          (make-rule 'bad-output '((ready))
                     (lambda (bindings)
                       (declare (ignore bindings))
                       'not-a-fact-list))))
    (signals invalid-rule-action-output
      (run-rules '((ready)) (list rule)))))

(defun run-tests ()
  (let ((passed 0)
        (failed 0))
    (dolist (test (reverse *tests*))
      (handler-case
          (progn
            (funcall test)
            (incf passed)
            (format t "PASS ~A~%" test))
        (error (condition)
          (incf failed)
          (format *error-output* "FAIL ~A: ~A~%" test condition))))
    (format t "~%Rule-system tests: ~D passed, ~D failed.~%" passed failed)
    (when (plusp failed)
      (error "Rule-system test failures: ~D" failed))
    passed))
