(in-package #:symbolic-ai.planner)

(define-condition ungrounded-action (error)
  ((schema :initarg :schema :reader ungrounded-action-schema)
   (term :initarg :term :reader ungrounded-action-term))
  (:report
   (lambda (condition stream)
     (format stream "Action schema ~S produced an ungrounded term: ~S"
             (action-schema-name (ungrounded-action-schema condition))
             (ungrounded-action-term condition)))))

(defstruct (action-schema
             (:constructor %make-action-schema
                 (name parameters preconditions add-effects delete-effects cost)))
  name
  parameters
  preconditions
  add-effects
  delete-effects
  (cost 1))

(defstruct ground-action
  schema-name
  name
  substitution
  preconditions
  add-effects
  delete-effects
  (cost 1))

(defun make-action-schema (name parameters preconditions add-effects delete-effects
                           &key (cost 1))
  "Construct one positive-precondition STRIPS-style teaching action schema.

PARAMETERS and all fact templates use the Pattern Matcher/Unifier variable
representation (:VAR NAME).  This milestone deliberately omits negative
preconditions, conditional effects, quantifiers, derived predicates, and PDDL
semantics."
  (dolist (value (list parameters preconditions add-effects delete-effects))
    (unless (listp value)
      (error 'type-error :datum value :expected-type 'list)))
  (unless (and (realp cost) (not (minusp cost)))
    (error 'type-error :datum cost :expected-type '(real 0 *)))
  (%make-action-schema name
                       (copy-tree parameters)
                       (copy-tree preconditions)
                       (copy-tree add-effects)
                       (copy-tree delete-effects)
                       cost))

(defun %fact-sort-key (fact)
  (let ((*print-readably* t)
        (*print-circle* t))
    (prin1-to-string fact)))

(defun canonical-state (facts)
  "Return a fresh, deterministic set-like state representation.

The planner treats world states as finite sets of ground symbolic facts.  The
canonical order is an implementation device for stable EQUAL keys; it is not a
claim that the printed ordering has domain semantics."
  (unless (listp facts)
    (error 'type-error :datum facts :expected-type 'list))
  (sort (mapcar #'copy-tree (remove-duplicates facts :test #'equal))
        #'string<
        :key #'%fact-sort-key))

(defun %ground-term-p (term)
  (cond
    ((symbolic-ai.pattern:variable-p term) nil)
    ((consp term)
     (and (%ground-term-p (car term))
          (%ground-term-p (cdr term))))
    (t t)))

(defun %ensure-ground (schema term)
  (unless (%ground-term-p term)
    (error 'ungrounded-action :schema schema :term term))
  term)

(defun goal-satisfied-p (state goals)
  "True when every ground GOAL fact is present in STATE under EQUAL."
  (every (lambda (goal) (member goal state :test #'equal)) goals))

(defun %extend-preconditions (preconditions state substitution)
  (if (endp preconditions)
      (list substitution)
      (mapcan
       (lambda (fact)
         (let ((result
                 (symbolic-ai.pattern:unify (first preconditions)
                                            fact
                                            :substitution substitution)))
           (if (eq :unified
                   (symbolic-ai.pattern:unification-result-status result))
               (%extend-preconditions
                (rest preconditions)
                state
                (symbolic-ai.pattern:unification-result-substitution result))
               '())))
       state)))

(defun %instantiate-facts (schema templates substitution)
  (mapcar
   (lambda (template)
     (%ensure-ground
      schema
      (symbolic-ai.pattern:apply-substitution template substitution)))
   templates))

(defun %instantiate-action-name (schema substitution)
  (let ((arguments
          (mapcar
           (lambda (parameter)
             (%ensure-ground
              schema
              (symbolic-ai.pattern:apply-substitution parameter substitution)))
           (action-schema-parameters schema))))
    (cons (action-schema-name schema) arguments)))

(defun %ground-action-key (action)
  (list (ground-action-name action)
        (ground-action-preconditions action)
        (ground-action-add-effects action)
        (ground-action-delete-effects action)
        (ground-action-cost action)))

(defun instantiate-applicable-actions (schema state)
  "Enumerate deterministic ground instances of SCHEMA applicable in STATE.

Binding consistency comes from repeated calls to the accepted public UNIFY
operation with the previously returned substitution.  Effects and action names
are instantiated only through APPLY-SUBSTITUTION; this code does not inspect or
mutate the substitution's representation."
  (let* ((world (canonical-state state))
         (substitutions
           (%extend-preconditions (action-schema-preconditions schema)
                                  world
                                  '()))
         (actions
           (mapcar
            (lambda (substitution)
              (make-ground-action
               :schema-name (action-schema-name schema)
               :name (%instantiate-action-name schema substitution)
               :substitution substitution
               :preconditions (%instantiate-facts
                               schema
                               (action-schema-preconditions schema)
                               substitution)
               :add-effects (%instantiate-facts
                             schema
                             (action-schema-add-effects schema)
                             substitution)
               :delete-effects (%instantiate-facts
                                schema
                                (action-schema-delete-effects schema)
                                substitution)
               :cost (action-schema-cost schema)))
            substitutions)))
    (remove-duplicates actions
                       :test #'equal
                       :key #'%ground-action-key)))

(defun apply-ground-action (state action)
  "Apply ACTION's delete set and then add set, returning a fresh canonical state."
  (let* ((without-deletes
           (remove-if
            (lambda (fact)
              (member fact
                      (ground-action-delete-effects action)
                      :test #'equal))
            state))
         (with-additions
           (append (ground-action-add-effects action)
                   without-deletes)))
    (canonical-state with-additions)))

(defun %planner-successors (schemas state)
  (loop
    for schema in schemas
    append
    (mapcar
     (lambda (action)
       (symbolic-ai.search:make-transition
        (apply-ground-action state action)
        :action (ground-action-name action)
        :cost (ground-action-cost action)))
     (instantiate-applicable-actions schema state))))

(defun make-planning-problem (initial-state goals schemas &key (heuristic (constantly 0)))
  "Adapt a finite classical planning task to the existing Search Library.

INITIAL-STATE and GOALS are lists of ground facts.  SCHEMAS is an ordered list
of ACTION-SCHEMA values.  State identity is the canonical fact set, so two
successor paths that produce the same world state meet at one graph-search key."
  (let ((initial (canonical-state initial-state))
        (goal-set (canonical-state goals))
        (schema-set (copy-list schemas)))
    (dolist (fact (append initial goal-set))
      (unless (%ground-term-p fact)
        (error 'type-error :datum fact :expected-type 'ground-symbolic-fact)))
    (dolist (schema schema-set)
      (unless (typep schema 'action-schema)
        (error 'type-error :datum schema :expected-type 'action-schema)))
    (symbolic-ai.search:make-problem
     initial
     (lambda (state) (goal-satisfied-p state goal-set))
     (lambda (state) (%planner-successors schema-set state))
     :heuristic heuristic
     :key #'identity)))

(defun solve-plan (initial-state goals schemas
                   &key (algorithm :breadth-first) (heuristic (constantly 0)))
  "Solve the course-local planning problem with an existing graph-search policy."
  (let ((problem (make-planning-problem initial-state goals schemas
                                        :heuristic heuristic)))
    (ecase algorithm
      (:breadth-first (symbolic-ai.search:breadth-first-search problem))
      (:uniform-cost (symbolic-ai.search:uniform-cost-search problem))
      (:a-star (symbolic-ai.search:a-star-search problem)))))
