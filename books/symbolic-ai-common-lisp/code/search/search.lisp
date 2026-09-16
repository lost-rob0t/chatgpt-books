(in-package #:symbolic-ai.search)

(define-condition invalid-step-cost (error)
  ((cost :initarg :cost :reader invalid-step-cost-cost)
   (from :initarg :from :reader invalid-step-cost-from)
   (to :initarg :to :reader invalid-step-cost-to))
  (:report
   (lambda (condition stream)
     (format stream "Invalid nonnegative real step cost ~S on transition ~S -> ~S."
             (invalid-step-cost-cost condition)
             (invalid-step-cost-from condition)
             (invalid-step-cost-to condition)))))

(define-condition invalid-heuristic-value (error)
  ((value :initarg :value :reader invalid-heuristic-value-value)
   (state :initarg :state :reader invalid-heuristic-value-state))
  (:report
   (lambda (condition stream)
     (format stream "Heuristic returned invalid nonnegative real value ~S for state ~S."
             (invalid-heuristic-value-value condition)
             (invalid-heuristic-value-state condition)))))

(defstruct (transition
             (:constructor make-transition (state &key action (cost 1))))
  state
  action
  (cost 1))

(defstruct (problem
             (:constructor %make-problem
                 (initial-state goal-p successors heuristic key)))
  initial-state
  goal-p
  successors
  heuristic
  key)

(defun make-problem (initial-state goal-p successors
                     &key (heuristic (constantly 0)) (key #'identity))
  "Create a graph-search problem.

GOAL-P, SUCCESSORS, HEURISTIC, and KEY are functions. SUCCESSORS returns a
list of TRANSITION values. KEY returns an EQUAL-comparable value that must not
be visibly mutated while it is stored in the search tables."
  (dolist (function (list goal-p successors heuristic key))
    (unless (functionp function)
      (error 'type-error :datum function :expected-type 'function)))
  (%make-problem initial-state goal-p successors heuristic key))

(defstruct node
  state
  parent
  action
  (g 0)
  (depth 0)
  (serial 0))

(defstruct (search-result
             (:constructor %make-search-result))
  status
  path
  actions
  cost
  (expanded 0)
  (generated 0)
  (duplicate-pruned 0)
  (stale-popped 0)
  (max-frontier 0)
  algorithm)

(defun state-key (problem state)
  (funcall (problem-key problem) state))

(defun goal-state-p (problem state)
  (funcall (problem-goal-p problem) state))

(defun successor-transitions (problem state)
  (let ((transitions (funcall (problem-successors problem) state)))
    (unless (listp transitions)
      (error 'type-error :datum transitions :expected-type 'list))
    (dolist (transition transitions)
      (unless (typep transition 'transition)
        (error 'type-error :datum transition :expected-type 'transition)))
    transitions))

(defun checked-step-cost (transition from)
  (let ((cost (transition-cost transition)))
    (unless (and (realp cost) (not (minusp cost)))
      (error 'invalid-step-cost
             :cost cost
             :from from
             :to (transition-state transition)))
    cost))

(defun checked-heuristic (problem state)
  (let ((value (funcall (problem-heuristic problem) state)))
    (unless (and (realp value) (not (minusp value)))
      (error 'invalid-heuristic-value :value value :state state))
    value))

(defun reconstruct-solution (node algorithm metrics)
  (let ((states '())
        (actions '()))
    (loop for cursor = node then (node-parent cursor)
          while cursor
          do (push (node-state cursor) states)
             (when (node-parent cursor)
               (push (node-action cursor) actions)))
    (%make-search-result
     :status :found
     :path states
     :actions actions
     :cost (node-g node)
     :expanded (getf metrics :expanded)
     :generated (getf metrics :generated)
     :duplicate-pruned (getf metrics :duplicate-pruned)
     :stale-popped (getf metrics :stale-popped)
     :max-frontier (getf metrics :max-frontier)
     :algorithm algorithm)))

(defun failed-result (algorithm metrics)
  (%make-search-result
   :status :not-found
   :path nil
   :actions nil
   :cost nil
   :expanded (getf metrics :expanded)
   :generated (getf metrics :generated)
   :duplicate-pruned (getf metrics :duplicate-pruned)
   :stale-popped (getf metrics :stale-popped)
   :max-frontier (getf metrics :max-frontier)
   :algorithm algorithm))

(defun note-frontier-size (metrics size)
  (setf (getf metrics :max-frontier)
        (max (getf metrics :max-frontier) size)))

(defstruct fifo
  front
  back
  (size 0))

(defun fifo-enqueue (queue value)
  (push value (fifo-back queue))
  (incf (fifo-size queue))
  value)

(defun fifo-dequeue (queue)
  (when (null (fifo-front queue))
    (setf (fifo-front queue) (nreverse (fifo-back queue))
          (fifo-back queue) nil))
  (when (fifo-front queue)
    (decf (fifo-size queue))
    (pop (fifo-front queue))))

(defun make-root-node (problem)
  (make-node :state (problem-initial-state problem)
             :g 0
             :depth 0
             :serial 0))

(defun unweighted-graph-search (problem algorithm)
  (let* ((root (make-root-node problem))
         (seen (make-hash-table :test #'equal))
         (metrics (list :expanded 0
                        :generated 1
                        :duplicate-pruned 0
                        :stale-popped 0
                        :max-frontier 1)))
    (setf (gethash (state-key problem (node-state root)) seen) t)
    (ecase algorithm
      (:depth-first
       (let ((frontier (list root)))
         (loop while frontier
               for current = (pop frontier)
               do (when (goal-state-p problem (node-state current))
                    (return-from unweighted-graph-search
                      (reconstruct-solution current algorithm metrics)))
                  (incf (getf metrics :expanded))
                  (let ((children '()))
                    (dolist (transition
                             (successor-transitions problem (node-state current)))
                      (let* ((state (transition-state transition))
                             (key (state-key problem state))
                             (cost (checked-step-cost transition
                                                      (node-state current))))
                        (if (gethash key seen)
                            (incf (getf metrics :duplicate-pruned))
                            (progn
                              (setf (gethash key seen) t)
                              (push (make-node
                                     :state state
                                     :parent current
                                     :action (transition-action transition)
                                     :g (+ (node-g current) cost)
                                     :depth (1+ (node-depth current)))
                                    children)
                              (incf (getf metrics :generated))))))
                    ;; CHILDREN is reverse successor order. Pushing it as-is
                    ;; puts the first declared successor on top of the stack.
                    (dolist (child children)
                      (push child frontier))
                    (note-frontier-size metrics (length frontier))))))
      (:breadth-first
       (let ((frontier (make-fifo)))
         (fifo-enqueue frontier root)
         (loop while (plusp (fifo-size frontier))
               for current = (fifo-dequeue frontier)
               do (when (goal-state-p problem (node-state current))
                    (return-from unweighted-graph-search
                      (reconstruct-solution current algorithm metrics)))
                  (incf (getf metrics :expanded))
                  (dolist (transition
                           (successor-transitions problem (node-state current)))
                    (let* ((state (transition-state transition))
                           (key (state-key problem state))
                           (cost (checked-step-cost transition
                                                    (node-state current))))
                      (if (gethash key seen)
                          (incf (getf metrics :duplicate-pruned))
                          (progn
                            (setf (gethash key seen) t)
                            (fifo-enqueue
                             frontier
                             (make-node
                              :state state
                              :parent current
                              :action (transition-action transition)
                              :g (+ (node-g current) cost)
                              :depth (1+ (node-depth current))))
                            (incf (getf metrics :generated)))))
                    (note-frontier-size metrics (fifo-size frontier)))))))
    (failed-result algorithm metrics)))

(defun depth-first-search (problem)
  "Run deterministic depth-first graph search.

States are marked seen when enqueued. Successor order is preserved: the first
transition returned by the problem is explored first."
  (unweighted-graph-search problem :depth-first))

(defun breadth-first-search (problem)
  "Run deterministic breadth-first graph search.

States are marked seen when enqueued, so equal-cost duplicate paths are pruned
before they occupy additional frontier slots."
  (unweighted-graph-search problem :breadth-first))

(defstruct heap-entry
  priority
  serial
  node)

(defstruct (min-heap (:constructor make-min-heap ()))
  (entries (make-array 16 :adjustable t :fill-pointer 0)))

(defun heap-size (heap)
  (length (min-heap-entries heap)))

(defun heap-entry-before-p (left right)
  (or (< (heap-entry-priority left) (heap-entry-priority right))
      (and (= (heap-entry-priority left) (heap-entry-priority right))
           (< (heap-entry-serial left) (heap-entry-serial right)))))

(defun heap-swap (vector left right)
  (rotatef (aref vector left) (aref vector right)))

(defun heap-push (heap entry)
  (let* ((vector (min-heap-entries heap))
         (index (vector-push-extend entry vector)))
    (loop while (plusp index)
          for parent = (floor (1- index) 2)
          while (heap-entry-before-p (aref vector index)
                                     (aref vector parent))
          do (heap-swap vector index parent)
             (setf index parent)))
  entry)

(defun heap-pop (heap)
  (let ((vector (min-heap-entries heap)))
    (when (zerop (length vector))
      (return-from heap-pop nil))
    (let ((minimum (aref vector 0))
          (last (vector-pop vector)))
      (when (plusp (length vector))
        (setf (aref vector 0) last)
        (let ((index 0))
          (loop
            with size = (length vector)
            for left = (1+ (* 2 index))
            for right = (+ 2 (* 2 index))
            while (< left size)
            for candidate = (if (and (< right size)
                                     (heap-entry-before-p (aref vector right)
                                                          (aref vector left)))
                                right
                                left)
            while (heap-entry-before-p (aref vector candidate)
                                       (aref vector index))
            do (heap-swap vector index candidate)
               (setf index candidate))))
      minimum)))

(defun best-first-graph-search (problem algorithm)
  (let* ((root (make-root-node problem))
         (frontier (make-min-heap))
         (best-g (make-hash-table :test #'equal))
         (serial 0)
         (metrics (list :expanded 0
                        :generated 1
                        :duplicate-pruned 0
                        :stale-popped 0
                        :max-frontier 1)))
    (labels ((priority-for (state g)
               (ecase algorithm
                 (:uniform-cost g)
                 (:a-star (+ g (checked-heuristic problem state)))))
             (enqueue (node)
               (setf (node-serial node) serial)
               (heap-push frontier
                          (make-heap-entry
                           :priority (priority-for (node-state node)
                                                   (node-g node))
                           :serial serial
                           :node node))
               (incf serial)
               (note-frontier-size metrics (heap-size frontier))))
      (setf (gethash (state-key problem (node-state root)) best-g) 0)
      (enqueue root)
      (loop while (plusp (heap-size frontier))
            for entry = (heap-pop frontier)
            for current = (heap-entry-node entry)
            for current-key = (state-key problem (node-state current))
            for known-g = (gethash current-key best-g)
            do (if (> (node-g current) known-g)
                   (incf (getf metrics :stale-popped))
                   (progn
                     (when (goal-state-p problem (node-state current))
                       (return-from best-first-graph-search
                         (reconstruct-solution current algorithm metrics)))
                     (incf (getf metrics :expanded))
                     (dolist (transition
                              (successor-transitions problem (node-state current)))
                       (let* ((state (transition-state transition))
                              (key (state-key problem state))
                              (new-g (+ (node-g current)
                                        (checked-step-cost
                                         transition
                                         (node-state current)))))
                         (multiple-value-bind (old-g present-p)
                             (gethash key best-g)
                           (if (and present-p (<= old-g new-g))
                               (incf (getf metrics :duplicate-pruned))
                               (progn
                                 (setf (gethash key best-g) new-g)
                                 (enqueue
                                  (make-node
                                   :state state
                                   :parent current
                                   :action (transition-action transition)
                                   :g new-g
                                   :depth (1+ (node-depth current))))
                                 (incf (getf metrics :generated))))))))))
      (failed-result algorithm metrics))))

(defun uniform-cost-search (problem)
  "Run uniform-cost graph search with best-cost duplicate handling.

When a cheaper path to an already discovered state appears, the new node is
queued. Older, more expensive frontier entries are recognized as stale when
popped and never expanded."
  (best-first-graph-search problem :uniform-cost))

(defun a-star-search (problem)
  "Run A* graph search using g(n) + h(n).

The implementation reopens a state when a cheaper g-value is found. This is
important for admissible but inconsistent heuristics: duplicate detection must
not permanently discard an improved path."
  (best-first-graph-search problem :a-star))
