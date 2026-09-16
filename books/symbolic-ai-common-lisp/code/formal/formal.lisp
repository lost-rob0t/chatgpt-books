(in-package #:symbolic-ai-formal)

(define-condition invalid-transition-system (error)
  ((message :initarg :message :reader invalid-transition-system-message))
  (:report (lambda (condition stream)
             (format stream "Invalid transition system: ~A"
                     (invalid-transition-system-message condition)))))

(define-condition unknown-successors (condition)
  ((state :initarg :state :reader unknown-state)
   (reason :initarg :reason :reader unknown-reason))
  (:report (lambda (condition stream)
             (format stream "Successor relation is unknown for state ~S: ~A"
                     (unknown-state condition)
                     (unknown-reason condition)))))

(defstruct (transition-system
            (:constructor %make-transition-system
                (&key initial-states successors invariant key)))
  initial-states
  successors
  invariant
  key)

(defstruct check-result
  status
  trace
  visited
  complete-p
  reason)

(defun make-transition-system (&key initial-states successors invariant (key #'identity))
  "Construct a finite-state model for explicit reachability checking.

INITIAL-STATES is a non-empty list of states.  SUCCESSORS is a total function
for the states it knows how to enumerate and returns a finite list.  It may
signal UNKNOWN-SUCCESSORS when the model cannot enumerate a state's outgoing
transitions.  INVARIANT is a predicate over states.  KEY returns a stable,
EQUAL-comparable identity for duplicate detection."
  (unless (and (listp initial-states) initial-states)
    (error 'invalid-transition-system
           :message "INITIAL-STATES must be a non-empty list."))
  (dolist (function (list successors invariant key))
    (unless (functionp function)
      (error 'invalid-transition-system
             :message "SUCCESSORS, INVARIANT, and KEY must be functions.")))
  (%make-transition-system
   :initial-states initial-states
   :successors successors
   :invariant invariant
   :key key))

(defun check-invariant (system &key max-states)
  "Check SYSTEM's invariant over explicitly reachable states.

Returns a CHECK-RESULT whose STATUS is one of:

  :PROVED   -- exploration exhausted the reachable finite model and every
               reached state satisfied the invariant.
  :REFUTED  -- a reachable state violated the invariant; TRACE is a shortest
               counterexample in transition count because exploration is BFS.
  :BOUNDED  -- MAX-STATES prevented exhaustive exploration.  This is not proof.
  :UNKNOWN  -- the model reported that some successor relation was unavailable.

The function proves a property of the supplied model, not arbitrary host code.
The proof claim is only as strong as the model, invariant, and state identity
function supplied by the caller."
  (unless (typep system 'transition-system)
    (error 'invalid-transition-system
           :message "CHECK-INVARIANT requires a TRANSITION-SYSTEM."))
  (when (and max-states
             (not (and (integerp max-states) (plusp max-states))))
    (error 'invalid-transition-system
           :message "MAX-STATES must be NIL or a positive integer."))
  (let* ((key-function (transition-system-key system))
         (invariant (transition-system-invariant system))
         (successors (transition-system-successors system))
         (seen (make-hash-table :test #'equal))
         (parents (make-hash-table :test #'equal))
         (states (make-hash-table :test #'equal))
         (front '())
         (back '())
         (visited 0)
         (root-marker (gensym "ROOT-")))
    (labels ((enqueue (key)
               (push key back))
             (queue-empty-p ()
               (and (null front) (null back)))
             (dequeue ()
               (when (null front)
                 (setf front (nreverse back)
                       back '()))
               (pop front))
             (trace-for (key)
               (let ((trace '())
                     (cursor key))
                 (loop
                   (push (gethash cursor states) trace)
                   (let ((parent (gethash cursor parents)))
                     (when (eq parent root-marker)
                       (return trace))
                     (setf cursor parent)))))
             (result (status &key trace complete-p reason)
               (make-check-result
                :status status
                :trace trace
                :visited visited
                :complete-p complete-p
                :reason reason))
             (admit (state parent-key)
               (let ((key (funcall key-function state)))
                 (multiple-value-bind (old present-p) (gethash key seen)
                   (declare (ignore old))
                   (when present-p
                     (return-from admit (values :duplicate key nil)))
                   (when (and max-states (>= visited max-states))
                     (return-from admit (values :bounded key nil)))
                   (setf (gethash key seen) t
                         (gethash key states) state
                         (gethash key parents) parent-key)
                   (incf visited)
                   (unless (funcall invariant state)
                     (return-from admit
                       (values :refuted key (trace-for key))))
                   (enqueue key)
                   (values :admitted key nil)))))
      (dolist (initial (transition-system-initial-states system))
        (multiple-value-bind (status key trace)
            (admit initial root-marker)
          (declare (ignore key))
          (case status
            (:refuted
             (return-from check-invariant
               (result :refuted :trace trace :complete-p t)))
            (:bounded
             (return-from check-invariant
               (result :bounded :complete-p nil
                       :reason "MAX-STATES prevented complete initial-state admission."))))))
      (loop until (queue-empty-p)
            for key = (dequeue)
            for state = (gethash key states)
            do (let ((next-states
                       (handler-case
                           (funcall successors state)
                         (unknown-successors (condition)
                           (return-from check-invariant
                             (result :unknown
                                     :trace (trace-for key)
                                     :complete-p nil
                                     :reason (unknown-reason condition)))))))
                 (unless (listp next-states)
                   (error 'invalid-transition-system
                          :message "SUCCESSORS must return a finite list."))
                 (dolist (next next-states)
                   (multiple-value-bind (status child-key trace)
                       (admit next key)
                     (declare (ignore child-key))
                     (case status
                       (:refuted
                        (return-from check-invariant
                          (result :refuted :trace trace :complete-p t)))
                       (:bounded
                        (return-from check-invariant
                          (result :bounded :complete-p nil
                                  :reason "MAX-STATES prevented exhaustive reachability exploration."))))))))
      (result :proved :complete-p t))))
