(in-package #:expert-systems.matcher)

(defparameter *service-diagnosis-facts*
  (list
   (make-fact
    :id "obs.api.state.failed"
    :relation 'service-state
    :arguments '(api failed)
    :provenance '(:kind :synthetic-observation
                  :scenario "api-start-failure"
                  :source "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"))
   (make-fact
    :id "cfg.api.restart.on-failure"
    :relation 'service-restart-policy
    :arguments '(api on-failure)
    :provenance '(:kind :synthetic-configuration
                  :scenario "api-start-failure"
                  :source "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"))
   (make-fact
    :id "obs.api.exit-code.1"
    :relation 'service-exit-code
    :arguments '(api 1)
    :provenance '(:kind :synthetic-observation
                  :scenario "api-start-failure"
                  :source "https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html"))
   (make-fact
    :id "dep.frontend.api"
    :relation 'depends-on
    :arguments '(frontend api)
    :provenance '(:kind :synthetic-topology
                  :scenario "api-start-failure"
                  :source "book-fixture"))
   (make-fact
    :id "obs.frontend.state.degraded"
    :relation 'service-state
    :arguments '(frontend degraded)
    :provenance '(:kind :synthetic-observation
                  :scenario "api-start-failure"
                  :source "book-fixture"))))

(defun derived-provenance (rule-id activation)
  "Build provenance for a fact derived inside the synthetic teaching scenario."
  (list :kind :derived
        :scenario "api-start-failure"
        :source "book-derived"
        :rule-id rule-id
        :support-fact-ids (copy-list (activation-fact-ids activation))))

(defun dependency-impact-action (activation)
  (let ((service (activation-binding activation '?service))
        (dependency (activation-binding activation '?dependency)))
    (list
     (make-fact
      :id (format nil "derived.dependency-impact.~(~A~).~(~A~)"
                  service dependency)
      :relation 'dependency-impact
      :arguments (list service dependency)
      :provenance
      (derived-provenance "rule.dependency-impact" activation)))))

(defun investigate-degraded-dependent-action (activation)
  (let ((service (activation-binding activation '?service)))
    (list
     (make-fact
      :id (format nil "derived.needs-investigation.~(~A~)" service)
      :relation 'needs-investigation
      :arguments (list service)
      :provenance
      (derived-provenance "rule.investigate-degraded-dependent" activation)))))

(defun make-service-diagnosis-productions ()
  "Return the two synthetic productions used by the milestone-B forward-chain lab."
  (list
   (make-production
    :id "rule.dependency-impact"
    :conditions '((service-state ?dependency failed)
                  (depends-on ?service ?dependency))
    :salience 10
    :provenance '(:kind :book-rule
                  :scenario "api-start-failure"
                  :status :synthetic-teaching-rule)
    :action #'dependency-impact-action)
   (make-production
    :id "rule.investigate-degraded-dependent"
    :conditions '((dependency-impact ?service ?dependency)
                  (service-state ?service degraded))
    :salience 0
    :provenance '(:kind :book-rule
                  :scenario "api-start-failure"
                  :status :synthetic-teaching-rule)
    :action #'investigate-degraded-dependent-action)))
