(in-package #:expert-systems.matcher)

;;;; Milestone B is intentionally a transparent semantic engine. It recomputes
;;;; production matches from working memory each cycle; incremental RETE-like
;;;; propagation remains a later optimization target.

(defstruct (working-memory (:constructor %make-working-memory))
  (facts '())
  (assertion-sequences '())
  (known-ids '())
  (next-sequence 0))

(defun valid-stable-id-p (id)
  (and (stringp id) (> (length id) 0)))

(defun ensure-fact-id (fact)
  (unless (valid-stable-id-p (fact-id fact))
    (error "Fact ID must be a non-empty string, got ~S" (fact-id fact))))

(defun make-working-memory (&optional facts)
  "Create mutable working memory and assert FACTS in the supplied order.

Fact identity is session-stable: once an ID has been used, retraction does not
make that ID reusable. Equal fact content is allowed under different IDs because
content equality does not establish observation identity."
  (let ((memory (%make-working-memory)))
    (dolist (fact facts memory)
      (assert-fact memory fact))))

(defun facts-in-working-memory (memory)
  "Return a fresh list of the currently active fact records."
  (copy-list (working-memory-facts memory)))

(defun fact-assertion-sequence (memory fact-id)
  "Return FACT-ID's active assertion sequence, or NIL when it is not active."
  (cdr (assoc fact-id (working-memory-assertion-sequences memory)
              :test #'string=)))

(defun assert-fact (memory fact)
  "Assert FACT and return its monotonic assertion sequence.

Duplicate content is permitted. Duplicate stable IDs, including IDs of facts
that were retracted earlier in this working-memory lifetime, are rejected."
  (ensure-fact-id fact)
  (when (member (fact-id fact) (working-memory-known-ids memory)
                :test #'string=)
    (error "Fact ID ~S has already been used in this working memory"
           (fact-id fact)))
  (let ((sequence (incf (working-memory-next-sequence memory))))
    (setf (working-memory-facts memory)
          (append (working-memory-facts memory) (list fact))
          (working-memory-assertion-sequences memory)
          (append (working-memory-assertion-sequences memory)
                  (list (cons (fact-id fact) sequence)))
          (working-memory-known-ids memory)
          (append (working-memory-known-ids memory) (list (fact-id fact))))
    sequence))

(defun retract-fact (memory fact-id)
  "Retract FACT-ID and return the removed fact, or NIL if it is not active.

The stable ID remains consumed. Re-observing equal content therefore requires a
new ID, which also gives refraction an unambiguous new support identity."
  (let ((fact (find fact-id (working-memory-facts memory)
                    :key #'fact-id :test #'string=)))
    (when fact
      (setf (working-memory-facts memory)
            (remove fact-id (working-memory-facts memory)
                    :key #'fact-id :test #'string= :count 1)
            (working-memory-assertion-sequences memory)
            (remove fact-id (working-memory-assertion-sequences memory)
                    :key #'car :test #'string= :count 1))
      fact)))

(defstruct production
  "A course-local production with structured, non-callable actions.

ID is a stable non-empty string. CONDITIONS use the milestone-A matcher.
ACTIONS are data forms; milestone B supports only (:ASSERT relation field ...).
SALIENCE is an integer used by the deterministic agenda policy."
  id
  conditions
  actions
  (salience 0)
  provenance)

(defstruct activation
  production
  production-id
  bindings
  fact-ids
  salience
  recency
  specificity
  signature)

(defstruct firing-record
  step
  production-id
  support-fact-ids
  asserted-fact-ids)

(defstruct inference-result
  status
  firings
  agenda)

(defstruct (inference-session (:constructor %make-inference-session))
  working-memory
  productions
  (fired-signatures '())
  (firing-count 0))

(defun validate-production (production)
  (unless (valid-stable-id-p (production-id production))
    (error "Production ID must be a non-empty string, got ~S"
           (production-id production)))
  (unless (and (listp (production-conditions production))
               (production-conditions production))
    (error "Production ~S must have at least one condition"
           (production-id production)))
  (unless (and (listp (production-actions production))
               (production-actions production))
    (error "Production ~S must have at least one action"
           (production-id production)))
  (unless (integerp (production-salience production))
    (error "Production ~S salience must be an integer"
           (production-id production)))
  (dolist (action (production-actions production))
    (unless (and (consp action)
                 (eq (first action) :assert)
                 (symbolp (second action)))
      (error "Unsupported action ~S in production ~S; milestone B accepts only (:ASSERT relation field ...)"
             action (production-id production))))
  production)

(defun make-inference-session (working-memory productions)
  "Validate PRODUCTIONS and create a session whose refraction state persists."
  (let ((seen '()))
    (dolist (production productions)
      (validate-production production)
      (when (member (production-id production) seen :test #'string=)
        (error "Duplicate production ID ~S" (production-id production)))
      (push (production-id production) seen)))
  (%make-inference-session :working-memory working-memory
                           :productions (copy-list productions)))

(defun activation-recency-from-supports (memory fact-ids)
  (reduce #'max fact-ids
          :key (lambda (id)
                 (or (fact-assertion-sequence memory id)
                     (error "Activation references inactive fact ~S" id)))))

(defun make-activation-from-match (memory production match)
  (let ((fact-ids (copy-list (match-result-fact-ids match))))
    (make-activation
     :production production
     :production-id (production-id production)
     :bindings (copy-tree (match-result-bindings match))
     :fact-ids fact-ids
     :salience (production-salience production)
     :recency (activation-recency-from-supports memory fact-ids)
     :specificity (length (production-conditions production))
     :signature (list (production-id production) fact-ids))))

(defun lexical-list< (left right)
  "Lexicographically compare lists of strings."
  (cond
    ((endp left) (not (endp right)))
    ((endp right) nil)
    ((string< (first left) (first right)) t)
    ((string> (first left) (first right)) nil)
    (t (lexical-list< (rest left) (rest right)))))

(defun activation-precedes-p (left right)
  "Total deterministic course-local agenda order.

Prefer greater salience, newer supporting evidence, and then more conditions.
Use stable production ID and ordered support IDs only as deterministic final
fallbacks. This is the teaching engine's policy, not a claim of CLIPS/OPS5
strategy equivalence."
  (cond
    ((/= (activation-salience left) (activation-salience right))
     (> (activation-salience left) (activation-salience right)))
    ((/= (activation-recency left) (activation-recency right))
     (> (activation-recency left) (activation-recency right)))
    ((/= (activation-specificity left) (activation-specificity right))
     (> (activation-specificity left) (activation-specificity right)))
    ((not (string= (activation-production-id left)
                   (activation-production-id right)))
     (string< (activation-production-id left)
              (activation-production-id right)))
    (t
     (lexical-list< (activation-fact-ids left)
                    (activation-fact-ids right)))))

(defun session-agenda (session)
  "Recompute and sort currently eligible activations for SESSION.

This deliberately rematches every production against every current fact set.
Refraction removes only an exact production/support identity that has already
fired in this session."
  (let* ((memory (inference-session-working-memory session))
         (facts (facts-in-working-memory memory))
         (fired (inference-session-fired-signatures session))
         (activations
           (loop for production in (inference-session-productions session)
                 append
                 (loop for match in (match-conditions
                                     (production-conditions production)
                                     facts)
                       for activation = (make-activation-from-match
                                         memory production match)
                       unless (member (activation-signature activation)
                                      fired :test #'equal)
                         collect activation))))
    (stable-sort activations #'activation-precedes-p)))

(defun lookup-binding (variable bindings)
  (let ((pair (assoc variable bindings :test #'eq)))
    (unless pair
      (error "Action references unbound variable ~S" variable))
    (cdr pair)))

(defun instantiate-term (term bindings)
  (cond
    ((variable-p term) (lookup-binding term bindings))
    ((consp term)
     (cons (instantiate-term (car term) bindings)
           (instantiate-term (cdr term) bindings)))
    (t term)))

(defun encode-id-part (value)
  (format nil "~D:~A" (length value) value))

(defun derived-fact-id (activation action-index)
  (format nil "derived|~A|~D|~{~A~^|~}"
          (encode-id-part (activation-production-id activation))
          action-index
          (mapcar #'encode-id-part (activation-fact-ids activation))))

(defun fire-activation (session activation)
  (let* ((memory (inference-session-working-memory session))
         (production (activation-production activation))
         (new-facts
           (loop for action in (production-actions production)
                 for action-index from 1
                 collect
                 (let* ((fact-form (rest action))
                        (instantiated
                          (instantiate-term fact-form
                                            (activation-bindings activation))))
                   (make-fact
                    :id (derived-fact-id activation action-index)
                    :relation (first instantiated)
                    :arguments (rest instantiated)
                    :provenance
                    (list :kind :derived
                          :production-id (production-id production)
                          :production-provenance (production-provenance production)
                          :support-fact-ids
                          (copy-list (activation-fact-ids activation))))))))
    ;; Instantiate every structured action before changing session state. This is
    ;; not a general transaction system, but malformed/unbound action templates
    ;; fail before refraction or working memory is mutated.
    (dolist (new-fact new-facts)
      (assert-fact memory new-fact))
    (push (copy-tree (activation-signature activation))
          (inference-session-fired-signatures session))
    (incf (inference-session-firing-count session))
    (make-firing-record
     :step (inference-session-firing-count session)
     :production-id (activation-production-id activation)
     :support-fact-ids (copy-list (activation-fact-ids activation))
     :asserted-fact-ids (mapcar #'fact-id new-facts))))

(defun run-forward-chain (session &key (max-firings 100))
  "Fire at most MAX-FIRINGS eligible activations from SESSION.

Returns an INFERENCE-RESULT whose STATUS is :QUIESCENT when no eligible
activation remains and :LIMIT-REACHED when bounded execution stops while work
remains. The bound is part of the teaching/debugging contract, not a proof of
termination."
  (unless (and (integerp max-firings) (>= max-firings 0))
    (error "MAX-FIRINGS must be a non-negative integer"))
  (let ((firings '()))
    (loop repeat max-firings
          for agenda = (session-agenda session)
          while agenda
          do (push (fire-activation session (first agenda)) firings))
    (let ((remaining (session-agenda session)))
      (make-inference-result
       :status (if remaining :limit-reached :quiescent)
       :firings (nreverse firings)
       :agenda remaining))))
