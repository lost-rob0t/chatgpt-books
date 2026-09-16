(in-package #:expert-systems.matcher)

(defstruct fact
  "One working datum at this stage of the course.

ID is stable within the teaching corpus. RELATION names the predicate-like
shape. ARGUMENTS are ordinary Common Lisp data. PROVENANCE is opaque to the
matcher; later chapters will give it stronger structure."
  id
  relation
  arguments
  provenance)

(defstruct match-result
  "A successful multi-condition match.

BINDINGS is an ordered association list mapping pattern variables to values.
FACT-IDS records which facts supplied the successful conditions, in condition
order."
  bindings
  fact-ids)

(defun variable-p (term)
  "Return true when TERM is a matcher variable such as ?SERVICE."
  (and (symbolp term)
       (> (length (symbol-name term)) 1)
       (char= (char (symbol-name term) 0) #\?)))

(defun literal-condition-match-p (condition fact)
  "Match CONDITION against FACT without variables.

This is intentionally the smallest useful matcher. It is retained after the
variable matcher exists because later chapters use it as a semantic baseline."
  (and (consp condition)
       (equal (first condition) (fact-relation fact))
       (equal (rest condition) (fact-arguments fact))))

(defun extend-binding (variable value bindings)
  "Extend BINDINGS with VARIABLE=VALUE without mutating prior bindings.

Returns two values: the resulting bindings and whether the extension is
consistent. Repeated variables must agree with their earlier value."
  (let ((existing (assoc variable bindings :test #'eq)))
    (cond
      (existing
       (if (equal (cdr existing) value)
           (values bindings t)
           (values nil nil)))
      (t
       (values (append bindings (list (cons variable value))) t)))))

(defun match-condition (condition fact &optional (bindings '()))
  "Match one CONDITION against FACT under existing BINDINGS.

A condition is `(relation field ...)`. Pattern variables are symbols whose
names begin with `?`. Literal fields compare with EQUAL. Returns two values:
the extended bindings and a success flag."
  (unless (and (consp condition)
               (equal (first condition) (fact-relation fact))
               (= (length (rest condition))
                  (length (fact-arguments fact))))
    (return-from match-condition (values nil nil)))
  (let ((current bindings))
    (loop for pattern-field in (rest condition)
          for fact-field in (fact-arguments fact)
          do (if (variable-p pattern-field)
                 (multiple-value-bind (next consistent-p)
                     (extend-binding pattern-field fact-field current)
                   (unless consistent-p
                     (return-from match-condition (values nil nil)))
                   (setf current next))
                 (unless (equal pattern-field fact-field)
                   (return-from match-condition (values nil nil)))))
    (values current t)))

(defun match-conditions (conditions facts &key (initial-bindings '()))
  "Return every deterministic match of CONDITIONS over FACTS.

This is deliberately a naive left-to-right nested-loop join. Every condition
is compared with the complete fact sequence. The implementation therefore
provides a correctness oracle for the incremental matcher derived later in the
book; it is not presented as RETE.

Results preserve condition order, fact order, and first-binding order. A fact
may satisfy more than one condition unless the rule language expresses an
additional distinctness constraint in a later chapter."
  (labels ((extend (remaining bindings fact-ids)
             (if (endp remaining)
                 (list (make-match-result :bindings bindings
                                          :fact-ids fact-ids))
                 (loop for fact in facts
                       append
                       (multiple-value-bind (next-bindings matched-p)
                           (match-condition (first remaining) fact bindings)
                         (if matched-p
                             (extend (rest remaining)
                                     next-bindings
                                     (append fact-ids (list (fact-id fact))))
                             '()))))))
    (extend conditions initial-bindings '())))
