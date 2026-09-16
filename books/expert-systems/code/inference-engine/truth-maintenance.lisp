(in-package #:expert-systems.matcher)

(define-condition fact-id-content-conflict (error)
  ((id :initarg :id :reader fact-id-content-conflict-id)
   (current :initarg :current :reader fact-id-content-conflict-current)
   (proposed :initarg :proposed :reader fact-id-content-conflict-proposed))
  (:report
   (lambda (condition stream)
     (format stream
             "Fact ID ~S already names ~S/~S, but the firing proposed ~S/~S."
             (fact-id-content-conflict-id condition)
             (fact-relation (fact-id-content-conflict-current condition))
             (fact-arguments (fact-id-content-conflict-current condition))
             (fact-relation (fact-id-content-conflict-proposed condition))
             (fact-arguments (fact-id-content-conflict-proposed condition))))))

(defstruct justification
  "One recorded reason for one exact derived-fact occurrence.

CONCLUSION-STAMP and SUPPORT-STAMPS use milestone-B occurrence identity. An old
reason therefore cannot silently attach itself to a later reassertion that
reuses the same stable fact ID. ID is deterministic from the production,
activation, and conclusion occurrence; it is an identity for this teaching
ledger, not a database key contract."
  id
  conclusion-fact-id
  conclusion-stamp
  production-id
  activation-key
  bindings
  support-stamps)

(defstruct support-report
  "Explanation-facing summary of the current support state for one fact ID."
  fact-id
  status
  present-p
  base-supported-p
  grounded-p
  current-justification-ids
  current-dependent-fact-ids)

(defstruct retraction-report
  "Result of removing base support and, when needed, cascading lost grounding.

BASE-SUPPORT-REMOVED-P reports only the support-classification change.
REQUESTED-OCCURRENCE-REMOVED-P reports whether the requested working-memory
occurrence itself was retracted. REMOVED-OCCURRENCE-STAMPS contains only exact
working-memory occurrences actually removed, so a base occurrence retained by
an independent derived reason is not misreported as retracted."
  requested-fact-id
  base-support-removed-p
  requested-occurrence-removed-p
  requested-stamp
  cascaded-fact-ids
  removed-occurrence-stamps)

(defstruct (truth-maintained-network
            (:constructor %make-truth-maintained-network))
  "A justification ledger layered over one milestone-C incremental network.

Every working-memory occurrence present when the wrapper is constructed is
base evidence. Later derived facts acquire explicit JUSTIFICATION records.
Matching caches remain owned by INCREMENTAL-NETWORK; this layer owns support
semantics only."
  incremental-network
  (base-support-stamps '())
  (justifications '()))

(defun truth-maintained-engine (truth-network)
  (incremental-network-engine
   (truth-maintained-network-incremental-network truth-network)))

(defun truth-maintained-working-memory (truth-network)
  (engine-working-memory (truth-maintained-engine truth-network)))

(defun entry-stamp (entry)
  (cons (fact-id (wm-entry-fact entry))
        (wm-entry-sequence entry)))

(defun current-stamp-for-fact-id (truth-network fact-id)
  "Return FACT-ID's current (ID . occurrence-sequence) stamp, or NIL."
  (let ((entry (find-wm-entry (truth-maintained-working-memory truth-network)
                              fact-id)))
    (and entry (entry-stamp entry))))

(defun support-stamp-current-p (truth-network stamp)
  "Return true when STAMP denotes the exact current working-memory occurrence."
  (let ((current (current-stamp-for-fact-id truth-network (car stamp))))
    (and current (equal current stamp))))

(defun make-truth-maintained-network (engine)
  "Wrap ENGINE with incremental matching plus a justification ledger.

All facts present at construction time are classified as base evidence. This is
a deliberate milestone-D boundary: callers should construct the wrapper before
running derived-fact firings they want truth-maintained."
  (let* ((incremental (make-incremental-network engine))
         (base-stamps
           (mapcar #'entry-stamp
                   (working-memory-entries (engine-working-memory engine)))))
    (%make-truth-maintained-network
     :incremental-network incremental
     :base-support-stamps base-stamps)))

(defun truth-maintained-base-supported-p (truth-network fact-id)
  "Return true when FACT-ID's exact current occurrence is base-supported."
  (let ((stamp (current-stamp-for-fact-id truth-network fact-id)))
    (and stamp
         (member stamp
                 (truth-maintained-network-base-support-stamps truth-network)
                 :test #'equal))))

(defun fact-logical-content-equal-p (left right)
  "Compare the logical content protected by a stable fact ID.

Provenance is deliberately excluded. A second rule may justify the same logical
fact with different source metadata; the justification ledger records that new
reason without mutating the already-materialized FACT object."
  (and (equal (fact-relation left) (fact-relation right))
       (equal (fact-arguments left) (fact-arguments right))))

(defun validate-truth-maintained-proposals (truth-network facts)
  "Validate one action result before any milestone-D state mutation.

Returns only facts that need a new working-memory occurrence. Same-ID,
same-content current facts are legal because another production may add an
independent justification. Same-ID, different-content proposals signal
FACT-ID-CONTENT-CONFLICT. Duplicate IDs within one action remain invalid."
  (let ((memory (truth-maintained-working-memory truth-network))
        (seen-ids '())
        (new-facts '()))
    (dolist (fact facts)
      (ensure-fact fact)
      (let ((id (fact-id fact)))
        (when (member id seen-ids :test #'equal)
          (error 'duplicate-fact-id :id id))
        (push id seen-ids)
        (let ((current-entry (find-wm-entry memory id)))
          (cond
            ((null current-entry)
             (push fact new-facts))
            ((fact-logical-content-equal-p
              (wm-entry-fact current-entry) fact)
             nil)
            (t
             (error 'fact-id-content-conflict
                    :id id
                    :current (wm-entry-fact current-entry)
                    :proposed fact))))))
    (setf new-facts (nreverse new-facts))
    ;; Reuse the milestone-B batch validator before any commit.
    (validate-assertion-batch memory new-facts)
    new-facts))

(defun justification-id-for (activation conclusion-stamp)
  (list :justification
        (production-id (activation-production activation))
        (copy-tree (activation-key activation))
        (copy-tree conclusion-stamp)))

(defun make-justification-from-activation (truth-network activation fact-id)
  (let ((conclusion-stamp
          (current-stamp-for-fact-id truth-network fact-id)))
    (unless conclusion-stamp
      (error "Cannot justify absent conclusion fact ~S." fact-id))
    (make-justification
     :id (justification-id-for activation conclusion-stamp)
     :conclusion-fact-id fact-id
     :conclusion-stamp (copy-tree conclusion-stamp)
     :production-id (production-id (activation-production activation))
     :activation-key (copy-tree (activation-key activation))
     :bindings (copy-tree (activation-bindings activation))
     :support-stamps (copy-tree (activation-support-stamps activation)))))

(defun add-justification (truth-network justification)
  "Append JUSTIFICATION unless its deterministic identity is already recorded."
  (unless (find (justification-id justification)
                (truth-maintained-network-justifications truth-network)
                :key #'justification-id
                :test #'equal)
    (setf (truth-maintained-network-justifications truth-network)
          (append (truth-maintained-network-justifications truth-network)
                  (list justification))))
  justification)

(defun truth-maintained-justifications-for (truth-network fact-id)
  "Return recorded historical justifications for FACT-ID in firing order."
  (remove-if-not
   (lambda (justification)
     (equal fact-id (justification-conclusion-fact-id justification)))
   (truth-maintained-network-justifications truth-network)))

(defun justification-conclusion-current-p (truth-network justification)
  (support-stamp-current-p truth-network
                           (justification-conclusion-stamp justification)))

(defun justification-supports-current-p (truth-network justification)
  "Return true when every exact support occurrence in JUSTIFICATION still exists."
  (every (lambda (stamp)
           (support-stamp-current-p truth-network stamp))
         (justification-support-stamps justification)))

(defun current-justifications-for (truth-network fact-id)
  "Return reasons attached to FACT-ID's exact current occurrence."
  (remove-if-not
   (lambda (justification)
     (justification-conclusion-current-p truth-network justification))
   (truth-maintained-justifications-for truth-network fact-id)))

(defun truth-maintained-fact-grounded-p (truth-network fact-id
                                         &optional (visiting '()))
  "Return true when FACT-ID has a current path to base evidence.

A justification is AND over its support occurrences; multiple justifications
are OR alternatives. VISITING stores exact conclusion occurrence stamps, so a
cycle without another path to base evidence cannot ground itself."
  (let ((stamp (current-stamp-for-fact-id truth-network fact-id)))
    (cond
      ((null stamp) nil)
      ((member stamp
               (truth-maintained-network-base-support-stamps truth-network)
               :test #'equal)
       t)
      ((member stamp visiting :test #'equal)
       nil)
      (t
       (some
        (lambda (justification)
          (and (equal stamp (justification-conclusion-stamp justification))
               (justification-supports-current-p truth-network justification)
               (every
                (lambda (support-stamp)
                  (truth-maintained-fact-grounded-p
                   truth-network
                   (car support-stamp)
                   (cons stamp visiting)))
                (justification-support-stamps justification))))
        (truth-maintained-network-justifications truth-network))))))

(defun current-dependent-fact-ids-for-stamp (truth-network support-stamp)
  "Return current conclusions with a recorded direct dependency on SUPPORT-STAMP."
  (remove-duplicates
   (loop for justification in
         (truth-maintained-network-justifications truth-network)
         when (and
               (justification-conclusion-current-p truth-network justification)
               (member support-stamp
                       (justification-support-stamps justification)
                       :test #'equal))
           collect (justification-conclusion-fact-id justification))
   :test #'equal))

(defun truth-maintained-current-dependents (truth-network fact-id)
  "Return current direct dependent fact IDs for FACT-ID's exact occurrence."
  (let ((stamp (current-stamp-for-fact-id truth-network fact-id)))
    (if stamp
        (current-dependent-fact-ids-for-stamp truth-network stamp)
        '())))

(defun truth-maintained-support-report (truth-network fact-id)
  "Summarize current base/derived support without inventing a proof narrative."
  (let* ((stamp (current-stamp-for-fact-id truth-network fact-id))
         (present-p (not (null stamp)))
         (base-p (and present-p
                      (truth-maintained-base-supported-p truth-network fact-id)))
         (current-reasons
           (if present-p
               (current-justifications-for truth-network fact-id)
               '())))
    (make-support-report
     :fact-id fact-id
     :status (cond (base-p :base)
                   (present-p :derived)
                   (t :absent))
     :present-p present-p
     :base-supported-p base-p
     :grounded-p (and present-p
                      (truth-maintained-fact-grounded-p truth-network fact-id))
     :current-justification-ids
     (mapcar (lambda (justification)
               (copy-tree (justification-id justification)))
             current-reasons)
     :current-dependent-fact-ids
     (if present-p
         (truth-maintained-current-dependents truth-network fact-id)
         '()))))

(defun truth-maintained-assert-base-fact (truth-network fact)
  "Assert FACT through the incremental API and mark its new occurrence as base."
  (let* ((network (truth-maintained-network-incremental-network truth-network))
         (entry (incremental-assert-fact network fact))
         (stamp (entry-stamp entry)))
    (setf (truth-maintained-network-base-support-stamps truth-network)
          (append (truth-maintained-network-base-support-stamps truth-network)
                  (list stamp)))
    entry))

(defun truth-maintained-fire-activation (truth-network activation)
  "Fire ACTIVATION while recording justifications for every proposed conclusion.

Same-ID/same-content conclusions already in working memory gain another reason
without another working-memory occurrence. This includes a base-supported
occurrence: base support and derived reasons are independent support sources.
Validation happens before normal state mutation. As in milestone C, no
transactional rollback is claimed for an unexpected host failure during
post-commit incremental propagation."
  (let* ((network (truth-maintained-network-incremental-network truth-network))
         (engine (truth-maintained-engine truth-network))
         (production (activation-production activation))
         (proposed (funcall (production-action production) activation)))
    (unless (listp proposed)
      (error "Production ~S action must return a list of FACT objects, got ~S."
             (production-id production) proposed))
    (let* ((new-facts
             (validate-truth-maintained-proposals truth-network proposed))
           (new-entries
             (if new-facts
                 (incremental-assert-facts network new-facts)
                 '()))
           (record
             (make-firing-record
              :sequence (1+ (length (engine-firing-records engine)))
              :production-id (production-id production)
              :bindings (copy-tree (activation-bindings activation))
              :support-fact-ids (copy-list (activation-fact-ids activation))
              :support-stamps (copy-tree (activation-support-stamps activation))
              :asserted-fact-ids
              (mapcar (lambda (entry)
                        (fact-id (wm-entry-fact entry)))
                      new-entries))))
      (mark-refracted engine activation)
      (setf (engine-firing-records engine)
            (append (engine-firing-records engine) (list record)))
      (dolist (fact proposed)
        (add-justification
         truth-network
         (make-justification-from-activation
          truth-network activation (fact-id fact))))
      record)))

(defun truth-maintained-run-engine (truth-network &key (firing-limit 100))
  "Forward-chain with incremental matching plus milestone-D justification recording."
  (unless (and (integerp firing-limit) (not (minusp firing-limit)))
    (error "FIRING-LIMIT must be a non-negative integer, got ~S." firing-limit))
  (let* ((network (truth-maintained-network-incremental-network truth-network))
         (engine (truth-maintained-engine truth-network)))
    (loop repeat firing-limit
          for agenda = (incremental-agenda network)
          do (when (endp agenda)
               (return-from truth-maintained-run-engine
                 (make-run-result-from-engine engine :quiescent agenda)))
             (truth-maintained-fire-activation truth-network (first agenda)))
    (let ((agenda (incremental-agenda network)))
      (make-run-result-from-engine
       engine
       (if (endp agenda) :quiescent :limit)
       agenda))))

(defun enqueue-new (items queue)
  "Append ITEMS to QUEUE without duplicate EQUAL entries, preserving order."
  (dolist (item items queue)
    (unless (member item queue :test #'equal)
      (setf queue (append queue (list item))))))

(defun truth-maintained-retract-base-fact (truth-network fact-id)
  "Remove FACT-ID's current base support and cascade only if grounding is lost.

Base support is one independent support source. Removing its exact stamp does
not automatically retract the working-memory occurrence: if a current derived
justification still grounds that same occurrence, it remains current and only
its base classification changes. If no grounded reason remains, the occurrence
is retracted through the incremental API and its exact stamp drives the usual
dependency-directed cascade. Historical justifications and firing records are
retained for later explanation work."
  (let* ((network (truth-maintained-network-incremental-network truth-network))
         (stamp (current-stamp-for-fact-id truth-network fact-id)))
    (cond
      ((null stamp)
       (make-retraction-report
        :requested-fact-id fact-id
        :base-support-removed-p nil
        :requested-occurrence-removed-p nil
        :requested-stamp nil
        :cascaded-fact-ids '()
        :removed-occurrence-stamps '()))
      ((not (member stamp
                    (truth-maintained-network-base-support-stamps truth-network)
                    :test #'equal))
       (error "Fact ID ~S is current but is not base-supported." fact-id))
      (t
       (setf (truth-maintained-network-base-support-stamps truth-network)
             (remove stamp
                     (truth-maintained-network-base-support-stamps truth-network)
                     :test #'equal :count 1))
       ;; Removing the base-support classification is not itself a working-memory
       ;; delta. A same-occurrence derived reason may still ground this fact.
       (if (truth-maintained-fact-grounded-p truth-network fact-id)
           (make-retraction-report
            :requested-fact-id fact-id
            :base-support-removed-p t
            :requested-occurrence-removed-p nil
            :requested-stamp (copy-tree stamp)
            :cascaded-fact-ids '()
            :removed-occurrence-stamps '())
           (progn
             (multiple-value-bind (fact present-p)
                 (incremental-retract-fact network fact-id)
               (declare (ignore fact))
               (unless present-p
                 (error "Truth-maintenance base stamp ~S had no current fact."
                        stamp)))
             (let ((removed-stamps (list stamp))
                   (cascaded '())
                   (queue
                     (current-dependent-fact-ids-for-stamp truth-network stamp)))
               (loop while queue
                     for candidate = (pop queue)
                     do (let ((candidate-stamp
                                (current-stamp-for-fact-id truth-network candidate)))
                          (when (and candidate-stamp
                                     (not (truth-maintained-base-supported-p
                                           truth-network candidate))
                                     (not (truth-maintained-fact-grounded-p
                                           truth-network candidate)))
                            (multiple-value-bind (removed removed-p)
                                (incremental-retract-fact network candidate)
                              (declare (ignore removed))
                              (when removed-p
                                (setf cascaded
                                      (append cascaded (list candidate))
                                      removed-stamps
                                      (append removed-stamps
                                              (list candidate-stamp))
                                      queue
                                      (enqueue-new
                                       (current-dependent-fact-ids-for-stamp
                                        truth-network candidate-stamp)
                                       queue)))))))
               (make-retraction-report
                :requested-fact-id fact-id
                :base-support-removed-p t
                :requested-occurrence-removed-p t
                :requested-stamp (copy-tree stamp)
                :cascaded-fact-ids cascaded
                :removed-occurrence-stamps removed-stamps))))))))

(defun truth-maintained-network-snapshot (truth-network)
  "Return deterministic support/cache state for tests and debugging labs."
  (list
   :base-support-stamps
   (copy-tree (truth-maintained-network-base-support-stamps truth-network))
   :justification-ids
   (mapcar (lambda (justification)
             (copy-tree (justification-id justification)))
           (truth-maintained-network-justifications truth-network))
   :incremental
   (incremental-network-snapshot
    (truth-maintained-network-incremental-network truth-network))))
