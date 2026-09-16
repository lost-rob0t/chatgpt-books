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
