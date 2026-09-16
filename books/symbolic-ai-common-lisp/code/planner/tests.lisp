(in-package #:cl-user)

(defpackage #:symbolic-ai.planner.tests
  (:use #:cl #:symbolic-ai.planner)
  (:export #:run-tests))

(in-package #:symbolic-ai.planner.tests)

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

(defun warehouse-schemas ()
  (let ((from (v 'from))
        (to (v 'to))
        (pkg (v 'pkg))
        (loc (v 'loc)))
    (list
     (make-action-schema
      'pickup
      (list pkg loc)
      `((at robot ,loc) (at ,pkg ,loc) (empty robot))
      `((carrying robot ,pkg))
      `((at ,pkg ,loc) (empty robot)))
     (make-action-schema
      'move
      (list from to)
      `((at robot ,from) (connected ,from ,to))
      `((at robot ,to))
      `((at robot ,from)))
     (make-action-schema
      'drop
      (list pkg loc)
      `((at robot ,loc) (carrying robot ,pkg))
      `((at ,pkg ,loc) (empty robot))
      `((carrying robot ,pkg))))))

(defun warehouse-initial-state ()
  '((at robot dock)
    (at package-17 dock)
    (empty robot)
    (connected dock hall)
    (connected hall office)))

(defun warehouse-goals ()
  '((at package-17 office)))

(deftest canonical-state-is-set-like-and-deterministic
  (let ((left (canonical-state '((z 2) (a 1) (z 2))))
        (right (canonical-state '((a 1) (z 2)))))
    (is-equal right left)
    (is (= 2 (length left)))))

(deftest planning-boundary-rejects-ungrounded-world-facts
  (let ((x (v 'x)))
    (signals ungrounded-world-fact
      (make-planning-problem `((at robot ,x))
                             '((at robot dock))
                             '()))
    (signals ungrounded-world-fact
      (make-planning-problem '((at robot dock))
                             `((at robot ,x))
                             '()))))

(deftest exported-instantiation-rejects-ungrounded-world-facts
  (let* ((x (v 'x))
         (loc (v 'loc))
         (schema (make-action-schema
                  'inspect
                  (list loc)
                  `((at robot ,loc))
                  `((inspected ,loc))
                  '())))
    (signals ungrounded-world-fact
      (instantiate-applicable-actions schema `((at robot ,x))))))

(deftest repeated-variable-bindings-must-be-consistent
  (let* ((x (v 'x))
         (schema (make-action-schema
                  'inspect
                  (list x)
                  `((at ,x room) (tag ,x heavy))
                  `((inspected ,x))
                  '())))
    (is (null (instantiate-applicable-actions
               schema
               '((at crate room) (tag other heavy)))))
    (let ((actions (instantiate-applicable-actions
                    schema
                    '((at crate room) (tag crate heavy)))))
      (is (= 1 (length actions)))
      (is-equal '(inspect crate) (ground-action-name (first actions))))))

(deftest delete-effects-run-before-add-effects
  (let* ((schema (make-action-schema
                  'refresh
                  '()
                  '((flag ready))
                  '((flag ready) (audit refreshed))
                  '((flag ready))))
         (state '((flag ready)))
         (action (first (instantiate-applicable-actions schema state)))
         (next (apply-ground-action state action)))
    (is (member '(flag ready) next :test #'equal))
    (is (member '(audit refreshed) next :test #'equal))
    (is (= 2 (length next)))))

(deftest unbound-effect-variable-fails-before-state-mutation
  (let* ((x (v 'x))
         (schema (make-action-schema
                  'invent
                  (list x)
                  '()
                  `((exists ,x))
                  '())))
    (signals ungrounded-action
      (instantiate-applicable-actions schema '()))))

(deftest warehouse-plan-composes-bindings-search-and-effects
  (let ((result (solve-plan
                 (warehouse-initial-state)
                 (warehouse-goals)
                 (warehouse-schemas)
                 :algorithm :breadth-first)))
    (is (eq :found (symbolic-ai.search:search-result-status result)))
    (is-equal '((pickup package-17 dock)
                (move dock hall)
                (move hall office)
                (drop package-17 office))
              (symbolic-ai.search:search-result-actions result))
    (is (= 4 (symbolic-ai.search:search-result-cost result)))
    (is (goal-satisfied-p
         (car (last (symbolic-ai.search:search-result-path result)))
         (warehouse-goals)))))

(deftest unreachable-goal-returns-not-found
  (let ((result (solve-plan
                 (warehouse-initial-state)
                 '((at package-17 moon))
                 (warehouse-schemas)
                 :algorithm :breadth-first)))
    (is (eq :not-found (symbolic-ai.search:search-result-status result)))
    (is (null (symbolic-ai.search:search-result-actions result)))))

(deftest uniform-cost-search-honors-action-costs
  (let* ((direct
           (make-action-schema
            'direct '()
            '((at robot a))
            '((at robot c))
            '((at robot a))
            :cost 10))
         (step-ab
           (make-action-schema
            'step-ab '()
            '((at robot a))
            '((at robot b))
            '((at robot a))
            :cost 2))
         (step-bc
           (make-action-schema
            'step-bc '()
            '((at robot b))
            '((at robot c))
            '((at robot b))
            :cost 2))
         (result
           (solve-plan '((at robot a))
                       '((at robot c))
                       (list direct step-ab step-bc)
                       :algorithm :uniform-cost)))
    (is-equal '((step-ab) (step-bc))
              (symbolic-ai.search:search-result-actions result))
    (is (= 4 (symbolic-ai.search:search-result-cost result)))))

(deftest canonical-state-merges-equivalent-successors
  (let* ((make-b
           (make-action-schema
            'make-b '()
            '((at robot a))
            '((flag ready) (at robot b))
            '((at robot a))))
         (make-b-reordered
           (make-action-schema
            'make-b-reordered '()
            '((at robot a))
            '((at robot b) (flag ready) (flag ready))
            '((at robot a))))
         (finish
           (make-action-schema
            'finish '()
            '((at robot b) (flag ready))
            '((done))
            '()))
         (result
           (solve-plan '((at robot a))
                       '((done))
                       (list make-b make-b-reordered finish)
                       :algorithm :breadth-first)))
    (is (eq :found (symbolic-ai.search:search-result-status result)))
    (is (plusp (symbolic-ai.search:search-result-duplicate-pruned result)))))

(deftest hmax-relaxation-is-inspectable-on-warehouse
  (let* ((analysis
           (analyze-hmax-relaxation
            (warehouse-initial-state)
            (warehouse-goals)
            (warehouse-schemas)))
         (support
           (cdr (assoc '(at package-17 office)
                       (relaxed-analysis-supports analysis)
                       :test #'equal))))
    (is (eq :reached (relaxed-analysis-status analysis)))
    (is (= 3 (relaxed-analysis-estimate analysis)))
    (is support)
    (is (eq :action (relaxed-support-source support)))
    (is-equal '(drop package-17 office)
              (relaxed-support-action-name support))))

(deftest hmax-is-a-lower-bound-on-controlled-warehouse-path
  (let* ((schemas (warehouse-schemas))
         (goals (warehouse-goals))
         (optimal
           (solve-plan (warehouse-initial-state)
                       goals
                       schemas
                       :algorithm :uniform-cost)))
    (is (= 4 (symbolic-ai.search:search-result-cost optimal)))
    (dolist (state (symbolic-ai.search:search-result-path optimal))
      (let* ((analysis (analyze-hmax-relaxation state goals schemas))
             (remaining (solve-plan state goals schemas :algorithm :uniform-cost)))
        (is (eq :reached (relaxed-analysis-status analysis)))
        (is (eq :found (symbolic-ai.search:search-result-status remaining)))
        (is (<= (relaxed-analysis-estimate analysis)
                (symbolic-ai.search:search-result-cost remaining)))))))

(deftest a-star-with-hmax-preserves-optimal-cost-on-warehouse
  (let* ((schemas (warehouse-schemas))
         (goals (warehouse-goals))
         (result
           (solve-plan
            (warehouse-initial-state)
            goals
            schemas
            :algorithm :a-star
            :heuristic (make-hmax-heuristic goals schemas))))
    (is (eq :found (symbolic-ai.search:search-result-status result)))
    (is (= 4 (symbolic-ai.search:search-result-cost result)))))

(deftest relaxed-fixpoint-distinguishes-unreachable-from-bounded
  (let ((unreachable
          (analyze-hmax-relaxation
           (warehouse-initial-state)
           '((at package-17 moon))
           (warehouse-schemas))))
    (is (eq :unreachable (relaxed-analysis-status unreachable)))
    (is (null (relaxed-analysis-estimate unreachable))))
  (let* ((x (v 'x))
         (grow
           (make-action-schema
            'grow
            (list x)
            `((seed ,x))
            `((seed (next ,x)))
            '()))
         (bounded
           (analyze-hmax-relaxation
            '((seed zero))
            '((done))
            (list grow)
            :max-iterations 3)))
    (is (eq :bounded (relaxed-analysis-status bounded)))
    (is (null (relaxed-analysis-estimate bounded)))))

(deftest plan-explanation-replays-every-ground-transition
  (let* ((schemas (warehouse-schemas))
         (result
           (solve-plan (warehouse-initial-state)
                       (warehouse-goals)
                       schemas
                       :algorithm :breadth-first))
         (steps (explain-plan-result schemas result)))
    (is (= 4 (length steps)))
    (is-equal '(pickup package-17 dock)
              (plan-step-explanation-action-name (first steps)))
    (is-equal 'pickup (plan-step-explanation-schema-name (first steps)))
    (is (member '(carrying robot package-17)
                (plan-step-explanation-add-effects (first steps))
                :test #'equal))
    (loop
      for step in steps
      for expected-before in (symbolic-ai.search:search-result-path result)
      for expected-after in (rest (symbolic-ai.search:search-result-path result))
      do (is-equal expected-before
                   (plan-step-explanation-before-state step))
         (is-equal expected-after
                   (plan-step-explanation-after-state step)))))

(deftest plan-explanation-refuses-ambiguous-provenance
  (let* ((first
           (make-action-schema 'finish '() '((ready)) '((done)) '()))
         (second
           (make-action-schema 'finish '() '((ready)) '((done)) '()))
         (schemas (list first second))
         (result
           (solve-plan '((ready)) '((done)) schemas :algorithm :breadth-first)))
    (is (eq :found (symbolic-ai.search:search-result-status result)))
    (signals ambiguous-plan-step
      (explain-plan-result schemas result))))

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
    (format t "~%Planner tests: ~D passed, ~D failed.~%" passed failed)
    (when (plusp failed)
      (error "Planner test failures: ~D" failed))
    passed))
