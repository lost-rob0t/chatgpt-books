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

(defparameter *service-diagnosis-productions*
  (list
   (make-production
    :id "derive.dependency-impact"
    :conditions '((service-state ?dependency failed)
                  (depends-on ?service ?dependency))
    :actions '((:assert dependency-impact ?service ?dependency))
    :salience 20
    :provenance '(:kind :book-rule :scenario "api-start-failure"))
   (make-production
    :id "derive.restart-candidate"
    :conditions '((service-state ?service failed)
                  (service-restart-policy ?service on-failure))
    :actions '((:assert restart-candidate ?service))
    :salience 10
    :provenance '(:kind :book-rule :scenario "api-start-failure"))))
