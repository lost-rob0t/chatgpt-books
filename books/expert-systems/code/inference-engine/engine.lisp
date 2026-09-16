(in-package #:expert-systems.matcher)

(define-condition duplicate-fact-id (error)
  ((id :initarg :id :reader duplicate-fact-id-id))
  (:report (lambda (condition stream)
             (format stream "Fact ID ~S is already present in working memory."
                     (duplicate-fact-id-id condition)))))

(define-condition duplicate-production-id (error)
  ((id :initarg :id :reader duplicate-production-id-id))
  (:report (lambda (condition stream)
             (format stream "Production ID ~S is duplicated."
                     (duplicate-production-id-id condition)))))

(defstruct wm-entry
  "One asserted fact occurrence and its monotonic working-memory sequence."
  fact
  sequence)

(defstruct (working-memory (:constructor %make-working-memory))
  "Mutable teaching working memory.

ENTRIES preserve assertion order. NEXT-SEQUENCE is monotonic within one working
memory and is not reused after retraction. Stable fact IDs identify logical
records; SEQUENCE distinguishes assertion occurrences for recency/refraction."
  (entries '())
  (next-sequence 0))

(defun ensure-fact (fact)
  (unless (typep fact 'fact)
    (error "Expected a FACT, got ~S." fact))
  (when (null (fact-id fact))
    (error "Facts asserted into working memory require a non-NIL stable ID."))
  fact)

(defun working-memory-facts (memory)
  "Return the current facts in assertion order."
  (mapcar #'wm-entry-fact (working-memory-entries memory)))

(defun find-wm-entry (memory fact-id)
  "Return the current WM-ENTRY with FACT-ID, or NIL."
  (find fact-id
        (working-memory-entries memory)
        :key (lambda (entry) (fact-id (wm-entry-fact entry)))
        :test #'equal))

(defun validate-assertion-batch (memory facts)
  "Validate FACTS before mutating MEMORY.

Stable IDs must be unique both against current working memory and within the
batch. Content equality is deliberately *not* a duplicate policy: two distinct
IDs may carry equal relation/arguments because they can represent distinct
observations."
  (let ((batch-ids '()))
    (dolist (fact facts)
      (ensure-fact fact)
      (let ((id (fact-id fact)))
        (when (or (find-wm-entry memory id)
                  (member id batch-ids :test #'equal))
          (error 'duplicate-fact-id :id id))
        (push id batch-ids))))
  facts)

(defun assert-facts (memory facts)
  "Atomically validate then append FACTS to MEMORY.

The batch has no externally visible partial state if validation fails. Returns
new WM-ENTRY objects in assertion order."
  (validate-assertion-batch memory facts)
  (let ((new-entries '())
        (sequence (working-memory-next-sequence memory)))
    (dolist (fact facts)
      (incf sequence)
      (push (make-wm-entry :fact fact :sequence sequence) new-entries))
    (setf new-entries (nreverse new-entries))
    (setf (working-memory-entries memory)
          (append (working-memory-entries memory) new-entries)
          (working-memory-next-sequence memory) sequence)
    new-entries))

(defun assert-fact (memory fact)
  "Assert one FACT and return its new WM-ENTRY."
  (first (assert-facts memory (list fact))))

(defun retract-fact (memory fact-id)
  "Retract FACT-ID from MEMORY.

Returns two values: the retracted FACT and true, or NIL/NIL when the ID is not
present. Retraction never rewinds the assertion sequence."
  (let ((entry (find-wm-entry memory fact-id)))
    (if (null entry)
        (values nil nil)
        (progn
          (setf (working-memory-entries memory)
                (remove entry (working-memory-entries memory)
                        :test #'eq :count 1))
          (values (wm-entry-fact entry) t)))))

(defun make-working-memory (&optional (facts '()))
  "Create working memory and assert FACTS in the supplied order."
  (let ((memory (%make-working-memory)))
    (assert-facts memory facts)
    memory))

(defstruct (production (:constructor %make-production))
  "A production in milestone B.

ACTION is a function of one ACTIVATION and returns a list of FACT objects to
assert. It must not mutate the engine. The engine validates the whole returned
batch before changing working memory."
  id
  conditions
  action
  (salience 0)
  provenance)

(defun make-production (&key id conditions action (salience 0) provenance)
  "Construct a validated teaching production."
  (when (null id)
    (error "Productions require a non-NIL stable ID."))
  (unless (listp conditions)
    (error "Production conditions must be a list, got ~S." conditions))
  (unless (functionp action)
    (error "Production action must be a function, got ~S." action))
  (unless (integerp salience)
    (error "Production salience must be an integer, got ~S." salience))
  (%make-production :id id
                    :conditions conditions
                    :action action
                    :salience salience
                    :provenance provenance))

(defun condition-specificity (condition)
  "Count literal terms in CONDITION for the course-local agenda policy."
  (count-if-not #'variable-p condition))

(defun production-specificity (production)
  "Return the structural-specificity score used only by this teaching engine.

Every non-variable LHS term contributes one point, including relation names.
This definition is deliberately explicit and is not claimed to be CLIPS or
OPS5 semantics."
  (reduce #'+ (production-conditions production)
          :key #'condition-specificity
          :initial-value 0))

(defstruct activation
  "One complete production instantiation eligible for the agenda."
  production
  bindings
  fact-ids
  support-stamps
  recency
  specificity
  key)

(defun activation-binding (activation variable)
  "Return VARIABLE's value in ACTIVATION, or NIL when unbound."
  (cdr (assoc variable (activation-bindings activation) :test #'eq)))

(defun support-stamps-for (memory fact-ids)
  "Map support FACT-IDS to (ID . assertion-sequence) occurrence stamps."
  (mapcar
   (lambda (id)
     (let ((entry (find-wm-entry memory id)))
       (unless entry
         (error "Matcher returned support ~S absent from working memory." id))
       (cons id (wm-entry-sequence entry))))
   fact-ids))

(defun activation-key-for (production bindings support-stamps)
  "Build a stable EQUAL-comparable refraction key."
  (list (production-id production)
        (copy-tree support-stamps)
        (copy-tree bindings)))

(defun make-activation-from-match (memory production match)
  (let* ((fact-ids (match-result-fact-ids match))
         (stamps (support-stamps-for memory fact-ids))
         (recency (reduce #'max stamps :key #'cdr :initial-value 0))
         (specificity (production-specificity production))
         (bindings (match-result-bindings match)))
    (make-activation
     :production production
     :bindings bindings
     :fact-ids fact-ids
     :support-stamps stamps
     :recency recency
     :specificity specificity
     :key (activation-key-for production bindings stamps))))

(defun stable-id-string (value)
  (string-downcase (princ-to-string value)))

(defun activation-precedes-p (left right)
  "Course-local deterministic conflict-resolution ordering.

Order by higher salience, newer support occurrence, greater structural
specificity, then stable production ID and activation key. The final two keys
exist to remove accidental dependence on definition/list order."
  (let ((left-production (activation-production left))
        (right-production (activation-production right)))
    (cond
      ((/= (production-salience left-production)
           (production-salience right-production))
       (> (production-salience left-production)
          (production-salience right-production)))
      ((/= (activation-recency left) (activation-recency right))
       (> (activation-recency left) (activation-recency right)))
      ((/= (activation-specificity left) (activation-specificity right))
       (> (activation-specificity left) (activation-specificity right)))
      ((string/= (stable-id-string (production-id left-production))
                 (stable-id-string (production-id right-production)))
       (string< (stable-id-string (production-id left-production))
                (stable-id-string (production-id right-production))))
      (t
       (string< (prin1-to-string (activation-key left))
                (prin1-to-string (activation-key right)))))))

(defstruct firing-record
  "An append-only trace record for one successfully committed firing."
  sequence
  production-id
  bindings
  support-fact-ids
  support-stamps
  asserted-fact-ids)

(defstruct (engine (:constructor %make-engine))
  working-memory
  productions
  (refracted-keys '())
  (firing-records '()))

(defun validate-productions (productions)
  (let ((ids '()))
    (dolist (production productions)
      (unless (typep production 'production)
        (error "Expected a PRODUCTION, got ~S." production))
      (let ((id (production-id production)))
        (when (member id ids :test #'equal)
          (error 'duplicate-production-id :id id))
        (push id ids))))
  productions)

(defun make-engine (&key (facts '()) (productions '()))
  "Create a milestone-B engine from initial FACTS and PRODUCTIONS."
  (validate-productions productions)
  (%make-engine :working-memory (make-working-memory facts)
                :productions (copy-list productions)))

(defun activation-refracted-p (engine activation)
  (member (activation-key activation)
          (engine-refracted-keys engine)
          :test #'equal))

(defun build-agenda (engine)
  "Completely rematch all productions and return ordered non-refracted activations.

This intentionally repeats work after every firing. It is the semantic oracle
that later incremental alpha/beta machinery must preserve."
  (let* ((memory (engine-working-memory engine))
         (facts (working-memory-facts memory))
         (activations
           (loop for production in (engine-productions engine)
                 append
                 (loop for match in
                       (match-conditions (production-conditions production) facts)
                       collect
                       (make-activation-from-match memory production match)))))
    (stable-sort
     (remove-if (lambda (activation)
                  (activation-refracted-p engine activation))
                activations)
     #'activation-precedes-p)))

(defun mark-refracted (engine activation)
  (pushnew (copy-tree (activation-key activation))
           (engine-refracted-keys engine)
           :test #'equal)
  engine)

(defun fire-activation (engine activation)
  "Fire ACTIVATION, validate its proposed facts, then commit them as one batch.

The production action receives only the activation and returns FACT objects.
This interface makes working-memory mutation an engine responsibility. Common
Lisp cannot prevent a malicious closure from reaching outside this boundary;
the contract is explicit and tested for normal project actions."
  (let* ((production (activation-production activation))
         (proposed (funcall (production-action production) activation)))
    (unless (listp proposed)
      (error "Production ~S action must return a list of FACT objects, got ~S."
             (production-id production) proposed))
    ;; ASSERT-FACTS validates the complete batch before mutating memory.
    (let* ((new-entries
             (assert-facts (engine-working-memory engine) proposed))
           (record
             (make-firing-record
              :sequence (1+ (length (engine-firing-records engine)))
              :production-id (production-id production)
              :bindings (copy-tree (activation-bindings activation))
              :support-fact-ids (copy-list (activation-fact-ids activation))
              :support-stamps (copy-tree (activation-support-stamps activation))
              :asserted-fact-ids
              (mapcar (lambda (entry) (fact-id (wm-entry-fact entry)))
                      new-entries))))
      (mark-refracted engine activation)
      (setf (engine-firing-records engine)
            (append (engine-firing-records engine) (list record)))
      record)))

(defstruct run-result
  status
  firing-count
  firing-records
  remaining-activation-keys)

(defun make-run-result-from-engine (engine status agenda)
  (make-run-result
   :status status
   :firing-count (length (engine-firing-records engine))
   :firing-records (copy-list (engine-firing-records engine))
   :remaining-activation-keys (mapcar #'activation-key agenda)))

(defun run-engine (engine &key (firing-limit 100))
  "Forward-chain until quiescence or FIRING-LIMIT.

:QUIESCENT means no eligible activation remains. :LIMIT means work remains but
the caller-supplied firing bound stopped execution. The two outcomes are never
collapsed."
  (unless (and (integerp firing-limit) (not (minusp firing-limit)))
    (error "FIRING-LIMIT must be a non-negative integer, got ~S." firing-limit))
  (loop repeat firing-limit
        for agenda = (build-agenda engine)
        do (when (endp agenda)
             (return-from run-engine
               (make-run-result-from-engine engine :quiescent agenda)))
           (fire-activation engine (first agenda)))
  (let ((agenda (build-agenda engine)))
    (make-run-result-from-engine
     engine
     (if (endp agenda) :quiescent :limit)
     agenda)))
