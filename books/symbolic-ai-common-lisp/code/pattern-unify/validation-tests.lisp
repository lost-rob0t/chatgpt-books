(in-package #:symbolic-ai.pattern.tests)

(defun %step-actions (steps)
  (mapcar #'unification-step-action steps))

(defun %assert-success-contract (label left right result)
  (when (eq :unified (unification-result-status result))
    (let* ((substitution (unification-result-substitution result))
           (left-once (apply-substitution left substitution))
           (right-once (apply-substitution right substitution))
           (left-twice (apply-substitution left-once substitution))
           (right-twice (apply-substitution right-once substitution)))
      (unless (equal left-once right-once)
        (error "~A returned a substitution that does not equalize ~S and ~S: ~S"
               label left right substitution))
      (unless (equal left-once left-twice)
        (error "~A substitution is not idempotent on left source term ~S: ~S"
               label left substitution))
      (unless (equal right-once right-twice)
        (error "~A substitution is not idempotent on right source term ~S: ~S"
               label right substitution))
      (dolist (binding substitution)
        (unless (equal (cdr binding)
                       (apply-substitution (cdr binding) substitution))
          (error "~A returned a non-normalized right-hand side ~S in ~S"
                 label binding substitution))))))

(defun %rename-variables (term mapping)
  (cond
    ((variable-p term)
     (let ((entry (assoc (variable-name term) mapping :test #'equal)))
       (if entry
           (make-variable (cdr entry))
           term)))
    ((consp term)
     (cons (%rename-variables (car term) mapping)
           (%rename-variables (cdr term) mapping)))
    (t term)))

(defun %bounded-unification-terms ()
  (let* ((x (make-variable 'x))
         (y (make-variable 'y))
         (base (list 'a 'b x y))
         (unary (mapcar (lambda (term) `(f ,term)) base))
         (binary (loop for left in base
                       append (loop for right in base
                                    collect `(p ,left ,right)))))
    (append base unary binary)))

(deftest equation-worklist-exposes-rewrite-actions
  (let* ((x (make-variable 'x))
         (y (make-variable 'y)))
    (multiple-value-bind (result steps)
        (unify-equations `(f a ,x) `(f ,y b))
      (is (eq :unified (unification-result-status result)))
      (is-equal 'a
                (binding-value 'y
                               (unification-result-substitution result)))
      (is-equal 'b
                (binding-value 'x
                               (unification-result-substitution result)))
      (let ((actions (%step-actions steps)))
        (is (member :decompose actions))
        (is (member :delete actions))
        (is (member :orient actions))
        (is (member :bind actions))))))

(deftest equation-worklist-occurs-check-is-visible
  (let ((x (make-variable 'x)))
    (multiple-value-bind (result steps)
        (unify-equations x `(f ,x))
      (is (eq :failed (unification-result-status result)))
      (is (eq :occurs-check (unification-result-reason result)))
      (is-equal '(:occurs-check) (%step-actions steps))
      (is (eq :occurs-check (unification-step-reason (car steps)))))))

(deftest equation-worklist-keeps-partial-bindings-in-trace-only
  (let ((x (make-variable 'x)))
    (multiple-value-bind (result steps)
        (unify-equations `(p ,x ,x) '(p a b))
      (is (eq :failed (unification-result-status result)))
      (is (eq :clash (unification-result-reason result)))
      (is (null (unification-result-substitution result)))
      (let ((bind-step (find :bind steps :key #'unification-step-action)))
        (is bind-step)
        (is-equal 'a
                  (binding-value 'x
                                 (unification-step-substitution bind-step))))
      (is (eq :clash
              (unification-step-action (car (last steps))))))))

(deftest equation-worklist-respects-seeded-substitution
  (let ((x (make-variable 'x)))
    (multiple-value-bind (result steps)
        (unify-equations `(pair ,x ,x)
                         '(pair a a)
                         :substitution '((x . a)))
      (declare (ignore steps))
      (is (eq :unified (unification-result-status result)))
      (is-equal 'a
                (binding-value 'x
                               (unification-result-substitution result))))))

(deftest bounded-generated-unifiers-agree-and-preserve-metamorphic-contracts
  (let ((terms (%bounded-unification-terms))
        (renaming '((x . fresh-x)
                    (y . fresh-y))))
    (dolist (left terms)
      (dolist (right terms)
        (let* ((recursive (unify left right))
               (reverse-result (unify right left))
               (renamed-left (%rename-variables left renaming))
               (renamed-right (%rename-variables right renaming))
               (renamed-result (unify renamed-left renamed-right)))
          (unless (eq (unification-result-status recursive)
                      (unification-result-status reverse-result))
            (error "Unification success/failure changed under side reversal: ~S vs ~S"
                   left right))
          (unless (eq (unification-result-status recursive)
                      (unification-result-status renamed-result))
            (error "Unification success/failure changed under fresh renaming: ~S vs ~S"
                   left right))
          (%assert-success-contract :recursive left right recursive)
          (%assert-success-contract :reverse right left reverse-result)
          (%assert-success-contract :renamed renamed-left renamed-right renamed-result)

          (when (eq :unified (unification-result-status recursive))
            (let* ((original-common
                     (apply-substitution
                      left
                      (unification-result-substitution recursive)))
                   (renamed-common
                     (apply-substitution
                      renamed-left
                      (unification-result-substitution renamed-result))))
              (unless (equal (%rename-variables original-common renaming)
                             renamed-common)
                (error "Fresh renaming changed the common instance for ~S vs ~S"
                       left right))))

          (multiple-value-bind (worklist steps)
              (unify-equations left right)
            (declare (ignore steps))
            (unless (eq (unification-result-status recursive)
                        (unification-result-status worklist))
              (error "Recursive/worklist status disagreement for ~S vs ~S"
                     left right))
            (%assert-success-contract :worklist left right worklist)))))))
