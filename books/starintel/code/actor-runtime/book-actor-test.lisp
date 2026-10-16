(in-package :star-server-tests)

(def-suite book-actor-tests
  :description "Executable Project 3 actor/dispatch boundary tests")

(in-suite book-actor-tests)

(defun make-book-target-document (&key (actor "book-audit")
                                       (id "starintel:target:book-actor-lab")
                                       (target "example.invalid"))
  (jsown:new-js
    ("_id" id)
    ("dtype" "target")
    ("actor" actor)
    ("target" target)
    ("delay" 1)
    ("recurring" :false)
    ("options" #())
    ("extensions" (jsown:empty-object))))

(defun make-book-envelope (&key
                             (id "starintel:target:book-actor-lab")
                             (target "example.invalid")
                             (trace-id "book-trace-001"))
  (let* ((record
           (star.actors:parse-target-record
            (make-book-target-document :id id :target target)))
         (destination
           (star.actors:resolve-target-destination
            (starintel-book.actor-lab:book-actor-name))))
    (values
     (star.actors:make-target-dispatch-envelope
      record
      :destination destination
      :trace-id trace-id
      :lease-id (format nil "book-lease-~a" trace-id))
     destination)))

(defun wait-for-book-receipt (&key (attempts 100) (sleep-seconds 0.01))
  (loop repeat attempts
        for receipts = (starintel-book.actor-lab:book-receipts)
        when receipts do (return receipts)
        do (sleep sleep-seconds)
        finally (return nil)))

(test book-actor-registers-and-receives-current-envelope
  (let ((system (make-actor-system)))
    (unwind-protect
         (progn
           ;; START-ACTOR-INDEX is intentionally internal test setup.  The book
           ;; actor itself uses the exported registration/dispatch surface.
           (star.actors::start-actor-index system)
           (starintel-book.actor-lab:reset-book-receipts)
           (let ((actor (starintel-book.actor-lab:start-book-actor system)))
             (is (eq actor
                     (star.actors:get-dest-actor
                      (starintel-book.actor-lab:book-actor-name))))
             (multiple-value-bind (envelope destination)
                 (make-book-envelope)
               (is (eq :local
                       (star.actors:target-destination-handle-kind destination)))
               (is-true (star.actors:dispatch-target-envelope-now envelope))
               (let ((receipts (wait-for-book-receipt)))
                 (is (= 1 (length receipts)))
                 (is (string= "example.invalid"
                              (getf (first receipts) :target)))
                 (is (string= "book-trace-001"
                              (getf (first receipts) :trace-id)))
                 (is (string= "starintel:target:book-actor-lab"
                              (getf (first receipts) :schedule-id)))))))
      (ignore-errors (sento.actor-context:shutdown system :wait t))
      (setf star.actors::*actor-index-agent* nil)
      (starintel-book.actor-lab:reset-book-receipts))))

(test handler-exception-isolated-and-same-actor-keeps-processing
  (let ((system (make-actor-system)))
    (unwind-protect
         (progn
           (star.actors::start-actor-index system)
           (starintel-book.actor-lab:reset-book-receipts)
           (let ((actor (starintel-book.actor-lab:start-book-actor system)))
             (is-true (sento.actor-cell:running-p actor))
             (starintel-book.actor-lab:arm-book-handler-failure)
             (multiple-value-bind (failing-envelope failing-destination)
                 (make-book-envelope
                  :id "starintel:target:book-actor-failure"
                  :target "failure.example.invalid"
                  :trace-id "book-trace-failure")
               (is (eq :local
                       (star.actors:target-destination-handle-kind
                        failing-destination)))
               (is-true
                (star.actors:dispatch-target-envelope-now failing-envelope)))
             ;; Sento processes one actor mailbox serially.  Queueing a valid
             ;; envelope after the failing envelope lets its observed receipt
             ;; prove that the same mailbox crossed the exception boundary and
             ;; continued handling messages.
             (multiple-value-bind (after-envelope after-destination)
                 (make-book-envelope
                  :id "starintel:target:book-actor-after-failure"
                  :target "after.example.invalid"
                  :trace-id "book-trace-after-failure")
               (is (eq :local
                       (star.actors:target-destination-handle-kind
                        after-destination)))
               (is-true
                (star.actors:dispatch-target-envelope-now after-envelope)))
             (let ((receipts (wait-for-book-receipt)))
               (is (= 1 (length receipts)))
               (is (string= "after.example.invalid"
                            (getf (first receipts) :target)))
               (is (string= "book-trace-after-failure"
                            (getf (first receipts) :trace-id))))
             (is (not (starintel-book.actor-lab:book-failure-armed-p)))
             (is-true (sento.actor-cell:running-p actor))
             (is (eq actor
                     (star.actors:get-dest-actor
                      (starintel-book.actor-lab:book-actor-name))))))
      (ignore-errors (sento.actor-context:shutdown system :wait t))
      (setf star.actors::*actor-index-agent* nil)
      (starintel-book.actor-lab:reset-book-receipts))))

(test unresolved-actor-selects-current-canonical-rabbit-route
  (let ((system (make-actor-system)))
    (unwind-protect
         (progn
           (star.actors::start-actor-index system)
           (let ((destination
                   (star.actors:resolve-target-destination "remote-demo")))
             (is (eq :rabbit
                     (star.actors:target-destination-handle-kind destination)))
             (is (string= "documents.target.dispatch.remote-demo"
                          (star.actors:target-destination-handle-routing-key
                           destination)))
             (is (equal '("actors.remote-demo.new.target")
                        (star.actors:target-destination-handle-compatibility-routing-keys
                         destination)))))
      (ignore-errors (sento.actor-context:shutdown system :wait t))
      (setf star.actors::*actor-index-agent* nil))))

(test actor-identity-validation-fails-before-routing
  (signals star.actors:invalid-target-dispatch
    (star.actors:canonical-target-routing-key "bad actor/name")))
