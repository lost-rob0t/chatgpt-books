(in-package #:symbolic-ai.planner)

(defstruct relaxed-support
  fact
  cost
  source
  schema-name
  action-name
  preconditions)

(defstruct relaxed-analysis
  status
  estimate
  iterations
  fact-costs
  supports)

(defstruct plan-step-explanation
  action-name
  schema-name
  cost
  preconditions
  add-effects
  delete-effects
  before-state
  after-state)

(define-condition invalid-plan-trace (error)
  ((action :initarg :action :reader invalid-plan-trace-action)
   (before :initarg :before :reader invalid-plan-trace-before)
   (after :initarg :after :reader invalid-plan-trace-after))
  (:report
   (lambda (condition stream)
     (format stream
             "Search trace action ~S cannot be replayed from ~S to ~S under the supplied schemas."
             (invalid-plan-trace-action condition)
             (invalid-plan-trace-before condition)
             (invalid-plan-trace-after condition)))))

(define-condition ambiguous-plan-step (error)
  ((action :initarg :action :reader ambiguous-plan-step-action)
   (before :initarg :before :reader ambiguous-plan-step-before)
   (after :initarg :after :reader ambiguous-plan-step-after)
   (matches :initarg :matches :reader ambiguous-plan-step-matches))
  (:report
   (lambda (condition stream)
     (format stream
             "Search trace action ~S has ~D grounded explanations from ~S to ~S."
             (ambiguous-plan-step-action condition)
             (length (ambiguous-plan-step-matches condition))
             (ambiguous-plan-step-before condition)
             (ambiguous-plan-step-after condition)))))

(defun %sorted-hash-alist (table)
  (let ((pairs '()))
    (maphash (lambda (key value)
               (push (cons (copy-tree key) value) pairs))
             table)
    (sort pairs #'string< :key (lambda (pair) (%fact-sort-key (car pair))))))

(defun %precondition-max-cost (preconditions costs)
  (loop
    with maximum = 0
    for fact in preconditions
    do (multiple-value-bind (cost present-p) (gethash fact costs)
         (unless present-p
           (error "Relaxed action precondition ~S has no recorded fact cost." fact))
         (setf maximum (max maximum cost)))
    finally (return maximum)))

(defun %goal-estimate (goals costs)
  (loop
    with maximum = 0
    for goal in goals
    do (multiple-value-bind (cost present-p) (gethash goal costs)
         (unless present-p
           (return-from %goal-estimate nil))
         (setf maximum (max maximum cost)))
    finally (return maximum)))

(defun %analysis-result (status estimate iterations costs supports)
  (make-relaxed-analysis
   :status status
   :estimate estimate
   :iterations iterations
   :fact-costs (%sorted-hash-alist costs)
   :supports (%sorted-hash-alist supports)))

(defun analyze-hmax-relaxation (state goals schemas &key (max-iterations 256))
  "Compute a bounded delete-relaxation H-MAX-style analysis.

The analysis uses the existing positive-precondition action schemas, ignores
DELETE effects, and propagates one best cost per ground fact.  The cost of a
grounded action is its declared action cost plus the maximum cost of its
preconditions.  The goal estimate is the maximum propagated goal-fact cost.

STATUS is one of :REACHED, :UNREACHABLE, or :BOUNDED.  :UNREACHABLE is returned
only after this monotone propagation reaches a fixpoint without all goals.
:BOUNDED means MAX-ITERATIONS stopped propagation first and must not be read as
a dead-end proof.  SUPPORTS explain this relaxed cost calculation only; they are
not evidence that a supporting action occurs in an executed plan."
  (unless (typep max-iterations '(integer 0 *))
    (error 'type-error :datum max-iterations :expected-type '(integer 0 *)))
  (let ((facts (canonical-state state))
        (goal-set (canonical-state goals))
        (schema-set (copy-list schemas))
        (costs (make-hash-table :test #'equal))
        (supports (make-hash-table :test #'equal)))
    (dolist (fact (append facts goal-set))
      (%ensure-ground-world-fact fact))
    (dolist (schema schema-set)
      (unless (typep schema 'action-schema)
        (error 'type-error :datum schema :expected-type 'action-schema)))
    (dolist (fact facts)
      (setf (gethash fact costs) 0
            (gethash fact supports)
            (make-relaxed-support
             :fact (copy-tree fact)
             :cost 0
             :source :initial)))
    (when (goal-satisfied-p facts goal-set)
      (return-from analyze-hmax-relaxation
        (%analysis-result :reached 0 0 costs supports)))
    (loop
      for iteration from 1 to max-iterations
      do (let ((changed-p nil))
           (dolist (schema schema-set)
             (dolist (action (instantiate-applicable-actions schema facts))
               (let ((candidate
                       (+ (ground-action-cost action)
                          (%precondition-max-cost
                           (ground-action-preconditions action)
                           costs))))
                 (dolist (effect (ground-action-add-effects action))
                   (multiple-value-bind (old-cost present-p)
                       (gethash effect costs)
                     (when (or (not present-p) (< candidate old-cost))
                       (setf (gethash effect costs) candidate
                             (gethash effect supports)
                             (make-relaxed-support
                              :fact (copy-tree effect)
                              :cost candidate
                              :source :action
                              :schema-name (ground-action-schema-name action)
                              :action-name (copy-tree (ground-action-name action))
                              :preconditions
                              (copy-tree (ground-action-preconditions action))))
                       (pushnew (copy-tree effect) facts :test #'equal)
                       (setf changed-p t)))))))
           (setf facts (canonical-state facts))
           (unless changed-p
             (let ((estimate (%goal-estimate goal-set costs)))
               (return-from analyze-hmax-relaxation
                 (%analysis-result (if estimate :reached :unreachable)
                                   estimate
                                   iteration
                                   costs
                                   supports)))))
      finally
         (return
           (%analysis-result :bounded nil max-iterations costs supports)))))

(defun make-hmax-heuristic (goals schemas &key (max-iterations 256))
  "Return an A*-compatible numeric heuristic backed by ANALYZE-HMAX-RELAXATION.

A converged :REACHED analysis returns its estimate.  :UNREACHABLE and :BOUNDED
return zero so the Search Library receives a finite nonnegative value instead
of silently treating incomplete analysis as infinity.  Call
ANALYZE-HMAX-RELAXATION directly when the evidence status matters."
  (let ((goal-set (copy-tree goals))
        (schema-set (copy-list schemas)))
    (lambda (state)
      (let ((analysis
              (analyze-hmax-relaxation state goal-set schema-set
                                       :max-iterations max-iterations)))
        (if (eq :reached (relaxed-analysis-status analysis))
            (relaxed-analysis-estimate analysis)
            0)))))

(defun %matching-ground-actions (schemas before action-name after)
  (loop
    for schema in schemas
    append
    (remove-if-not
     (lambda (action)
       (and (equal action-name (ground-action-name action))
            (equal after (apply-ground-action before action))))
     (instantiate-applicable-actions schema before))))

(defun %explanation-from-ground-action (action before after)
  (make-plan-step-explanation
   :action-name (copy-tree (ground-action-name action))
   :schema-name (ground-action-schema-name action)
   :cost (ground-action-cost action)
   :preconditions (copy-tree (ground-action-preconditions action))
   :add-effects (copy-tree (ground-action-add-effects action))
   :delete-effects (copy-tree (ground-action-delete-effects action))
   :before-state (copy-tree before)
   :after-state (copy-tree after)))

(defun explain-plan-result (schemas result)
  "Replay a found Search Library plan against the supplied planner schemas.

Each returned PLAN-STEP-EXPLANATION records the unique grounded action whose
application transforms one recorded path state into the next.  Missing matches
signal INVALID-PLAN-TRACE.  Multiple grounded matches signal
AMBIGUOUS-PLAN-STEP rather than inventing provenance."
  (unless (typep result 'symbolic-ai.search:search-result)
    (error 'type-error :datum result :expected-type 'symbolic-ai.search:search-result))
  (unless (eq :found (symbolic-ai.search:search-result-status result))
    (error 'invalid-plan-trace :action nil :before nil :after nil))
  (let ((states (symbolic-ai.search:search-result-path result))
        (actions (symbolic-ai.search:search-result-actions result))
        (schema-set (copy-list schemas))
        (explanations '()))
    (unless (= (length actions) (1- (length states)))
      (error 'invalid-plan-trace :action nil :before states :after actions))
    (loop
      for action-name in actions
      for before in states
      for after in (rest states)
      do (let ((matches
                 (%matching-ground-actions schema-set before action-name after)))
           (cond
             ((null matches)
              (error 'invalid-plan-trace
                     :action action-name :before before :after after))
             ((rest matches)
              (error 'ambiguous-plan-step
                     :action action-name
                     :before before
                     :after after
                     :matches matches))
             (t
              (push (%explanation-from-ground-action
                     (first matches) before after)
                    explanations)))))
    (nreverse explanations)))
