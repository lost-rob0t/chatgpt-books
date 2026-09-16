(in-package #:cl-user)

(defpackage #:symbolic-ai.pattern.tests
  (:use #:cl #:symbolic-ai.pattern)
  (:export #:run-tests))

(in-package #:symbolic-ai.pattern.tests)

(defvar *tests* '())

(defmacro deftest (name &body body)
  `(progn
     (defun ,name () ,@body)
     (pushnew ',name *tests*)))

(defmacro is (form &optional message)
  `(unless ,form
     (error "Assertion failed: ~S~@[ -- ~A~]" ',form ,message)))

(defmacro is-equal (expected form &key (test ''equal))
  `(let ((actual ,form)
         (wanted ,expected))
     (unless (funcall ,test wanted actual)
       (error "Expected ~S, got ~S from ~S" wanted actual ',form))))

(defun binding-value (name bindings)
  (cdr (assoc name bindings :test #'equal)))

(deftest literal-match-succeeds
  (let ((result (match-pattern '(robot at dock) '(robot at dock))))
    (is (eq :matched (match-result-status result)))
    (is (null (match-result-bindings result)))))

(deftest nested-variable-match-binds-structure
  (let* ((x (make-variable 'x))
         (result (match-pattern `(robot (at ,x)) '(robot (at loading-dock)))))
    (is (eq :matched (match-result-status result)))
    (is-equal 'loading-dock (binding-value 'x (match-result-bindings result)))))

(deftest repeated-variable-must-agree
  (let* ((x (make-variable 'x))
         (ok (match-pattern `(same ,x ,x) '(same a a)))
         (bad (match-pattern `(same ,x ,x) '(same a b))))
    (is (eq :matched (match-result-status ok)))
    (is (eq :failed (match-result-status bad)))
    (is (eq :repeated-variable-clash (match-result-reason bad)))))

(deftest matcher-handles-dotted-conses
  (let* ((tail (make-variable 'tail))
         (result (match-pattern `(a . ,tail) '(a b c))))
    (is (eq :matched (match-result-status result)))
    (is-equal '(b c) (binding-value 'tail (match-result-bindings result)))))

(deftest literal-clash-is-inspectable
  (let ((result (match-pattern '(robot at dock) '(robot at lab))))
    (is (eq :failed (match-result-status result)))
    (is (eq :literal-clash (match-result-reason result)))
    (is-equal 'dock (match-result-pattern result))
    (is-equal 'lab (match-result-datum result))))

(deftest compound-unification-is-symmetric
  (let* ((x (make-variable 'x))
         (y (make-variable 'y))
         (left `(f ,x a))
         (right `(f b ,y))
         (forward (unify left right))
         (reverse (unify right left)))
    (is (eq :unified (unification-result-status forward)))
    (is (eq :unified (unification-result-status reverse)))
    (is-equal '(f b a)
              (apply-substitution left
                                  (unification-result-substitution forward)))
    (is-equal '(f b a)
              (apply-substitution right
                                  (unification-result-substitution reverse)))))

(deftest variable-chains-normalize-through-later-bindings
  (let* ((x (make-variable 'x))
         (y (make-variable 'y))
         (first (unify x y))
         (second (unify y '(g a)
                        :substitution
                        (unification-result-substitution first)))
         (subst (unification-result-substitution second)))
    (is (eq :unified (unification-result-status second)))
    (is-equal '(g a) (binding-value 'x subst))
    (is-equal '(g a) (binding-value 'y subst))
    (is-equal '(pair (g a) (g a))
              (apply-substitution `(pair ,x ,y) subst))))

(deftest occurs-check-rejects-infinite-term
  (let* ((x (make-variable 'x))
         (result (unify x `(f ,x))))
    (is (eq :failed (unification-result-status result)))
    (is (eq :occurs-check (unification-result-reason result)))
    (is-equal x (unification-result-left result))
    (is-equal `(f ,x) (unification-result-right result))))

(deftest functor-or-shape-clash-fails
  (dolist (pair '(((f a) (g a))
                  ((f a b) (f a))
                  (a b)))
    (destructuring-bind (left right) pair
      (let ((result (unify left right)))
        (is (eq :failed (unification-result-status result)))
        (is (eq :clash (unification-result-reason result)))))))

(deftest dotted-terms-unify-structurally
  (let* ((x (make-variable 'x))
         (result (unify `(a . ,x) '(a b c))))
    (is (eq :unified (unification-result-status result)))
    (is-equal '(b c)
              (binding-value 'x
                             (unification-result-substitution result)))))

(deftest unification-does-not-mutate-input-terms
  (let* ((x (make-variable 'x))
         (left `(f ,x (nested a)))
         (right '(f b (nested a)))
         (left-copy (copy-tree left))
         (right-copy (copy-tree right)))
    (unify left right)
    (is-equal left-copy left)
    (is-equal right-copy right)))

(deftest seeded-substitution-is-respected
  (let* ((x (make-variable 'x))
         (result (unify `(pair ,x ,x)
                        '(pair a a)
                        :substitution '((x . a)))))
    (is (eq :unified (unification-result-status result)))
    (is-equal 'a
              (binding-value 'x
                             (unification-result-substitution result)))))

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
    (format t "~%~D passed, ~D failed.~%" passed failed)
    (when (plusp failed)
      (error "Pattern/unification suite failed."))
    t))
