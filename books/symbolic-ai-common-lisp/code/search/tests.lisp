(in-package #:cl-user)

(defpackage #:symbolic-ai.search.tests
  (:use #:cl #:symbolic-ai.search)
  (:export #:run-tests))

(in-package #:symbolic-ai.search.tests)

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

(defun edge (state action &optional (cost 1))
  (make-transition state :action action :cost cost))

(defun table-successors (table)
  (lambda (state)
    (copy-list (cdr (assoc state table :test #'equal)))))

(defun goal-is (goal)
  (lambda (state) (equal state goal)))

(defun problem-from-table (start goal table &key (heuristic (constantly 0)))
  (make-problem start
                (goal-is goal)
                (table-successors table)
                :heuristic heuristic))

(deftest breadth-first-finds-shortest-edge-count-path
  (let* ((table `((s ,(edge 'a :s-a) ,(edge 'b :s-b))
                  (a ,(edge 'g :a-g))
                  (b ,(edge 'c :b-c))
                  (c ,(edge 'g :c-g))))
         (result (breadth-first-search
                  (problem-from-table 's 'g table))))
    (is (eq :found (search-result-status result)))
    (is-equal '(s a g) (search-result-path result))
    (is-equal '(:s-a :a-g) (search-result-actions result))
    (is (= 2 (search-result-cost result)))
    (is (plusp (search-result-expanded result)))))

(deftest unreachable-goal-terminates-with-cycle
  (let* ((table `((s ,(edge 'a :s-a))
                  (a ,(edge 'b :a-b))
                  (b ,(edge 's :b-s))))
         (result (breadth-first-search
                  (problem-from-table 's 'missing table))))
    (is (eq :not-found (search-result-status result)))
    (is (null (search-result-path result)))
    (is (= 3 (search-result-expanded result)))
    (is (= 1 (search-result-duplicate-pruned result)))))

(deftest dfs-and-bfs-have-different-deterministic-frontier-orders
  (let* ((table `((s ,(edge 'a :s-a) ,(edge 'b :s-b))
                  (a ,(edge 'c :a-c))
                  (c ,(edge 'g :c-g))
                  (b ,(edge 'g :b-g))))
         (problem (problem-from-table 's 'g table))
         (dfs (depth-first-search problem))
         (bfs (breadth-first-search problem)))
    (is-equal '(s a c g) (search-result-path dfs))
    (is-equal '(s b g) (search-result-path bfs))))

(deftest uniform-cost-prefers-cheaper-longer-path
  (let* ((table `((s ,(edge 'g :direct 10) ,(edge 'a :s-a 2))
                  (a ,(edge 'b :a-b 2))
                  (b ,(edge 'g :b-g 2))))
         (result (uniform-cost-search
                  (problem-from-table 's 'g table))))
    (is-equal '(s a b g) (search-result-path result))
    (is-equal '(:s-a :a-b :b-g) (search-result-actions result))
    (is (= 6 (search-result-cost result)))))

(deftest a-star-uses-heuristic-without-changing-optimal-answer
  (let* ((table `((s ,(edge 'g :direct 10) ,(edge 'a :s-a 2))
                  (a ,(edge 'b :a-b 2))
                  (b ,(edge 'g :b-g 2))))
         (estimates '((s . 6) (a . 4) (b . 2) (g . 0)))
         (heuristic (lambda (state) (cdr (assoc state estimates))))
         (result (a-star-search
                  (problem-from-table 's 'g table :heuristic heuristic))))
    (is-equal '(s a b g) (search-result-path result))
    (is (= 6 (search-result-cost result)))
    (is (< (search-result-expanded result) 4))))

(deftest a-star-reopens-a-state-for-an-admissible-inconsistent-heuristic
  (let* ((table `((s ,(edge 'a :slow-a 3) ,(edge 'b :s-b 1))
                  (b ,(edge 'a :fast-a 1))
                  (a ,(edge 'g :a-g 10))))
         ;; True remaining costs are S=12, B=11, A=10, G=0.  B's
         ;; estimate is admissible but inconsistent across B -> A because
         ;; 10 > 1 + 0.  A is therefore expanded once at g=3 and must be
         ;; reopened when B later discovers A at g=2.
         (estimates '((s . 0) (a . 0) (b . 10) (g . 0)))
         (heuristic (lambda (state) (cdr (assoc state estimates))))
         (result (a-star-search
                  (problem-from-table 's 'g table :heuristic heuristic))))
    (is-equal '(s b a g) (search-result-path result))
    (is (= 12 (search-result-cost result)))
    (is (= 4 (search-result-expanded result)))))

(deftest cheaper-rediscovery-leaves-a-stale-frontier-entry
  (let* ((table `((s ,(edge 'a :slow-a 5) ,(edge 'b :s-b 1))
                  (b ,(edge 'a :fast-a 1))
                  (a ,(edge 'g :a-g 10))))
         (result (uniform-cost-search
                  (problem-from-table 's 'g table))))
    (is-equal '(s b a g) (search-result-path result))
    (is (= 12 (search-result-cost result)))
    (is (= 1 (search-result-stale-popped result)))))

(deftest equal-structural-keys-prune-fresh-list-duplicates
  (let* ((successors
           (lambda (state)
             (cond
               ((equal state '(at s))
                (list (edge (list 'at 'a) :move-a)))
               ((equal state '(at a))
                (list (edge (list 'at 's) :back-s)
                      (edge (list 'at 'g) :move-g)))
               (t nil))))
         (problem (make-problem (list 'at 's)
                                (lambda (state) (equal state '(at g)))
                                successors))
         (result (breadth-first-search problem)))
    (is-equal '((at s) (at a) (at g)) (search-result-path result))
    (is (= 1 (search-result-duplicate-pruned result)))))

(deftest negative-step-cost-is-rejected-before-use
  (let* ((table `((s ,(edge 'g :bad -1))))
         (problem (problem-from-table 's 'g table)))
    (signals invalid-step-cost
      (uniform-cost-search problem))))

(deftest invalid-heuristic-is-rejected
  (let ((problem
          (make-problem 's
                        (goal-is 'g)
                        (lambda (state)
                          (declare (ignore state))
                          (list (edge 'g :go)))
                        :heuristic (lambda (state)
                                     (declare (ignore state))
                                     :unknown))))
    (signals invalid-heuristic-value
      (a-star-search problem)))
  (let ((problem
          (make-problem 's
                        (goal-is 'g)
                        (lambda (state)
                          (declare (ignore state))
                          (list (edge 'g :go)))
                        :heuristic (lambda (state)
                                     (declare (ignore state))
                                     -1))))
    (signals invalid-heuristic-value
      (a-star-search problem))))

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
    (format t "~%~D passed; ~D failed.~%" passed failed)
    (when (plusp failed)
      (error "Search test suite failed with ~D failure~:P." failed))
    t))
