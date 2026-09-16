(in-package #:symbolic-ai-formal)

(defun %assert-equal (expected actual label)
  (unless (equal expected actual)
    (error "~A: expected ~S, got ~S" label expected actual)))

(defun %assert-true (value label)
  (unless value
    (error "~A: expected true, got ~S" label value)))

(defun test-safe-cycle-is-proved ()
  (let* ((system
           (make-transition-system
            :initial-states '(0)
            :successors (lambda (state)
                          (case state
                            (0 '(1))
                            (1 '(0))
                            (otherwise '())))
            :invariant (lambda (state) (member state '(0 1)))))
         (result (check-invariant system)))
    (%assert-equal :proved (check-result-status result) "safe cycle status")
    (%assert-equal 2 (check-result-visited result) "safe cycle visited")
    (%assert-true (check-result-conclusive-p result)
                  "exhaustive proof is conclusive")))

(defun test-violation-has-shortest-counterexample ()
  (let* ((system
           (make-transition-system
            :initial-states '(0)
            :successors (lambda (state)
                          (case state
                            (0 '(1 10))
                            (1 '(2))
                            (10 '(11))
                            (11 '(12))
                            (otherwise '())))
            :invariant (lambda (state) (< state 2))))
         (result (check-invariant system)))
    (%assert-equal :refuted (check-result-status result) "refuted status")
    (%assert-equal '(0 10) (check-result-trace result)
                   "BFS counterexample chooses shortest violating trace")
    (%assert-true (check-result-conclusive-p result)
                  "concrete refutation is conclusive without graph exhaustion")))

(defun test-unreachable-bad-state-does-not-refute ()
  (let* ((system
           (make-transition-system
            :initial-states '(0)
            :successors (lambda (state)
                          (case state
                            (0 '(1))
                            (1 '())
                            (99 '(99))
                            (otherwise '())))
            :invariant (lambda (state) (/= state 99))))
         (result (check-invariant system)))
    (%assert-equal :proved (check-result-status result) "unreachable bad state")
    (%assert-equal 2 (check-result-visited result) "only reachable states count")))

(defun test-cycle-terminates-with-duplicate-state ()
  (let* ((system
           (make-transition-system
            :initial-states '((a))
            :successors (lambda (state)
                          (if (equal state '(a))
                              (list (list 'b))
                              (list (list 'a))))
            :invariant (lambda (state)
                         (member (first state) '(a b)))))
         (result (check-invariant system)))
    (%assert-equal :proved (check-result-status result) "cycle result")
    (%assert-equal 2 (check-result-visited result)
                   "EQUAL duplicate detection terminates cycle")))

(defun test-bound-is-not-proof ()
  (let* ((system
           (make-transition-system
            :initial-states '(0)
            :successors (lambda (state)
                          (if (< state 4) (list (1+ state)) '()))
            :invariant (lambda (state) (< state 99))))
         (result (check-invariant system :max-states 2)))
    (%assert-equal :bounded (check-result-status result) "bounded status")
    (%assert-equal 2 (check-result-visited result) "bounded visited")
    (%assert-equal nil (check-result-conclusive-p result)
                   "bounded exploration is explicitly inconclusive")))

(defun test-unknown-successor-relation-is-not-proof ()
  (let* ((system
           (make-transition-system
            :initial-states '(0)
            :successors (lambda (state)
                          (case state
                            (0 '(1))
                            (1 (error 'unknown-successors
                                      :state state
                                      :reason "external transition source unavailable"))
                            (otherwise '())))
            :invariant (constantly t)))
         (result (check-invariant system)))
    (%assert-equal :unknown (check-result-status result) "unknown status")
    (%assert-equal '(0 1) (check-result-trace result) "unknown trace")
    (%assert-equal nil (check-result-conclusive-p result)
                   "unknown exploration is inconclusive")
    (%assert-equal "external transition source unavailable"
                   (check-result-reason result)
                   "unknown reason preserved")))

(defun run-formal-tests ()
  (let ((tests '(test-safe-cycle-is-proved
                 test-violation-has-shortest-counterexample
                 test-unreachable-bad-state-does-not-refute
                 test-cycle-terminates-with-duplicate-state
                 test-bound-is-not-proof
                 test-unknown-successor-relation-is-not-proof))
        (passed 0))
    (dolist (test tests)
      (handler-case
          (progn
            (funcall test)
            (incf passed)
            (format t "PASS ~A~%" test))
        (error (condition)
          (format *error-output* "FAIL ~A: ~A~%" test condition)
          (error condition))))
    (format t "~D/~D formal-methods tests passed.~%" passed (length tests))
    t))
