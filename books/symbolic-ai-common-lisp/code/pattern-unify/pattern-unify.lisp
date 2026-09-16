(in-package #:symbolic-ai.pattern)

(defconstant +variable-tag+ :var)

(defun make-variable (name)
  "Return the reserved two-element representation for a symbolic variable."
  (list +variable-tag+ name))

(defun variable-p (term)
  "True when TERM has the reserved variable shape (:VAR NAME)."
  (and (consp term)
       (eq (car term) +variable-tag+)
       (consp (cdr term))
       (null (cddr term))))

(defun variable-name (term)
  "Return TERM's variable name, rejecting non-variable terms."
  (unless (variable-p term)
    (error "Not a symbolic variable: ~S" term))
  (second term))

(defstruct match-result
  status
  bindings
  reason
  pattern
  datum)

(defstruct unification-result
  status
  substitution
  reason
  left
  right)

(defun %binding (variable substitution)
  (assoc (variable-name variable) substitution :test #'equal))

(defun %walk (term substitution)
  "Follow top-level variable bindings until TERM is unbound or non-variable."
  (loop
    with current = term
    with seen = (make-hash-table :test #'equal)
    while (variable-p current)
    for name = (variable-name current)
    for binding = (%binding current substitution)
    do (cond
         ((null binding)
          (return current))
         ((gethash name seen)
          (error "Cyclic substitution while walking ~S" term))
         (t
          (setf (gethash name seen) t
                current (cdr binding))))
    finally (return current)))

(defun apply-substitution (term substitution)
  "Recursively apply SUBSTITUTION to finite acyclic TERM.

SUBSTITUTION is an alist from variable names to terms.  Substitutions produced by
UNIFY satisfy the occurs check; arbitrary cyclic substitutions supplied by a
caller are rejected rather than interpreted as rational trees."
  (labels ((rewrite (value active)
             (cond
               ((variable-p value)
                (let* ((name (variable-name value))
                       (binding (%binding value substitution)))
                  (if (null binding)
                      value
                      (progn
                        (when (member name active :test #'equal)
                          (error "Cyclic substitution while rewriting ~S" term))
                        (rewrite (cdr binding) (cons name active))))))
               ((consp value)
                (cons (rewrite (car value) active)
                      (rewrite (cdr value) active)))
               (t value))))
    (rewrite term '())))

(defun normalize-substitution (substitution)
  "Return a fresh substitution whose right-hand sides are fully rewritten."
  (mapcar (lambda (binding)
            (cons (car binding)
                  (apply-substitution (cdr binding) substitution)))
          substitution))

(defun match-pattern (pattern datum &key (bindings '()))
  "Match directional PATTERN against literal DATUM.

Variables are recognized only in PATTERN. Existing BINDINGS may seed the
match. The result status is :MATCHED or :FAILED."
  (labels ((match* (p d env)
             (cond
               ((variable-p p)
                (let ((binding (%binding p env)))
                  (cond
                    ((null binding)
                     (values (acons (variable-name p) d env)
                             t nil p d))
                    ((equal (cdr binding) d)
                     (values env t nil p d))
                    (t
                     (values env nil :repeated-variable-clash p d)))))
               ((consp p)
                (if (consp d)
                    (multiple-value-bind (env-1 ok reason left right)
                        (match* (car p) (car d) env)
                      (if ok
                          (match* (cdr p) (cdr d) env-1)
                          (values env-1 nil reason left right)))
                    (values env nil :shape-clash p d)))
               ((equal p d)
                (values env t nil nil nil))
               (t
                (values env nil :literal-clash p d)))))
    (multiple-value-bind (result-bindings ok reason left right)
        (match* pattern datum bindings)
      (if ok
          ;; Matcher right-hand sides are literal datum.  Do not feed them
          ;; through unifier substitution semantics merely because a datum
          ;; happens to have the reserved (:VAR NAME) shape.
          (make-match-result :status :matched
                             :bindings result-bindings)
          (make-match-result :status :failed
                             :bindings bindings
                             :reason reason
                             :pattern left
                             :datum right)))))

(defun %occurs-p (variable term substitution)
  "True when VARIABLE occurs in TERM after following current bindings."
  (let ((target (variable-name variable)))
    (labels ((occurs* (value active)
               (let ((walked (%walk value substitution)))
                 (cond
                   ((variable-p walked)
                    (let ((name (variable-name walked)))
                      (cond
                        ((equal target name) t)
                        ((member name active :test #'equal) nil)
                        (t
                         (let ((binding (%binding walked substitution)))
                           (and binding
                                (occurs* (cdr binding)
                                         (cons name active))))))))
                   ((consp walked)
                    (or (occurs* (car walked) active)
                        (occurs* (cdr walked) active)))
                   (t nil)))))
      (occurs* term '()))))

(defun unify (left right &key (substitution '()))
  "Unify finite acyclic first-order terms LEFT and RIGHT.

Variables use the reserved (:VAR NAME) representation. The occurs check is
mandatory in this milestone. The result status is :UNIFIED or :FAILED; on
failure REASON is :OCCURS-CHECK or :CLASH and LEFT/RIGHT identify the pair
that could not be unified."
  (labels ((bind-variable (variable term env)
             (let ((walked-term (%walk term env)))
               (cond
                 ((equal variable walked-term)
                  (values env t nil nil nil))
                 ((%occurs-p variable walked-term env)
                  (values env nil :occurs-check variable walked-term))
                 (t
                  (values (acons (variable-name variable)
                                 walked-term
                                 env)
                          t nil nil nil)))))
           (unify* (x y env)
             (let ((a (%walk x env))
                   (b (%walk y env)))
               (cond
                 ((equal a b)
                  (values env t nil nil nil))
                 ((variable-p a)
                  (bind-variable a b env))
                 ((variable-p b)
                  (bind-variable b a env))
                 ((and (consp a) (consp b))
                  (multiple-value-bind (env-1 ok reason bad-left bad-right)
                      (unify* (car a) (car b) env)
                    (if ok
                        (unify* (cdr a) (cdr b) env-1)
                        (values env-1 nil reason bad-left bad-right))))
                 (t
                  (values env nil :clash a b))))))
    (multiple-value-bind (result-substitution ok reason bad-left bad-right)
        (unify* left right substitution)
      (if ok
          (make-unification-result
           :status :unified
           :substitution (normalize-substitution result-substitution))
          (make-unification-result
           :status :failed
           :substitution substitution
           :reason reason
           :left bad-left
           :right bad-right)))))
