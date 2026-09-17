(in-package #:symbolic-ai.rules)

(define-condition invalid-derived-fact (error)
  ((datum :initarg :datum :reader invalid-derived-fact-datum))
  (:report (lambda (condition stream)
             (format stream "Rule action produced an ungrounded fact: ~S"
                     (invalid-derived-fact-datum condition)))))

(define-condition invalid-rule-action-output (error)
  ((value :initarg :value :reader invalid-rule-action-output-value))
  (:report (lambda (condition stream)
             (format stream "Rule action must return a proper list of facts, got: ~S"
                     (invalid-rule-action-output-value condition)))))

(defstruct fact
  id
  datum
  origin)

(defstruct (working-memory (:constructor %make-working-memory))
  (facts '())
  (next-id 1))

(defstruct (rule (:constructor %make-rule))
  id
  (conditions '())
  (salience 0)
  action
  (allow-fact-reuse-p nil))

(defstruct activation
  rule-id
  rule-order
  salience
  bindings
  support-fact-ids
  rule)

(defstruct justification
  fact-id
  rule-id
  bindings
  support-fact-ids)

(defstruct firing
  index
  activation
  asserted-fact-ids
  duplicate-fact-ids)

(defstruct run-result
  status
  working-memory
  firings
  justifications
  remaining-agenda)

(defun ground-term-p (term)
  "True when TERM contains no project symbolic variables."
  (cond
    ((symbolic-ai.pattern:variable-p term) nil)
    ((consp term)
     (and (ground-term-p (car term))
          (ground-term-p (cdr term))))
    (t t)))

(defun binding-value (name bindings)
  "Return two values: the value bound to NAME and whether NAME is present."
  (let ((binding (assoc name bindings :test #'equal)))
    (if binding
        (values (cdr binding) t)
        (values nil nil))))

(defun make-working-memory (&optional (data '()))
  "Create working memory and assert DATA in order, deduplicating EQUAL facts."
  (let ((memory (%make-working-memory)))
    (dolist (datum data memory)
      (assert-fact memory datum :origin :initial))))

(defun %find-fact-by-datum (memory datum)
  (find datum (working-memory-facts memory)
        :key #'fact-datum
        :test #'equal))

(defun assert-fact (memory datum &key origin)
  "Assert ground DATUM into MEMORY.

Return the FACT and a second value that is true only when a new fact was added.
Existing EQUAL facts keep their original stable fact identity."
  (unless (ground-term-p datum)
    (error 'invalid-derived-fact :datum datum))
  (let ((existing (%find-fact-by-datum memory datum)))
    (if existing
        (values existing nil)
        (let ((fact (make-fact :id (working-memory-next-id memory)
                               :datum datum
                               :origin origin)))
          (incf (working-memory-next-id memory))
          (setf (working-memory-facts memory)
                (append (working-memory-facts memory) (list fact)))
          (values fact t)))))

(defun make-rule (id conditions action &key (salience 0) (allow-fact-reuse-p nil))
  "Create a transparent production rule.

CONDITIONS are directional patterns consumed by the book's Pattern Matcher.
ACTION is a function of one argument, the final binding environment, and must
return a proper list of ground facts to assert."
  (unless (listp conditions)
    (error "Rule conditions must be a list, got ~S" conditions))
  (unless (functionp action)
    (error "Rule action must be a function, got ~S" action))
  (unless (integerp salience)
    (error "Rule salience must be an integer, got ~S" salience))
  (%make-rule :id id
              :conditions conditions
              :salience salience
              :action action
              :allow-fact-reuse-p allow-fact-reuse-p))

(defun %condition-matches (conditions facts bindings support-ids allow-reuse-p)
  (if (endp conditions)
      (list (cons bindings (reverse support-ids)))
      (mapcan
       (lambda (fact)
         (if (and (not allow-reuse-p)
                  (member (fact-id fact) support-ids :test #'eql))
             '()
             (let ((result
                     (symbolic-ai.pattern:match-pattern
                      (first conditions)
                      (fact-datum fact)
                      :bindings bindings)))
               (if (eq :matched (symbolic-ai.pattern:match-result-status result))
                   (%condition-matches
                    (rest conditions)
                    facts
                    (symbolic-ai.pattern:match-result-bindings result)
                    (cons (fact-id fact) support-ids)
                    allow-reuse-p)
                   '()))))
       facts)))

(defun %activation-key (activation)
  (list (activation-rule-id activation)
        (activation-support-fact-ids activation)))

(defun %number-list< (left right)
  (loop
    for x in left
    for y in right
    when (< x y) do (return t)
    when (> x y) do (return nil)
    finally (return (< (length left) (length right)))))

(defun %activation< (left right)
  (cond
    ((> (activation-salience left) (activation-salience right)) t)
    ((< (activation-salience left) (activation-salience right)) nil)
    ((< (activation-rule-order left) (activation-rule-order right)) t)
    ((> (activation-rule-order left) (activation-rule-order right)) nil)
    (t (%number-list< (activation-support-fact-ids left)
                      (activation-support-fact-ids right)))))

(defun build-agenda (rules memory &key (fired-keys '()))
  "Fully rematch RULES against MEMORY and return deterministic activations.

This milestone intentionally rebuilds the agenda from working memory after each
firing. FIRED-KEYS implements exact-activation refraction; later material can
replace full rematching with incremental memories without changing this public
semantic contract."
  (let ((activations '())
        (facts (working-memory-facts memory)))
    (loop
      for rule in rules
      for rule-order from 0
      do (dolist (match
                   (%condition-matches
                    (rule-conditions rule)
                    facts
                    '()
                    '()
                    (rule-allow-fact-reuse-p rule)))
           (let ((activation
                   (make-activation
                    :rule-id (rule-id rule)
                    :rule-order rule-order
                    :salience (rule-salience rule)
                    :bindings (car match)
                    :support-fact-ids (cdr match)
                    :rule rule)))
             (unless (member (%activation-key activation)
                             fired-keys
                             :test #'equal)
               (push activation activations)))))
    (stable-sort activations #'%activation<)))

(defun %proper-list-p (value)
  (loop
    for tail = value then (cdr tail)
    while (consp tail)
    finally (return (null tail))))

(defun %ensure-unique-rule-ids (rules)
  (let ((seen '()))
    (dolist (rule rules)
      (when (member (rule-id rule) seen :test #'equal)
        (error "Duplicate rule identity: ~S" (rule-id rule)))
      (push (rule-id rule) seen))))

(defun %finish-run (status memory firings justifications agenda)
  (make-run-result :status status
                   :working-memory memory
                   :firings (reverse firings)
                   :justifications (reverse justifications)
                   :remaining-agenda agenda))

(defun run-rules (initial-facts rules &key (max-firings 100))
  "Forward-chain RULES from INITIAL-FACTS.

Return :QUIESCENT only when no unfired activation remains. Return :BOUNDED when
MAX-FIRINGS stops execution while an activation still exists. The engine uses
exact-activation refraction keyed by rule identity plus supporting fact IDs."
  (unless (and (integerp max-firings) (not (minusp max-firings)))
    (error "MAX-FIRINGS must be a nonnegative integer, got ~S" max-firings))
  (%ensure-unique-rule-ids rules)
  (let ((memory (make-working-memory initial-facts))
        (fired-keys '())
        (firings '())
        (justifications '())
        (firing-count 0))
    (loop
      for agenda = (build-agenda rules memory :fired-keys fired-keys)
      do (cond
           ((endp agenda)
            (return (%finish-run :quiescent memory firings justifications '())))
           ((>= firing-count max-firings)
            (return (%finish-run :bounded memory firings justifications agenda)))
           (t
            (let* ((activation (first agenda))
                   (rule (activation-rule activation))
                   (output (funcall (rule-action rule)
                                    (activation-bindings activation)))
                   (asserted '())
                   (duplicates '()))
              (unless (%proper-list-p output)
                (error 'invalid-rule-action-output :value output))
              (push (%activation-key activation) fired-keys)
              (dolist (datum output)
                (unless (ground-term-p datum)
                  (error 'invalid-derived-fact :datum datum))
                (multiple-value-bind (fact new-p)
                    (assert-fact
                     memory datum
                     :origin (list :rule (activation-rule-id activation)))
                  (if new-p
                      (progn
                        (push (fact-id fact) asserted)
                        (push
                         (make-justification
                          :fact-id (fact-id fact)
                          :rule-id (activation-rule-id activation)
                          :bindings (copy-tree (activation-bindings activation))
                          :support-fact-ids
                          (copy-list (activation-support-fact-ids activation)))
                         justifications))
                      (push (fact-id fact) duplicates))))
              (incf firing-count)
              (push
               (make-firing :index firing-count
                            :activation activation
                            :asserted-fact-ids (reverse asserted)
                            :duplicate-fact-ids (reverse duplicates))
               firings)))))))
