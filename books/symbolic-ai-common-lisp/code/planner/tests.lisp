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

(deftest canonical-state-is-set-like-and-deterministic
  (let ((left (canonical-state '((z 2) (a 1) (z 2))))
        (right (canonical-state '((a 1) (z 2)))))
    (is-equal right left)
    (is (= 2 (length left)))))

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
  (let* ((from (v 'from))
         (to (v 'to))
         (schema (make-action-schema
                  'move
                  (list from to)
                  `((at robot ,from) (connected ,from ,to))
                  `((at robot ,to))
                  `((at robot ,from))))
         (state '((at robot dock) (connected dock hall)))
         (action (first (instantiate-applicable-actions schema state)))
         (next (apply-ground-action state action)))
    (is (member '(at robot hall) next :test #'equal))
    (is (not (member '(at robot dock) next :test #'equal)))
    (is (member '(connected dock hall) next :test #'equal))))

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
                 '((at package-17 office))
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
         '((at package-17 office))))))

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
