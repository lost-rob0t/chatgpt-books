(in-package #:expert-systems.service-kb)

(defparameter *systemd-unit-v2613-source*
  '(:kind :upstream-documentation
    :project "systemd"
    :release "v261.3"
    :published "2026-09-10"
    :retrieved "2026-09-16"
    :path "man/systemd.unit.xml"
    :url "https://github.com/systemd/systemd/blob/v261.3/man/systemd.unit.xml")
  "Pinned upstream source metadata for the Project 2 dependency rules.")

(defun rule-source (documented-claim)
  (append (copy-list *systemd-unit-v2613-source*)
          (list :documented-claim documented-claim
                :course-status :source-backed-teaching-rule)))

(defun observation-provenance (kind scenario source-id)
  "Build explicit provenance for one synthetic fixture observation.

The source is intentionally fixture-local. Upstream documentation justifies the
rule semantics; it does not pretend these observations came from a real host."
  (list :kind kind
        :status :synthetic
        :scenario scenario
        :source-id source-id
        :source "book-fixture"))

(defun derived-hypothesis-provenance (rule-id activation)
  (list :kind :derived-diagnostic-hypothesis
        :status :course-inference
        :rule-id rule-id
        :support-fact-ids (copy-list (activation-fact-ids activation))))

(defun derived-boundary-provenance (rule-id activation)
  (list :kind :derived-diagnostic-boundary
        :status :course-inference
        :rule-id rule-id
        :support-fact-ids (copy-list (activation-fact-ids activation))))

(defun stable-component-string (value)
  (string-downcase (princ-to-string value)))

(defun required-dependency-hypothesis-id (unit dependency attempt generation)
  (format nil "hypothesis.required-dependency-blocked.~A.~A.~A.~A"
          (stable-component-string unit)
          (stable-component-string dependency)
          (stable-component-string attempt)
          (stable-component-string generation)))

(defun wanted-dependency-boundary-id (unit dependency attempt generation)
  (format nil "boundary.wanted-dependency-failure.~A.~A.~A.~A"
          (stable-component-string unit)
          (stable-component-string dependency)
          (stable-component-string attempt)
          (stable-component-string generation)))

(defun required-dependency-block-action (activation)
  (let ((unit (activation-binding activation '?unit))
        (dependency (activation-binding activation '?dependency))
        (attempt (activation-binding activation '?attempt))
        (generation (activation-binding activation '?generation)))
    (list
     (make-fact
      :id (required-dependency-hypothesis-id
           unit dependency attempt generation)
      :relation 'diagnostic-hypothesis
      :arguments (list :required-dependency-blocked-startup
                       unit dependency attempt generation)
      :provenance
      (derived-hypothesis-provenance
       "rule.systemd.requires-after-failed-dependency" activation)))))

(defun wanted-dependency-failure-boundary-action (activation)
  (let ((unit (activation-binding activation '?unit))
        (dependency (activation-binding activation '?dependency))
        (attempt (activation-binding activation '?attempt))
        (generation (activation-binding activation '?generation)))
    (list
     (make-fact
      :id (wanted-dependency-boundary-id
           unit dependency attempt generation)
      :relation 'diagnostic-boundary
      :arguments (list :wanted-unit-failure-alone-does-not-invalidate-transaction
                       unit dependency attempt generation)
      :provenance
      (derived-boundary-provenance
       "rule.systemd.wants-failure-boundary" activation)))))

(defun make-systemd-dependency-productions ()
  "Return the source-backed Project 2 dependency rules.

These rules cover a deliberately narrow subset of systemd unit dependency
semantics documented by v261.3. They are not a complete systemd model."
  (list
   (make-production
    :id "rule.systemd.requires-after-failed-dependency"
    :conditions
    '((unit-requirement ?unit ?dependency :requires ?generation)
      (unit-ordering ?unit ?dependency :after ?generation)
      (activation-attempt ?unit ?attempt ?generation)
      (activation-outcome ?dependency ?attempt ?generation :failed))
    :salience 20
    :provenance
    (rule-source
     :requires-plus-after-and-failed-required-unit-prevents-dependent-start)
    :action #'required-dependency-block-action)
   (make-production
    :id "rule.systemd.wants-failure-boundary"
    :conditions
    '((unit-requirement ?unit ?dependency :wants ?generation)
      (activation-attempt ?unit ?attempt ?generation)
      (activation-outcome ?dependency ?attempt ?generation :failed))
    :salience 10
    :provenance
    (rule-source
     :wanted-unit-start-failure-does-not-invalidate-transaction-as-a-whole)
    :action #'wanted-dependency-failure-boundary-action)))

(defun fixture-fact (id relation arguments kind scenario source-id)
  (make-fact
   :id id
   :relation relation
   :arguments arguments
   :provenance (observation-provenance kind scenario source-id)))

(defun make-systemd-dependency-fixture
    (&key
       (unit "frontend.service")
       (dependency "api.service")
       (requirement-kind :requires)
       (include-requirement t)
       (include-ordering t)
       (attempt "attempt-1")
       (generation "generation-1")
       (requirement-generation generation)
       (ordering-generation generation)
       (attempt-generation generation)
       (outcome-attempt attempt)
       (outcome-generation generation)
       (dependency-outcome :failed)
       (scenario "systemd-dependency-fixture"))
  "Build synthetic, provenance-bearing systemd dependency observations.

Separate generation/attempt keyword arguments exist specifically so tests and
reader labs can demonstrate failed joins across stale configuration or another
activation attempt. Nothing returned by this function is a real-host claim."
  (remove
   nil
   (list
    (and include-requirement
         (fixture-fact
          "cfg.unit.requirement"
          'unit-requirement
          (list unit dependency requirement-kind requirement-generation)
          :synthetic-configuration scenario "fixture:unit-requirement"))
    (and include-ordering
         (fixture-fact
          "cfg.unit.ordering"
          'unit-ordering
          (list unit dependency :after ordering-generation)
          :synthetic-configuration scenario "fixture:unit-ordering"))
    (fixture-fact
     "obs.unit.activation-attempt"
     'activation-attempt
     (list unit attempt attempt-generation)
     :synthetic-observation scenario "fixture:activation-attempt")
    (fixture-fact
     "obs.dependency.activation-outcome"
     'activation-outcome
     (list dependency outcome-attempt outcome-generation dependency-outcome)
     :synthetic-observation scenario "fixture:dependency-outcome"))))

(defun make-systemd-dependency-network (facts)
  "Construct the Project 2 network without duplicating inference internals."
  (make-assumption-network
   (make-truth-maintained-network
    (make-engine :facts facts
                 :productions (make-systemd-dependency-productions)))))

(defun run-systemd-dependency-case (facts &key (firing-limit 20))
  "Run one synthetic dependency case and return NETWORK, then RUN-RESULT."
  (let ((network (make-systemd-dependency-network facts)))
    (values
     network
     (run-assumption-network
      network
      :firing-limit firing-limit
      :contradiction-policy :report-only))))

(defun explain-required-dependency-hypothesis
    (network unit dependency attempt generation)
  (explain-current-fact
   network
   (required-dependency-hypothesis-id unit dependency attempt generation)))
