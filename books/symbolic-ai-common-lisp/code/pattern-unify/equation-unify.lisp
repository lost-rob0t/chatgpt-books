(in-package #:symbolic-ai.pattern)

(defstruct (%equation
            (:constructor %make-equation (left right)))
  left
  right)

(defstruct unification-step
  action
  left
  right
  substitution
  pending-count
  reason)

(defun unify-equations (left right &key (substitution '()))
  "Unify LEFT and RIGHT through an explicit equation worklist.

This is an independently structured teaching/validation path for the same finite
acyclic first-order term contract as UNIFY.  It returns two values: a normal
UNIFICATION-RESULT and a chronological list of UNIFICATION-STEP records.

The selected equation is rewritten through the current substitution before each
step.  Successful variable elimination is represented lazily: a new binding is
added to the substitution and later equations are rewritten when selected.
Caller terms and the caller-supplied substitution are never destructively
modified."
  (let ((pending (list (%make-equation left right)))
        (environment substitution)
        (steps '()))
    (labels ((record-step (action step-left step-right &key reason)
               (push (make-unification-step
                      :action action
                      :left step-left
                      :right step-right
                      :substitution (copy-tree environment)
                      :pending-count (length pending)
                      :reason reason)
                     steps))
             (success-result ()
               (make-unification-result
                :status :unified
                :substitution (normalize-substitution environment)))
             (failure-result (reason bad-left bad-right)
               ;; Match UNIFY's failure contract: partial bindings are useful in
               ;; the trace, but the result does not expose a half-completed
               ;; substitution as if it were a solution.
               (make-unification-result
                :status :failed
                :substitution substitution
                :reason reason
                :left bad-left
                :right bad-right)))
      (loop while pending
            for equation = (pop pending)
            for a = (apply-substitution (%equation-left equation) environment)
            for b = (apply-substitution (%equation-right equation) environment)
            do (cond
                 ((equal a b)
                  (record-step :delete a b))

                 ((variable-p a)
                  (if (%occurs-p a b environment)
                      (progn
                        (record-step :occurs-check a b :reason :occurs-check)
                        (return-from unify-equations
                          (values (failure-result :occurs-check a b)
                                  (nreverse steps))))
                      (progn
                        (setf environment
                              (acons (variable-name a) b environment))
                        (record-step :bind a b))))

                 ((variable-p b)
                  ;; Orientation is deliberately visible instead of silently
                  ;; folding the symmetric case into BIND.
                  (push (%make-equation b a) pending)
                  (record-step :orient a b))

                 ((and (consp a) (consp b))
                  ;; PENDING is a stack.  Push CDR first so CAR is selected
                  ;; next, matching the recursive implementation's left-to-right
                  ;; teaching trace.
                  (push (%make-equation (cdr a) (cdr b)) pending)
                  (push (%make-equation (car a) (car b)) pending)
                  (record-step :decompose a b))

                 (t
                  (record-step :clash a b :reason :clash)
                  (return-from unify-equations
                    (values (failure-result :clash a b)
                            (nreverse steps))))))
      (values (success-result)
              (nreverse steps)))))
