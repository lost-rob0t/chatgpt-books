(in-package #:expert-systems.matcher)

(define-condition duplicate-contradiction-spec-id (error)
  ((id :initarg :id :reader duplicate-contradiction-spec-id-id))
  (:report
   (lambda (condition stream)
     (format stream "Contradiction specification ID ~S is duplicated."
             (duplicate-contradiction-spec-id-id condition)))))

(defstruct (contradiction-spec (:constructor %make-contradiction-spec))
  "One explicit declaration that two fact patterns cannot jointly hold.

The two patterns use the same matcher language as production conditions. Shared
variables therefore constrain both sides of the contradiction. PROVENANCE is
opaque engine metadata that identifies where the consistency rule came from;
this layer does not treat the declaration as self-proving domain truth."
  id
  left-pattern
  right-pattern
  provenance)

(defun make-contradiction-spec (&key id left-pattern right-pattern provenance)
  "Construct a validated course-local contradiction specification."
  (when (null id)
    (error "Contradiction specifications require a non-NIL stable ID."))
  (unless (consp left-pattern)
    (error "LEFT-PATTERN must be a non-empty condition pattern, got ~S."
           left-pattern))
  (unless (consp right-pattern)
    (error "RIGHT-PATTERN must be a non-empty condition pattern, got ~S."
           right-pattern))
  (%make-contradiction-spec
   :id id
   :left-pattern (copy-tree left-pattern)
   :right-pattern (copy-tree right-pattern)
   :provenance provenance))

(defstruct contradiction-report
  "One current pair of grounded occurrences matching a contradiction spec.

Reports preserve both sides as counterevidence. The engine does not choose a
winner, retract either side, or convert the contradiction into a probability."
  spec-id
  spec-provenance
  bindings
  left-fact-id
  left-stamp
  left-support-kind
  right-fact-id
  right-stamp
  right-support-kind)

(defstruct consistency-run-result
  "Result of forward chaining under an explicit contradiction policy.

STATUS is :QUIESCENT, :LIMIT, or :CONTRADICTION. CONTRADICTIONS is always the
current report set at the return boundary, including in :REPORT-ONLY mode."
  status
  firing-count
  firing-records
  remaining-activation-keys
  contradictions)

(defstruct (assumption-network (:constructor %make-assumption-network))
  "Assumption and contradiction semantics layered over milestone-D support.

TRUTH-NETWORK remains the owner of working memory, matching, justifications,
and cascading retraction. ASSUMPTION-STAMPS classifies selected exact base
occurrences as assumptions. CONTRADICTION-SPECS declare domain consistency
constraints without silently resolving them."
  truth-network
  (assumption-stamps '())
  (contradiction-specs '()))

(defun validate-contradiction-specs (specs)
  (let ((ids '()))
    (dolist (spec specs)
      (unless (typep spec 'contradiction-spec)
        (error "Expected a CONTRADICTION-SPEC, got ~S." spec))
      (let ((id (contradiction-spec-id spec)))
        (when (member id ids :test #'equal)
          (error 'duplicate-contradiction-spec-id :id id))
        (push id ids))))
  specs)

(defun make-assumption-network (truth-network &key (contradiction-specs '()))
  "Layer explicit assumptions and contradiction declarations over TRUTH-NETWORK.

Existing base-supported facts remain ordinary evidence. A caller must use
ASSUMPTION-NETWORK-ASSERT-ASSUMPTION for an occurrence that should be marked as
an assumption."
  (unless (typep truth-network 'truth-maintained-network)
    (error "Expected a TRUTH-MAINTAINED-NETWORK, got ~S." truth-network))
  (validate-contradiction-specs contradiction-specs)
  (%make-assumption-network
   :truth-network truth-network
   :contradiction-specs (copy-list contradiction-specs)))

(defun assumption-network-engine (network)
  (truth-maintained-engine (assumption-network-truth-network network)))

(defun assumption-network-working-memory (network)
  (truth-maintained-working-memory (assumption-network-truth-network network)))

(defun assumption-network-incremental-network (network)
  (truth-maintained-network-incremental-network
   (assumption-network-truth-network network)))

(defun assumption-supported-p (network fact-id)
  "Return true when FACT-ID's exact current occurrence is marked an assumption."
  (let* ((truth (assumption-network-truth-network network))
         (stamp (current-stamp-for-fact-id truth fact-id)))
    (and stamp
         (member stamp
                 (assumption-network-assumption-stamps network)
                 :test #'equal))))

(defun assumption-network-support-kind (network fact-id)
  "Classify FACT-ID's current support boundary for contradiction reports.

:ASSUMPTION is an explicit assumption occurrence; :EVIDENCE is other current
base support; :DERIVED is a non-base current occurrence; :ABSENT has no current
working-memory occurrence. This classification does not rank sources or choose
between contradictory evidence."
  (let* ((truth (assumption-network-truth-network network))
         (stamp (current-stamp-for-fact-id truth fact-id)))
    (cond
      ((null stamp) :absent)
      ((assumption-supported-p network fact-id) :assumption)
      ((truth-maintained-base-supported-p truth fact-id) :evidence)
      (t :derived))))

(defun assumption-network-assert-evidence (network fact)
  "Assert FACT as ordinary base evidence, not as an assumption."
  (truth-maintained-assert-base-fact
   (assumption-network-truth-network network) fact))

(defun assumption-network-assert-assumption (network fact)
  "Assert FACT as base-supported evidence and mark that exact occurrence assumed."
  (let* ((truth (assumption-network-truth-network network))
         (entry (truth-maintained-assert-base-fact truth fact))
         (stamp (entry-stamp entry)))
    (setf (assumption-network-assumption-stamps network)
          (append (assumption-network-assumption-stamps network)
                  (list stamp)))
    entry))

(defun assumption-network-withdraw-assumption (network fact-id)
  "Withdraw FACT-ID's exact current assumption support.

The operation removes only the assumption's base-support source first. If a
separate derived justification still grounds the same occurrence, milestone-D
semantics keep it current. Otherwise normal support-driven cascading retraction
occurs."
  (let* ((truth (assumption-network-truth-network network))
         (stamp (current-stamp-for-fact-id truth fact-id)))
    (unless (and stamp (assumption-supported-p network fact-id))
      (error "Fact ID ~S is not a current explicit assumption." fact-id))
    (let ((report (truth-maintained-retract-base-fact truth fact-id)))
      (setf (assumption-network-assumption-stamps network)
            (remove stamp
                    (assumption-network-assumption-stamps network)
                    :test #'equal :count 1))
      report)))

(defun grounded-entry-p (network entry)
  (truth-maintained-fact-grounded-p
   (assumption-network-truth-network network)
   (fact-id (wm-entry-fact entry))))

(defun contradiction-report-key (report)
  (list (contradiction-report-spec-id report)
        (contradiction-report-left-stamp report)
        (contradiction-report-right-stamp report)))

(defun contradiction-reports-for-spec (network spec)
  "Return deterministic current contradiction reports for SPEC.

The left pattern is matched first. Its bindings are carried into the right
pattern, so shared variables encode the consistency key. Reports require two
distinct exact current occurrences and both occurrences must be grounded."
  (let ((entries (working-memory-entries
                  (assumption-network-working-memory network)))
        (reports '()))
    (dolist (left-entry entries)
      (let ((left-fact (wm-entry-fact left-entry)))
        (multiple-value-bind (left-bindings left-matched-p)
            (match-condition (contradiction-spec-left-pattern spec) left-fact)
          (when (and left-matched-p (grounded-entry-p network left-entry))
            (dolist (right-entry entries)
              (unless (eq left-entry right-entry)
                (let ((right-fact (wm-entry-fact right-entry)))
                  (multiple-value-bind (bindings right-matched-p)
                      (match-condition (contradiction-spec-right-pattern spec)
                                       right-fact
                                       left-bindings)
                    (when (and right-matched-p
                               (grounded-entry-p network right-entry))
                      (push
                       (make-contradiction-report
                        :spec-id (contradiction-spec-id spec)
                        :spec-provenance (contradiction-spec-provenance spec)
                        :bindings (copy-tree bindings)
                        :left-fact-id (fact-id left-fact)
                        :left-stamp (entry-stamp left-entry)
                        :left-support-kind
                        (assumption-network-support-kind network
                                                         (fact-id left-fact))
                        :right-fact-id (fact-id right-fact)
                        :right-stamp (entry-stamp right-entry)
                        :right-support-kind
                        (assumption-network-support-kind network
                                                         (fact-id right-fact)))
                       reports))))))))))
    (nreverse reports)))

(defun assumption-network-contradictions (network)
  "Return every current grounded contradiction in specification/memory order."
  (let ((reports
          (loop for spec in (assumption-network-contradiction-specs network)
                append (contradiction-reports-for-spec network spec))))
    (remove-duplicates reports
                       :test #'equal
                       :key #'contradiction-report-key)))

(defun assumption-network-consistency-status (network)
  "Return :CONSISTENT when no contradiction is current, else :CONTRADICTORY."
  (if (endp (assumption-network-contradictions network))
      :consistent
      :contradictory))

(defun make-consistency-run-result-from-network (network status contradictions)
  (let* ((truth (assumption-network-truth-network network))
         (engine (truth-maintained-engine truth))
         (agenda (incremental-agenda
                  (truth-maintained-network-incremental-network truth))))
    (make-consistency-run-result
     :status status
     :firing-count (length (engine-firing-records engine))
     :firing-records (copy-list (engine-firing-records engine))
     :remaining-activation-keys (mapcar #'activation-key agenda)
     :contradictions contradictions)))

(defun run-assumption-network (network
                               &key
                                 (firing-limit 100)
                                 (contradiction-policy :halt))
  "Forward-chain while making contradiction handling explicit.

:HALT checks for current contradictions before every next firing and returns
:CONTRADICTION without choosing a winner. Thus a contradiction produced by one
firing prevents a later firing from consuming the inconsistent state.
:REPORT-ONLY preserves the same counterevidence reports but continues ordinary
truth-maintained forward chaining. Neither mode retracts a contradictory fact.
"
  (unless (and (integerp firing-limit) (not (minusp firing-limit)))
    (error "FIRING-LIMIT must be a non-negative integer, got ~S." firing-limit))
  (unless (member contradiction-policy '(:halt :report-only) :test #'eq)
    (error "CONTRADICTION-POLICY must be :HALT or :REPORT-ONLY, got ~S."
           contradiction-policy))
  (let* ((truth (assumption-network-truth-network network))
         (incremental
           (truth-maintained-network-incremental-network truth)))
    (loop repeat firing-limit
          do (let ((contradictions
                     (assumption-network-contradictions network)))
               (when (and (eq contradiction-policy :halt)
                          contradictions)
                 (return-from run-assumption-network
                   (make-consistency-run-result-from-network
                    network :contradiction contradictions))))
             (let ((agenda (incremental-agenda incremental)))
               (when (endp agenda)
                 (return-from run-assumption-network
                   (make-consistency-run-result-from-network
                    network :quiescent
                    (assumption-network-contradictions network))))
               (truth-maintained-fire-activation truth (first agenda))))
    (let ((contradictions (assumption-network-contradictions network))
          (agenda (incremental-agenda incremental)))
      (make-consistency-run-result-from-network
       network
       (cond
         ((and (eq contradiction-policy :halt) contradictions)
          :contradiction)
         ((endp agenda) :quiescent)
         (t :limit))
       contradictions))))
