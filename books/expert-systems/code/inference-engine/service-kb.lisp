(in-package #:expert-systems.matcher)

(defparameter *systemd-unit-source-url*
  "https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html")

(defparameter *systemd-unit-state-source-url*
  "https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.systemd1.html")

(defun systemd-kb-provenance (kind source-id source-url &rest fields)
  "Build structured provenance for Project 2 source-backed teaching data.

KIND distinguishes configuration, observations, and derived hypotheses.
SOURCE-ID names the inspected authority record; SOURCE-URL is preserved for
reader/debugging inspection. FIELDS are additional plist entries. The helper
records retrieval date but does not assign confidence or authority scores."
  (append (list :kind kind
                :source-id source-id
                :source-url source-url
                :retrieved "2026-09-16")
          fields))

(defun make-systemd-start-request-fact (id service attempt config-generation)
  "Create one synthetic modeled start request with explicit attempt/config IDs."
  (make-fact
   :id id
   :relation 'unit-start-request
   :arguments (list service attempt config-generation)
   :provenance
   (systemd-kb-provenance
    :synthetic-observation
    "book.project2.start-request"
    "book-fixture"
    :status :synthetic-fixture
    :observation-kind :modeled-start-request)))

(defun make-systemd-requirement-fact
    (id service dependency kind config-generation)
  "Create one synthetic unit requirement fact for REQUIRES or WANTS."
  (unless (member kind '(requires wants) :test #'eq)
    (error "Requirement KIND must be REQUIRES or WANTS, got ~S." kind))
  (make-fact
   :id id
   :relation 'unit-requirement
   :arguments (list service dependency kind config-generation)
   :provenance
   (systemd-kb-provenance
    :synthetic-configuration
    "systemd.unit.requirement"
    *systemd-unit-source-url*
    :status :synthetic-fixture
    :directive kind)))

(defun make-systemd-ordering-fact
    (id service dependency relation config-generation)
  "Create one synthetic unit ordering fact for AFTER or BEFORE."
  (unless (member relation '(after before) :test #'eq)
    (error "Ordering RELATION must be AFTER or BEFORE, got ~S." relation))
  (make-fact
   :id id
   :relation 'unit-ordering
   :arguments (list service dependency relation config-generation)
   :provenance
   (systemd-kb-provenance
    :synthetic-configuration
    "systemd.unit.ordering"
    *systemd-unit-source-url*
    :status :synthetic-fixture
    :directive relation)))

(defun make-systemd-activation-fact
    (id unit state attempt config-generation)
  "Create one synthetic activation-state observation for a modeled attempt."
  (unless (member state '(active failed inactive activating deactivating)
                  :test #'eq)
    (error "Unsupported teaching activation STATE ~S." state))
  (make-fact
   :id id
   :relation 'unit-activation
   :arguments (list unit state attempt config-generation)
   :provenance
   (systemd-kb-provenance
    :synthetic-observation
    "systemd.dbus.unit.active-state"
    *systemd-unit-state-source-url*
    :status :synthetic-fixture
    :property 'active-state)))

(defun systemd-required-after-rule-provenance ()
  "Return provenance for the one source-backed Project 2 production.

Current systemd.unit documentation states that Requires= activates listed
units and that, when a required unit fails to activate and an After= ordering
dependency on it is set, the requiring unit will not be started. Requirement
and ordering dependencies are documented as orthogonal. The production below
encodes only that bounded combination for one modeled start attempt."
  (systemd-kb-provenance
   :source-backed-course-rule
   "systemd.unit.requires-after-failure"
   *systemd-unit-source-url*
   :documented-claim :required-unit-failure-with-after-prevents-start
   :scope :modeled-start-attempt))

(defun required-dependency-blocked-start-action (activation)
  "Materialize the bounded diagnostic hypothesis for one complete activation."
  (let ((service (activation-binding activation '?service))
        (dependency (activation-binding activation '?dependency))
        (attempt (activation-binding activation '?attempt))
        (config (activation-binding activation '?config)))
    (list
     (make-fact
      :id (format nil "diagnosis.required-block.~(~A~).~(~A~).~(~A~).~(~A~)"
                  service dependency attempt config)
      :relation 'startup-blocked-by-required-dependency
      :arguments (list service dependency attempt config)
      :provenance
      (systemd-kb-provenance
       :derived-hypothesis
       "systemd.unit.requires-after-failure"
       *systemd-unit-source-url*
       :status :source-backed-course-rule
       :rule-id "rule.systemd.required-after-failure"
       :support-fact-ids (copy-list (activation-fact-ids activation)))))))

(defun make-systemd-dependency-productions ()
  "Return Project 2 milestone-A source-backed productions.

There is intentionally no rule for WANTS+failure, AFTER alone, or REQUIRES
alone. Their absence is part of the tested domain boundary, not an implicit
closed-world conclusion about every systemd behavior."
  (list
   (make-production
    :id "rule.systemd.required-after-failure"
    :conditions
    '((unit-start-request ?service ?attempt ?config)
      (unit-requirement ?service ?dependency requires ?config)
      (unit-ordering ?service ?dependency after ?config)
      (unit-activation ?dependency failed ?attempt ?config))
    :salience 20
    :provenance (systemd-required-after-rule-provenance)
    :action #'required-dependency-blocked-start-action)))

(defun make-systemd-dependency-fixture ()
  "Return a synthetic four-fact fixture matching the documented rule boundary."
  (list
   (make-systemd-start-request-fact
    "obs.frontend.start.attempt-17" 'frontend 'attempt-17 'config-3)
   (make-systemd-requirement-fact
    "cfg.frontend.requires.api.config-3" 'frontend 'api 'requires 'config-3)
   (make-systemd-ordering-fact
    "cfg.frontend.after.api.config-3" 'frontend 'api 'after 'config-3)
   (make-systemd-activation-fact
    "obs.api.failed.attempt-17" 'api 'failed 'attempt-17 'config-3)))

(defun make-systemd-dependency-kb (&optional (facts (make-systemd-dependency-fixture)))
  "Build the Project 2 teaching KB over the accepted Project 1 engine stack."
  (make-assumption-network
   (make-truth-maintained-network
    (make-engine :facts facts
                 :productions (make-systemd-dependency-productions)))))

(defun systemd-diagnosis-fact-id (service dependency attempt config-generation)
  "Return the deterministic stable ID used by the milestone-A diagnosis fact."
  (format nil "diagnosis.required-block.~(~A~).~(~A~).~(~A~).~(~A~)"
          service dependency attempt config-generation))
